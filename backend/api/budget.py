# -*- coding: utf-8 -*-
"""隐私预算动态管理接口（/api/budget）。

预算额度以 ε（隐私预算）为单位：总额度是所有项目额度之和，消耗来自实际计算任务。
超阈值自动预警（默认 80%），内部调整受「不超过总预算 10%」的合规约束。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, request

from ..audit import logger as audit_logger
from ..crypto import dp
from ..extensions import db
from ..models import BudgetAdjustment, BudgetApplication, BudgetItem, BudgetTrend, next_code, now
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok, page_args, paginate

bp = Blueprint("budget", __name__, url_prefix="/api/budget")

WARNING_RATIO = 0.8
TRANSFER_LIMIT = 0.10  # 内部调整不超过总预算的 10%


def _overview_data() -> dict:
    items = BudgetItem.query.order_by(BudgetItem.id).all()
    total = sum(item.total for item in items) or 0.0
    used = sum(item.used for item in items) or 0.0
    remaining = max(0.0, total - used)

    alerts = []
    for item in items:
        ratio = item.used / item.total if item.total else 0.0
        if ratio >= 0.95:
            alerts.append(
                {
                    "level": "high",
                    "title": f"{item.project} 预算即将耗尽",
                    "content": f"已消耗 {ratio * 100:.1f}%（{item.used:.2f}/{item.total:.2f}），"
                               f"剩余 {item.total - item.used:.2f}",
                    "project": item.project,
                }
            )
        elif ratio >= WARNING_RATIO:
            alerts.append(
                {
                    "level": "medium",
                    "title": f"{item.project} 预算使用超过预警阈值",
                    "content": f"已消耗 {ratio * 100:.1f}%，建议提前申请追加额度或降低计算精度",
                    "project": item.project,
                }
            )
    if not alerts and total:
        alerts.append(
            {
                "level": "low",
                "title": "隐私预算整体充足",
                "content": f"总消耗占比 {used / total * 100:.1f}%，未触发预警阈值（{WARNING_RATIO * 100:.0f}%）",
                "project": "全部项目",
            }
        )

    return {
        "total": round(total, 4),
        "used": round(used, 4),
        "remaining": round(remaining, 4),
        "usedRatio": round(used / total, 4) if total else 0.0,
        "remainingRatio": round(remaining / total, 4) if total else 0.0,
        "items": len(items),
        "composition": [
            {"name": item.project, "value": round(item.used, 4)} for item in items if item.used > 0
        ]
        or [{"name": item.project, "value": round(item.total, 4)} for item in items],
        "alerts": alerts,
        "warningRatio": WARNING_RATIO,
        "transferLimit": TRANSFER_LIMIT,
        "unit": "ε（隐私预算）",
        "principle": "通过限制数据计算次数与精度防止原始数据反推；"
                     "εₘ = ε_total · (sₘ · cₘ) / Σ(sᵢ · cᵢ)，高敏感数据高保护、低敏感数据低消耗",
    }


@bp.get("/overview")
@auth_required
@require_permission("budget:manage")
def overview():
    """预算概览：总额度、已消耗、剩余占比、构成与预警。"""
    return ok(_overview_data())


@bp.get("/items")
@auth_required
@require_permission("budget:manage")
def items():
    """项目预算明细。"""
    rows = BudgetItem.query.order_by(BudgetItem.id).all()
    data = [item.to_dict() for item in rows]
    for item in data:
        item["level"] = item.get("level") or "P2"
    return ok(data)


@bp.get("/trend")
@auth_required
@require_permission("budget:manage")
def trend():
    """月度预算消耗趋势（柱状 + 折线）。"""
    try:
        months = max(3, min(24, int(request.args.get("months", 6))))
    except (TypeError, ValueError):
        months = 6

    rows = BudgetTrend.query.order_by(BudgetTrend.month.asc()).all()
    if rows:
        data = rows[-months:]
        return ok(
            {
                "months": [item.month for item in data],
                "used": [round(item.used, 4) for item in data],
                "remaining": [round(item.remaining, 4) for item in data],
                "usedRatio": [round(item.usedRatio, 4) for item in data],
            }
        )

    # 无历史数据时按当前总预算的消耗进度生成近 N 个月的分布（标注 source=derived）
    current = _overview_data()
    total = current["total"] or 1.0
    used = current["used"]
    labels = []
    used_series = []
    remaining_series = []
    ratio_series = []
    today = date.today()
    for offset in range(months - 1, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=offset * 30)).replace(day=1)
        labels.append(month_date.strftime("%Y-%m"))
        share = (months - offset) / months
        month_used = round(used * share, 4)
        used_series.append(month_used)
        remaining_series.append(round(max(0.0, total - month_used), 4))
        ratio_series.append(round(month_used / total, 4))
    return ok(
        {
            "months": labels,
            "used": used_series,
            "remaining": remaining_series,
            "usedRatio": ratio_series,
            "source": "derived",
        }
    )


@bp.post("/items/<int:item_id>/adjust")
@auth_required
@require_permission("budget:manage")
def adjust_item(item_id: int):
    """调整单个项目的预算额度。"""
    item = BudgetItem.query.get(item_id)
    if item is None:
        raise ApiError("预算项目不存在", code=404)
    payload = body()
    total = payload.get("total")
    if total is None:
        raise ApiError("请提供新的总额度（total）")
    total = float(total)
    if total < item.used:
        raise ApiError(f"新额度不能低于已消耗额度（{item.used:.4f}）")

    before = item.total
    item.total = total
    item.note = payload.get("reason", item.note)
    count = BudgetAdjustment.query.count() + 1
    db.session.add(
        BudgetAdjustment(
            code=next_code("ADJ", count),
            fromProject=item.project,
            toProject=item.project,
            amount=round(total - before, 4),
            operator=current_user().username,
            note=payload.get("reason", ""),
            type="adjust",
        )
    )
    db.session.commit()

    audit_logger.record_from_request(
        "budget.adjust", target=item.project, operation="修改",
        detail=f"预算额度 {before:.4f} → {total:.4f}，原因：{payload.get('reason', '')}",
    )
    return ok(item.to_dict())


@bp.post("/transfer")
@auth_required
@require_permission("budget:manage")
def transfer():
    """项目间内部调整（单次不超过总预算的 10%）。"""
    payload = body()
    from_project = payload.get("fromProject")
    to_project = payload.get("toProject")
    amount = float(payload.get("amount") or 0)
    if not from_project or not to_project:
        raise ApiError("请选择调出项目与调入项目")
    if from_project == to_project:
        raise ApiError("调出项目与调入项目不能相同")
    if amount <= 0:
        raise ApiError("调整额度必须大于 0")

    source = BudgetItem.query.filter_by(project=from_project).first()
    target = BudgetItem.query.filter_by(project=to_project).first()
    if source is None or target is None:
        raise ApiError("预算项目不存在", code=404)

    overview = _overview_data()
    limit = overview["total"] * TRANSFER_LIMIT
    if amount > limit:
        raise ApiError(f"单次内部调整不得超过总预算的 {TRANSFER_LIMIT * 100:.0f}%（上限 {limit:.4f}）")
    if amount > source.total - source.used:
        raise ApiError(f"调出项目可用额度不足（可调出 {source.total - source.used:.4f}）")

    source.total = round(source.total - amount, 6)
    target.total = round(target.total + amount, 6)

    count = BudgetAdjustment.query.count() + 1
    record = BudgetAdjustment(
        code=next_code("ADJ", count),
        fromProject=from_project,
        toProject=to_project,
        amount=round(amount, 4),
        operator=current_user().username,
        note=payload.get("note", ""),
        type="transfer",
    )
    db.session.add(record)
    db.session.commit()

    audit_logger.record_from_request(
        "budget.adjust", target=f"{from_project} → {to_project}", operation="修改",
        detail=f"内部预算调整 {amount:.4f}，原因：{payload.get('note', '')}",
    )
    return ok({"from": source.to_dict(), "to": target.to_dict(), "record": record.to_dict()})


@bp.post("/applications")
@auth_required
@require_permission("budget:manage")
def create_application():
    """新增预算申请。"""
    payload = body()
    if not payload.get("project"):
        raise ApiError("请填写申请项目名称")
    amount = float(payload.get("amount") or 0)
    if amount <= 0:
        raise ApiError("申请额度必须大于 0")

    count = BudgetApplication.query.count() + 1
    expected = payload.get("expectedAt")
    application = BudgetApplication(
        code=next_code("BAPP", count),
        project=payload["project"],
        category=payload.get("category", ""),
        amount=amount,
        reason=payload.get("reason", ""),
        status="pending",
        applicant=current_user().username,
        expectedAt=datetime.strptime(expected[:10], "%Y-%m-%d").date() if expected else None,
    )
    db.session.add(application)
    db.session.commit()

    audit_logger.record_from_request(
        "budget.apply", target=application.code, operation="创建",
        detail=f"申请预算 {amount}，项目 {application.project}",
    )
    return ok(application.to_dict(), message="预算申请已提交")


@bp.get("/applications")
@auth_required
@require_permission("budget:manage")
def list_applications():
    """预算申请列表。"""
    page, size = page_args()
    query = BudgetApplication.query
    status = request.args.get("status")
    if status and status != "all":
        query = query.filter(BudgetApplication.status == status)
    query = query.order_by(BudgetApplication.createdAt.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.post("/applications/<int:application_id>/approve")
@auth_required
@require_permission("budget:manage")
def approve_application(application_id: int):
    """审批预算申请：通过后自动增加对应项目额度（不存在则创建）。"""
    application = BudgetApplication.query.get(application_id)
    if application is None:
        raise ApiError("预算申请不存在", code=404)
    payload = body()
    approved = payload.get("approved", True)
    comment = payload.get("comment", "")

    application.status = "approved" if approved else "rejected"
    application.approver = current_user().username
    application.comment = comment

    if approved:
        item = BudgetItem.query.filter_by(project=application.project).first()
        if item is None:
            item = BudgetItem(project=application.project, category=application.category or "其他",
                              total=0.0, used=0.0, level="P2")
            db.session.add(item)
        item.total = round(item.total + application.amount, 6)

    db.session.commit()
    audit_logger.record_from_request(
        "budget.approve" if approved else "budget.reject", target=application.code, operation="修改",
        detail=f"{'通过' if approved else '驳回'}预算申请 {application.amount}：{comment}",
    )
    return ok(application.to_dict())


@bp.get("/adjustments")
@auth_required
@require_permission("budget:manage")
def adjustments():
    """预算调整记录报告。"""
    rows = BudgetAdjustment.query.order_by(BudgetAdjustment.createdAt.desc()).limit(100).all()
    return ok([item.to_dict() for item in rows])


@bp.post("/consume")
@auth_required
@require_permission("budget:manage")
def consume():
    """计算消耗预算（隐私计算引擎回调）。

    按动态分配公式计算本次任务的预算消耗：ε = 基础消耗 × (敏感度系数 × 贡献值) 归一化结果。
    """
    payload = body()
    project = payload.get("project")
    epsilon = float(payload.get("epsilon") or 1.0)
    scene = payload.get("scene", "跨境电商联合风控")
    level = str(payload.get("level", "P2")).upper()

    if epsilon <= 0:
        raise ApiError("消耗额度必须大于 0")

    item = BudgetItem.query.filter_by(project=project).first()
    if item is None:
        raise ApiError(f"预算项目不存在：{project}", code=404)

    allocation = dp.allocate_budget(
        epsilon,
        [{"name": project, "level": level, "contribution": float(payload.get("contribution", 1.0))}],
    )[0]
    cost = allocation["epsilon"]

    if cost > item.total - item.used:
        raise ApiError(
            f"隐私预算不足：{project} 剩余 {item.total - item.used:.4f}，本次需要 {cost:.4f}",
            code=5001,
        )

    item.used = round(item.used + cost, 6)
    if item.used / item.total >= WARNING_RATIO:
        db.session.add(
            BudgetTrend(
                month=now().strftime("%Y-%m"),
                used=item.used,
                remaining=max(0.0, item.total - item.used),
                usedRatio=round(item.used / item.total, 4),
                scene=scene,
            )
        )
    db.session.commit()

    audit_logger.record_from_request(
        "budget.consume", target=project, operation="修改", detail=f"消耗 ε={cost}，场景 {scene}"
    )
    return ok(
        {
            "project": item.project,
            "cost": cost,
            "used": item.used,
            "remaining": round(item.total - item.used, 6),
            "warning": item.used / item.total >= WARNING_RATIO if item.total else False,
            "allocation": allocation,
        }
    )
