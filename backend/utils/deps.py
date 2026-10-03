# -*- coding: utf-8 -*-
"""鉴权、权限矩阵与零信任动态管控依赖。

权限模型（与 docs/API.md §10、前端 src/store/user.js 保持一致）：
- 角色：pingpong（PingPong 运营/风控）、merchant（商户）、regulator（监管机构）、admin（数据安全管理员）
- 权限点：`模块:资源:动作`，例如 engine:task:create、compliance:rule:manage
- 零信任：每次敏感操作都会做「身份 → 数据敏感度 → 使用场景」动态判定，
  异常行为触发分级熔断（锁定账号或暂停数据传输权限 1-24 小时）。
"""

from __future__ import annotations

from datetime import timedelta
from functools import wraps
from typing import Iterable

from flask import g, request

from ..config import Config
from ..extensions import db
from ..models import AuditLog, CircuitBreakerEvent, TokenBlacklist, User, now
from ..utils.response import ApiError
from ..utils.security import decode_token

# 角色 → 权限点
PERMISSION_MATRIX: dict[str, list[str]] = {
    "pingpong": [
        "engine:task:create", "engine:task:manage", "engine:query:oblivious", "engine:stats:joint",
        "compliance:rule:manage", "compliance:report:create", "compliance:report:view",
        "authz:grant:manage", "authz:grant:view", "budget:manage", "lineage:view",
        "audit:view", "audit:chain:verify",
    ],
    "merchant": [
        "engine:query:oblivious", "engine:stats:joint", "compliance:report:create",
        "compliance:report:view", "authz:grant:view", "lineage:view",
    ],
    "regulator": [
        "engine:stats:joint", "compliance:report:view", "authz:grant:view", "lineage:view",
        "audit:view", "audit:chain:verify",
    ],
    "admin": [
        "engine:task:create", "engine:task:manage", "engine:query:oblivious", "engine:stats:joint",
        "compliance:rule:manage", "compliance:report:create", "compliance:report:view",
        "authz:grant:manage", "authz:grant:view", "budget:manage", "lineage:view",
        "audit:view", "audit:chain:verify",
    ],
}

ROLE_LABELS = {
    "pingpong": "PingPong 运营端",
    "merchant": "商户端",
    "regulator": "监管端",
    "admin": "数据安全管理端",
}


def permissions_of(role: str) -> list[str]:
    return PERMISSION_MATRIX.get(role, [])


def has_permission(role: str, permission: str | None) -> bool:
    if not permission:
        return True
    return permission in permissions_of(role)


# ---------------------------------------------------------------------------
# 认证与鉴权装饰器
# ---------------------------------------------------------------------------


def auth_required(func):
    """校验 Bearer JWT、黑名单与账号状态，并把用户写入 flask.g。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise ApiError("未提供访问令牌，请先登录", code=401)
        payload = decode_token(header[7:].strip())

        if TokenBlacklist.query.filter_by(jti=payload.get("jti", "")).first():
            raise ApiError("该访问令牌已失效（已登出或触发熔断）", code=401)

        user = User.query.filter_by(username=payload.get("sub")).first()
        if user is None:
            raise ApiError("用户不存在或已被删除", code=401)
        if user.status == "locked":
            raise ApiError("账号已被熔断锁定，请提交申诉或联系数据安全管理员", code=429)
        if user.status != "active":
            raise ApiError("账号状态异常，禁止访问", code=403)

        g.user = user
        g.jwt = payload
        g.role = payload.get("role") or user.role
        return func(*args, **kwargs)

    return wrapper


def require_permission(permission: str):
    """权限点校验（在 auth_required 之后使用）。"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if user is None:
                raise ApiError("未认证", code=401)
            if not has_permission(g.role, permission):
                raise ApiError(
                    f"权限不足：当前角色「{ROLE_LABELS.get(g.role, g.role)}」缺少权限点 {permission}",
                    code=403,
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


def current_user() -> User:
    user = getattr(g, "user", None)
    if user is None:
        raise ApiError("未认证", code=401)
    return user


def actor_name() -> str:
    user = getattr(g, "user", None)
    return user.username if user else "anonymous"


# ---------------------------------------------------------------------------
# 异常行为熔断机制
# ---------------------------------------------------------------------------


def evaluate_risk(user: User, action: str, level: str | None = None,
                  extra: dict | None = None) -> tuple[float, str, list[str]]:
    """零信任动态风险评分。

    返回 (风险分 0~1, 严重度 low/medium/high, 命中的熔断规则说明)。
    规则与文档「异常行为熔断机制」一致：
      1. 同一账号 1 小时内跨欧盟与中国同时登录
      2. 10 分钟内超过 5 次访问 P1 级数据且未发起建模任务
      3. 未通过合规校验尝试传输数据
      4. 解密次数超当日阈值
    """
    rules = Config.CIRCUIT_BREAKER
    triggered: list[str] = []
    score = 0.0

    # 规则 1：跨地区同时登录
    # 注意：登录审计记录把「登录地区」写入 AuditLog.node（与计算任务的节点字段复用同一列），
    # 审计日志表本身没有 region 列，此处必须读 node，否则会抛 AttributeError。
    window_start = now() - timedelta(minutes=rules["cross_region_login_minutes"])
    login_records = AuditLog.query.filter(
        AuditLog.actor == user.username,
        AuditLog.action == "login",
        AuditLog.ts >= window_start,
    ).all()
    regions = {getattr(item, "node", "") for item in login_records if getattr(item, "node", "")}
    if {"欧盟", "中国"} <= regions or len(regions) >= 3:
        triggered.append("同一账号短时间内跨地区登录")
        score += 0.35

    # 规则 2：短时间内高频访问 P1 级数据
    p1_start = now() - timedelta(minutes=rules["p1_access_window_minutes"])
    p1_count = AuditLog.query.filter(
        AuditLog.actor == user.username,
        AuditLog.ts >= p1_start,
        AuditLog.action.in_(["data.access", "task.create", "oblivious.query"]),
    ).count()
    if p1_count >= rules["p1_access_limit"] and (level or "").upper() == "P1":
        triggered.append(f"{rules['p1_access_window_minutes']} 分钟内访问 P1 级数据超过 {rules['p1_access_limit']} 次")
        score += 0.3

    # 规则 3：未通过合规校验仍尝试传输
    if extra and extra.get("compliance_passed") is False:
        triggered.append("未通过合规校验尝试传输数据")
        score += 0.5

    # 规则 4：当日解密次数超阈值
    day_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    decrypt_count = AuditLog.query.filter(
        AuditLog.actor == user.username,
        AuditLog.action == "crypto.decrypt",
        AuditLog.ts >= day_start,
    ).count()
    if decrypt_count >= rules["decrypt_daily_limit"]:
        triggered.append(f"当日解密次数超过阈值 {rules['decrypt_daily_limit']} 次")
        score += 0.35

    severity = "high" if score >= 0.5 else "medium" if score >= 0.3 else "low"
    return min(1.0, score), severity, triggered


def apply_circuit_breaker(user: User, rules_hit: Iterable[str], severity: str) -> CircuitBreakerEvent | None:
    """执行分级熔断：锁定账号 1~24 小时，并记录熔断事件。"""
    rules_hit = list(rules_hit)
    if not rules_hit:
        return None
    lock_hours = Config.CIRCUIT_BREAKER["lock_hours"].get(severity, 1)
    event = CircuitBreakerEvent(
        username=user.username,
        rule="；".join(rules_hit),
        severity=severity,
        detail=f"命中 {len(rules_hit)} 条异常行为规则，锁定 {lock_hours} 小时",
        lockUntil=now() + timedelta(hours=lock_hours),
        status="locked",
    )
    db.session.add(event)
    if severity == "high":
        user.status = "locked"
    db.session.commit()
    return event


def assert_circuit_ok(user: User) -> None:
    """检查是否存在未解除的熔断锁定。"""
    event = (
        CircuitBreakerEvent.query.filter_by(username=user.username, status="locked")
        .order_by(CircuitBreakerEvent.ts.desc())
        .first()
    )
    if event and event.lockUntil and event.lockUntil > now():
        raise ApiError(
            f"账号触发异常行为熔断（{event.rule}），锁定至 {event.lockUntil.strftime('%Y-%m-%d %H:%M:%S')}",
            code=429,
        )
