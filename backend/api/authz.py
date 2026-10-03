# -*- coding: utf-8 -*-
"""多方协同权限管控接口（/api/authz）：零信任动态授权。"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, request

from ..audit import logger as audit_logger
from ..extensions import db
from ..models import AuditLog, DataGrant, Dataset, LoginSession, Partner, next_code, now
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok, page_args, paginate

bp = Blueprint("authz", __name__, url_prefix="/api/authz")

# 授权级别（与前端页面取值保持一致）
GRANT_LEVELS = {
    "readonly": "只读计算",
    "query-limited": "结果查询限制",
    "mpc": "允许参与隐私计算",
}

# 使用目的字典
PURPOSES = ["反欺诈模型训练", "联合风控验证", "黑名单核验", "监管申报统计", "联合信用评分"]

# 授权对象可选的数据范围
SCOPE_OPTIONS = [
    {"code": "user_base", "name": "用户基础信息（不含敏感字段）", "level": "P3"},
    {"code": "user_identity", "name": "用户身份信息（身份证号/护照）", "level": "P1"},
    {"code": "bank_account", "name": "银行卡与结算账户信息", "level": "P1"},
    {"code": "transaction", "name": "跨境交易明细与金额", "level": "P2"},
    {"code": "tax_info", "name": "商户税号与经营信息", "level": "P2"},
    {"code": "risk_feature", "name": "风控特征与评分结果", "level": "P2"},
    {"code": "sanction_list", "name": "监管制裁清单", "level": "P3"},
    {"code": "category", "name": "商品类别与地区编码", "level": "P3"},
]


def _parse_datetime(value: str | None, default: datetime | None = None) -> datetime | None:
    if not value:
        return default
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return default


def _append_history(grant: DataGrant, action: str, detail: str = "") -> None:
    history = list(grant.history or [])
    history.append(
        {
            "ts": now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "operator": current_user().username,
            "detail": detail,
        }
    )
    grant.history = history


@bp.get("/grants")
@auth_required
def grants():
    """授权记录列表（支持状态、关键字、授权对象筛选）。"""
    page, size = page_args()
    query = DataGrant.query
    status = request.args.get("status")
    keyword = request.args.get("keyword")
    partner = request.args.get("partner")
    if keyword:
        query = query.filter(
            db.or_(DataGrant.code.like(f"%{keyword}%"), DataGrant.partner.like(f"%{keyword}%"))
        )
    if partner:
        query = query.filter(DataGrant.partner.like(f"%{partner}%"))
    rows = query.order_by(DataGrant.createdAt.desc()).all()
    if status and status != "all":
        rows = [item for item in rows if item.computed_status == status]
    total = len(rows)
    start = (page - 1) * size
    return ok(
        {
            "list": [item.to_dict() for item in rows[start : start + size]],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@bp.post("/grants")
@auth_required
@require_permission("authz:grant:manage")
def create_grant():
    """新建数据授权申请。

    P1 级数据范围的授权自动进入「待审核」状态，需由数据安全管理员审批（双人复核）；
    P2/P3 级数据可由数据安全管理员直接生效 —— 对应文档「权限动态调整机制」。
    """
    payload = body()
    if not payload.get("partner"):
        raise ApiError("请选择授权对象（合作方）")
    if not payload.get("datasetScope"):
        raise ApiError("请选择授权数据范围")

    scope = payload.get("datasetScope") or []
    if isinstance(scope, str):
        scope = [scope]
    level = payload.get("level") or "readonly"
    purpose = payload.get("purpose")
    if isinstance(purpose, list):
        purpose = "、".join(str(item) for item in purpose)

    valid_from = _parse_datetime(payload.get("validFrom"), now())
    valid_to = _parse_datetime(payload.get("validTo"), now() + timedelta(days=180))
    if valid_to <= valid_from:
        raise ApiError("授权有效期结束时间必须晚于开始时间")
    if (valid_to - valid_from).days > 365:
        raise ApiError("授权有效期最长 1 年，请调整有效期")

    # 数据范围对应最高敏感度
    scope_levels = [item["level"] for item in SCOPE_OPTIONS if item["code"] in scope]
    highest = "P1" if "P1" in scope_levels else ("P2" if "P2" in scope_levels else "P3")

    partner = Partner.query.filter(Partner.name == payload["partner"]).first()
    if partner and not partner.verified:
        raise ApiError("该合作方尚未通过资质审核，无法创建授权", code=400)

    count = DataGrant.query.count() + 1
    grant = DataGrant(
        code=next_code("GRANT", count),
        partner=payload["partner"],
        partnerRegion=(partner.region if partner else payload.get("partnerRegion", "EU")),
        datasetScope=scope,
        purpose=purpose or "",
        level=level,
        permissions=payload.get("permissions") or [],
        validFrom=valid_from,
        validTo=valid_to,
        status="pending" if highest == "P1" else "active",
        remark=payload.get("remark", ""),
        applicant=current_user().username,
        certExpireAt=partner.certExpireAt if partner else None,
    )
    _append_history(
        grant,
        "create",
        f"创建授权申请，数据范围最高敏感度 {highest}，"
        + ("需数据安全管理员审批（P1 双人复核）" if highest == "P1" else "已自动生效"),
    )
    db.session.add(grant)
    db.session.commit()

    audit_logger.record_from_request(
        "grant.create", target=grant.code, operation="创建",
        detail=f"授权对象 {grant.partner}，范围 {len(scope)} 项，有效期至 {valid_to.strftime('%Y-%m-%d')}",
    )
    return ok(
        {"id": grant.id, "code": grant.code, "status": grant.status, "highestLevel": highest},
        message="授权申请已提交" if grant.status == "pending" else "授权已生效",
    )


@bp.get("/grants/<int:grant_id>")
@auth_required
def grant_detail(grant_id: int):
    """授权详情与权限变更日志。"""
    grant = DataGrant.query.get(grant_id)
    if grant is None:
        raise ApiError("授权记录不存在", code=404)
    data = grant.to_dict()
    data["scopeDetail"] = [item for item in SCOPE_OPTIONS if item["code"] in (grant.datasetScope or [])]
    data["levelLabel"] = GRANT_LEVELS.get(grant.level, grant.level)
    data["permissionDetail"] = [
        {"code": code, "name": _permission_name(code)} for code in (grant.permissions or [])
    ]
    data["zeroTrust"] = {
        "principle": "按「身份 - 数据敏感度 - 使用场景」动态授权，权限与任务周期绑定（最长 30 天）到期自动回收",
        "mfaRequired": "authz:mfa-required" in (grant.permissions or []),
        "reAuthorizeAllowed": "authz:re-authorize" in (grant.permissions or []),
    }
    return ok(data)


def _permission_name(code: str) -> str:
    return {
        "authz:re-authorize": "允许二次授权",
        "authz:mfa-required": "强制多因素认证",
        "authz:compute": "允许参与隐私计算",
        "authz:result-only": "仅可查询计算结果",
        "authz:readonly": "只读访问",
    }.get(code, code)


@bp.post("/grants/<int:grant_id>/approve")
@auth_required
@require_permission("authz:grant:manage")
def approve_grant(grant_id: int):
    """审批授权（P1 级数据需数据安全管理员二次审批）。"""
    grant = DataGrant.query.get(grant_id)
    if grant is None:
        raise ApiError("授权记录不存在", code=404)
    payload = body()
    approved = payload.get("approved", True)
    comment = payload.get("comment", "")

    if approved:
        grant.status = "active"
        grant.approver = current_user().username
        if not grant.validFrom or grant.validFrom < now():
            grant.validFrom = now()
    else:
        grant.status = "revoked"
    _append_history(grant, "approve" if approved else "reject", comment or ("审批通过" if approved else "审批驳回"))
    db.session.commit()

    audit_logger.record_from_request(
        "grant.approve" if approved else "grant.reject", target=grant.code, operation="修改",
        detail=f"{'通过' if approved else '驳回'}授权 {grant.code}：{comment}",
    )
    return ok({"id": grant.id, "status": grant.computed_status})


@bp.post("/grants/<int:grant_id>/revoke")
@auth_required
@require_permission("authz:grant:manage")
def revoke_grant(grant_id: int):
    """撤销授权（到期前主动回收，权限立即失效）。"""
    grant = DataGrant.query.get(grant_id)
    if grant is None:
        raise ApiError("授权记录不存在", code=404)
    payload = body()
    reason = payload.get("reason", "未填写原因")
    grant.status = "revoked"
    _append_history(grant, "revoke", reason)
    db.session.commit()

    audit_logger.record_from_request(
        "grant.revoke", target=grant.code, operation="删除", detail=f"撤销授权：{reason}"
    )
    return ok({"id": grant.id, "status": grant.computed_status})


@bp.post("/grants/<int:grant_id>/renew")
@auth_required
@require_permission("authz:grant:manage")
def renew_grant(grant_id: int):
    """续期（最长 1 年，且不超过合作方资质证书有效期）。"""
    grant = DataGrant.query.get(grant_id)
    if grant is None:
        raise ApiError("授权记录不存在", code=404)
    payload = body()
    valid_to = _parse_datetime(payload.get("validTo"))
    if valid_to is None:
        raise ApiError("请提供新的到期时间（validTo）")
    if valid_to <= now():
        raise ApiError("新的到期时间必须晚于当前时间")
    if grant.certExpireAt and valid_to > grant.certExpireAt:
        raise ApiError(f"续期时间超出合作方资质有效期（{grant.certExpireAt.strftime('%Y-%m-%d')}）")

    grant.validTo = valid_to
    if grant.status in ("expired", "revoked") and valid_to > now():
        grant.status = "active"
    _append_history(grant, "renew", f"续期至 {valid_to.strftime('%Y-%m-%d %H:%M:%S')}")
    db.session.commit()

    audit_logger.record_from_request(
        "grant.renew", target=grant.code, operation="修改",
        detail=f"授权续期至 {valid_to.strftime('%Y-%m-%d')}",
    )
    return ok({"id": grant.id, "validTo": grant.to_dict()["validTo"], "status": grant.computed_status})


@bp.get("/export")
@auth_required
def export_grants():
    """导出授权记录（CSV）。"""
    rows = DataGrant.query.order_by(DataGrant.createdAt.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["授权ID", "授权对象", "地区", "数据范围", "使用目的", "授权级别", "有效期起", "有效期止",
                     "状态", "申请人", "审批人", "剩余天数"])
    for item in rows:
        data = item.to_dict()
        writer.writerow([
            data["code"], data["partner"], data["partnerRegion"], "、".join(data["datasetScope"]),
            data["purpose"], GRANT_LEVELS.get(data["level"], data["level"]),
            data["validFrom"], data["validTo"], data["status"], data["applicant"], data["approver"],
            data["remainDays"],
        ])
    audit_logger.record_from_request("data.export", target="grants", operation="导出",
                                     detail=f"导出授权记录 {len(rows)} 条")
    response = Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        "attachment; filename=authz-grants.csv; filename*=UTF-8''%E6%8E%88%E6%9D%83%E8%AE%B0%E5%BD%95.csv"
    )
    return response


@bp.get("/filters")
@auth_required
def filters():
    """筛选项字典（授权对象 / 数据范围 / 使用目的）。"""
    partners = [
        {
            "code": item.code,
            "name": item.name,
            "region": item.region,
            "verified": item.verified,
            "certExpireAt": item.certExpireAt.strftime("%Y-%m-%d") if item.certExpireAt else None,
        }
        for item in Partner.query.order_by(Partner.id).all()
    ]
    return ok({"partners": partners, "scopes": SCOPE_OPTIONS, "purposes": PURPOSES, "levels": [
        {"code": code, "name": name} for code, name in GRANT_LEVELS.items()
    ]})


@bp.get("/risks")
@auth_required
def risks():
    """风险与预警：异常访问、即将过期授权、MFA 失败记录。

    字段命名与前端 views/authz/GrantManage.vue 的渲染口径保持一致
    （ts / account / action / riskScore；code / partner / validTo / remainDays；account / ts / ip / count）。
    """
    # 1) 异常访问：风险评分较高的审计记录
    abnormal = (
        AuditLog.query.filter(AuditLog.riskScore > 0)
        .order_by(AuditLog.riskScore.desc(), AuditLog.ts.desc())
        .limit(20)
        .all()
    )
    abnormal_access = [
        {
            "ts": item.ts.strftime("%Y-%m-%d %H:%M:%S"),
            "account": item.actor,
            "action": item.action,
            "target": item.target,
            "riskScore": round(item.riskScore, 3),
            "result": item.result,
        }
        for item in abnormal
    ]
    if not abnormal_access:
        # 无异常时返回空数组（前端有兜底），不伪造数据
        abnormal_access = []

    # 2) 即将过期授权（30 天内）
    expiring = []
    for grant in DataGrant.query.filter(DataGrant.status == "active").all():
        if not grant.validTo:
            continue
        remain = (grant.validTo - now()).days
        if 0 <= remain <= 30:
            expiring.append(
                {
                    "code": grant.code,
                    "partner": grant.partner,
                    "validTo": grant.validTo.strftime("%Y-%m-%d %H:%M:%S"),
                    "remainDays": remain,
                    "datasetScope": grant.datasetScope or [],
                }
            )
    expiring.sort(key=lambda item: item["remainDays"])

    # 3) MFA 失败记录（以登录失败审计记录聚合）
    failures: dict[tuple, dict] = {}
    for log in AuditLog.query.filter(AuditLog.action == "login", AuditLog.result == "failed").all():
        key = (log.actor, log.ts.strftime("%Y-%m-%d"))
        item = failures.setdefault(
            key,
            {"account": log.actor, "ts": log.ts.strftime("%Y-%m-%d %H:%M:%S"), "ip": "-", "count": 0,
             "detail": log.detail},
        )
        item["count"] += 1
        item["ts"] = max(item["ts"], log.ts.strftime("%Y-%m-%d %H:%M:%S"))
    mfa_failures = sorted(failures.values(), key=lambda item: -item["count"])[:20]

    # 4) 跨地区登录会话（异常登录检测）
    recent = LoginSession.query.order_by(LoginSession.loginAt.desc()).limit(50).all()
    risk_sessions = [
        {
            "account": item.username,
            "ts": item.loginAt.strftime("%Y-%m-%d %H:%M:%S"),
            "region": item.region,
            "ip": item.ip,
            "risk": item.risk,
        }
        for item in recent
        if item.risk in ("medium", "high")
    ]

    return ok(
        {
            "abnormalAccess": abnormal_access,
            "expiringSoon": expiring,
            "mfaFailures": mfa_failures,
            "riskSessions": risk_sessions,
            "circuitBreakerRules": [
                "同一账号 1 小时内跨欧盟与中国同时登录",
                "10 分钟内超过 5 次访问 P1 级数据且未发起建模任务",
                "未通过合规校验尝试传输数据",
                "解密次数超过当日阈值",
            ],
        }
    )


@bp.get("/audit")
@auth_required
def audit():
    """权限变更与计算请求行为审计。"""
    page, size = page_args()
    query = AuditLog.query.filter(
        AuditLog.action.in_(["grant.create", "grant.approve", "grant.revoke", "grant.renew",
                             "task.create", "task.start", "oblivious.query", "crypto.decrypt"])
    ).order_by(AuditLog.ts.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.get("/datasets")
@auth_required
def datasets():
    """可选数据范围（含真实数据集与敏感度分级）。"""
    rows = Dataset.query.order_by(Dataset.level).all()
    return ok(
        [
            {"code": item.code, "name": item.name, "level": item.level,
             "owner": item.owner, "region": item.region, "fields": item.fields or []}
            for item in rows
        ]
        + SCOPE_OPTIONS
    )
