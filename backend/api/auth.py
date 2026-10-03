# -*- coding: utf-8 -*-
"""认证与用户接口（/api/auth）。"""

from __future__ import annotations

from flask import Blueprint, current_app, g, request

from ..audit import logger as audit_logger
from ..extensions import db
from ..models import LoginSession, TokenBlacklist, User, now
from ..utils.deps import (
    PERMISSION_MATRIX,
    ROLE_LABELS,
    apply_circuit_breaker,
    auth_required,
    evaluate_risk,
    permissions_of,
)
from ..utils.response import ApiError, body, ok, require_fields
from ..utils.security import create_token, decode_token, verify_password

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    """登录：口令 + MFA 动态码 + 数字证书校验（零信任身份三要素）。"""
    payload = body()
    require_fields(payload, ["username", "password"])
    username = payload["username"]
    password = payload["password"]
    role = payload.get("role") or None
    mfa_code = str(payload.get("mfaCode", ""))
    cert_no = payload.get("certNo")

    user = User.query.filter_by(username=username).first()
    if user is None or not verify_password(user.passwordHash, password):
        # 登录失败也留痕，便于异常检测
        audit_logger.record(username, role or "", "login", result="failed", detail="用户名或口令错误")
        raise ApiError("用户名或口令错误", code=401)

    if user.status == "locked":
        raise ApiError("账号已被熔断锁定，请联系数据安全管理员申诉解锁", code=429)
    if user.status != "active":
        raise ApiError("账号状态异常，禁止登录", code=403)

    if user.mfaEnabled:
        expected = str(current_app.config.get("DEMO_MFA_CODE", "123456"))
        if mfa_code and mfa_code != expected:
            audit_logger.record(username, user.role, "login", result="failed", detail="MFA 动态码错误")
            raise ApiError("多因素认证失败：动态码错误", code=401)
        if not mfa_code:
            raise ApiError("该账号已启用多因素认证，请填写 6 位动态码（演示环境为 123456）", code=401)

    if cert_no and user.certNo and cert_no != user.certNo:
        audit_logger.record(username, user.role, "login", result="failed", detail="数字证书不匹配")
        raise ApiError("数字证书校验失败：证书编号与账号绑定关系不一致", code=401)

    # 记录登录地区，用于「同一账号跨地区同时登录」的异常检测
    login_region = payload.get("region") or user.region or "中国"
    session = LoginSession(
        username=user.username,
        role=user.role,
        region=login_region,
        ip=request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1"),
        loginAt=now(),
        risk="normal",
    )
    db.session.add(session)

    user.lastLoginAt = now()
    user.lastLoginIp = session.ip
    db.session.commit()

    # 登录动作写入审计日志（含风险评分与链上存证）
    risk_score, severity, rules_hit = evaluate_risk(user, "login")
    audit_logger.record(
        user.username, user.role, "login", target=ROLE_LABELS.get(user.role, user.role),
        node=login_region, operation="登录", risk_score=risk_score,
        detail=f"登录地区：{login_region}",
    )
    if rules_hit:
        session.risk = severity
        session.note = "；".join(rules_hit)
        db.session.commit()
        apply_circuit_breaker(user, rules_hit, severity)

    token, expires_in = create_token(user, role=role or user.role)
    return ok(
        {
            "token": token,
            "expiresIn": expires_in,
            "user": user.to_dict(),
            "permissions": permissions_of(user.role),
            "risk": {"score": risk_score, "severity": severity, "rules": rules_hit},
        },
        message="登录成功",
    )


@bp.post("/logout")
@auth_required
def logout():
    """登出：JWT 加入黑名单，令牌立即失效。"""
    payload = g.get("jwt") or {}
    jti = payload.get("jti")
    if jti:
        db.session.add(
            TokenBlacklist(jti=jti, username=payload.get("sub", ""), reason="logout", expireAt=now())
        )
        db.session.commit()
    audit_logger.record_from_request("logout", operation="登出")
    return ok({"success": True}, message="已安全退出")


@bp.get("/profile")
@auth_required
def profile():
    """当前用户信息与权限点。"""
    user = g.user
    return ok(
        {
            "user": user.to_dict(),
            "roleLabel": ROLE_LABELS.get(g.role, g.role),
            "permissions": permissions_of(g.role),
        }
    )


@bp.get("/roles")
def roles():
    """角色与权限矩阵（登录页/权限说明页使用，无需鉴权）。"""
    return ok(
        [
            {
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "description": _role_description(role),
                "permissions": permissions,
            }
            for role, permissions in PERMISSION_MATRIX.items()
        ]
    )


def _role_description(role: str) -> str:
    return {
        "pingpong": "PingPong 内部风控/合规角色：发起隐私计算任务、配置合规规则、管理授权与预算",
        "merchant": "出海商户角色：查询制裁清单、查看交易统计与自身合规状态、生成合规报告",
        "regulator": "监管机构角色：查看数据流转日志、合规报告与联盟链存证，校验链完整性",
        "admin": "数据安全管理员：全量权限，负责权限审批、熔断处置与审计",
    }.get(role, "")


@bp.get("/sessions")
@auth_required
def sessions():
    """在线会话列表与异常登录检测结果。"""
    rows = LoginSession.query.order_by(LoginSession.loginAt.desc()).limit(30).all()
    return ok([item.to_dict() for item in rows])


@bp.post("/verify-token")
def verify_token():
    """令牌校验（供网关/其他微服务调用）。"""
    payload = body()
    token = payload.get("token")
    if not token:
        raise ApiError("缺少 token 参数")
    claims = decode_token(token)
    if TokenBlacklist.query.filter_by(jti=claims.get("jti", "")).first():
        return ok({"valid": False, "reason": "token 已加入黑名单"})
    return ok({"valid": True, "claims": claims})
