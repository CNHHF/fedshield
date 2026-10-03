# -*- coding: utf-8 -*-
"""全球支付一体化智能支撑接口（/api/ops）。

对应赛题 A16 的五大建设范围，是本平台面向「AI 驱动风控合规智能大脑」的核心业务接口：

| 赛题建设范围 | 接口 |
| --- | --- |
| ① 支付智能处理能力 | `/payment/*`：通道池、路由预演、批量处理、订单跟踪、链路指标 |
| ② 智能风控能力 | `/monitoring/*`：异常检测规则、实时预警、自动处置、风险汇总 |
| ③ 智能合规审核能力 | `/review/*`：KYC/交易审核、AI 初审、人工复核协同 |
| ④ AI 审核一致性管理 | `/review/consistency`、`/review/optimize`、`/review/apply`、`/review/optimizations` |
| ⑤ 运营决策支撑 | `/decisions`：指标监控、策略评估、决策建议输出 |
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from flask import Blueprint, request

from ..audit import logger as audit_logger
from ..engine import monitoring, payment, review
from ..extensions import db
from ..models import (
    Merchant,
    MonitoringAlert,
    OptimizationRecord,
    PaymentChannel,
    PaymentOrder,
    ReviewRecord,
    Transaction,
    next_code,
    now,
)
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok, page_args, paginate

bp = Blueprint("ops", __name__, url_prefix="/api/ops")

# 当前审核策略（进程内保存；生产环境应落库并版本化）
_POLICY = review.default_policy()


def _channels() -> list[dict]:
    """取通道池：优先用数据库配置，缺失时用引擎内置默认值并落库。"""
    rows = PaymentChannel.query.order_by(PaymentChannel.id).all()
    if not rows:
        for item in payment.DEFAULT_CHANNELS:
            db.session.add(PaymentChannel(**item))
        db.session.commit()
        rows = PaymentChannel.query.order_by(PaymentChannel.id).all()
    return [item.to_dict() for item in rows]


def _recent_hour(order: dict) -> int:
    return int(order.get("hour") or datetime.now().hour)


# ---------------------------------------------------------------------------
# ① 支付智能处理
# ---------------------------------------------------------------------------


@bp.get("/payment/channels")
@auth_required
def payment_channels():
    """通道池：费率、成功率、时延、限额、健康状态与合规说明。"""
    channels = _channels()
    return ok(
        {
            "channels": channels,
            "restricted": sorted(payment.RESTRICTED_DESTINATIONS),
            "retryPolicy": {"maxRetry": payment.MAX_RETRY, "backoffMs": payment.RETRY_BACKOFF_MS},
            "weights": payment.ROUTE_WEIGHTS,
        }
    )


@bp.post("/payment/route-preview")
@auth_required
def payment_route_preview():
    """智能路由预演：对一笔拟发起的交易展示所有候选通道打分与排除原因。"""
    payload = body()
    order = {
        "amount": float(payload.get("amount") or 100_000),
        "currency": payload.get("currency") or "USD",
        "destRegion": payload.get("destRegion") or "EU",
        "merchantName": payload.get("merchantName") or "演示商户",
    }
    risk_level = payload.get("riskLevel") or "low"
    result = payment.route_preview(order, _channels(), risk_level)
    result["order"] = order
    result["riskLevel"] = risk_level
    return ok(result)


@bp.post("/payment/process")
@auth_required
@require_permission("engine:task:manage")
def payment_process():
    """批量处理支付订单：接入 → 风控 → 智能路由 → 处理 → 重试 → 补偿，全链路落库。"""
    payload = body()
    count = max(1, min(50, int(payload.get("count") or 12)))
    rng = random.Random(payload.get("seed") or 2026)
    channels = _channels()
    merchants = Merchant.query.limit(80).all()
    if not merchants:
        raise ApiError("没有可用商户数据，请先初始化演示数据（python run.py --seed）", code=400)

    # 故障演练：注入通道故障概率，用于演示「失败重试 + 自动补偿」能力
    inject_failure_rate = float(payload.get("injectFailureRate") or 0.0)
    inject_failure_rate = max(0.0, min(0.6, inject_failure_rate))

    destinations = ["EU", "US", "SEA", "ME", "AF", "CN"]
    currencies = ["USD", "EUR", "CNY", "SGD"]
    created: list[dict] = []
    start_index = PaymentOrder.query.count()

    for index in range(count):
        merchant = rng.choice(merchants)
        order = {
            "code": f"PAY-{datetime.now().strftime('%Y%m%d')}-{start_index + index + 1:04d}",
            "merchantCode": merchant.code,
            "merchantName": merchant.name,
            "region": merchant.region,
            "destRegion": rng.choice(destinations),
            "amount": round(rng.lognormvariate(11.2, 1.1), 2),
            "currency": rng.choice(currencies),
            "hour": rng.randint(0, 23),
        }
        # 风险分：复用商户风险评分 + 随机扰动，构成风控前置输入
        risk_score = round(min(0.99, max(0.01, merchant.riskScore + rng.uniform(-0.15, 0.25))), 4)
        risk_level = "high" if risk_score >= 0.7 else ("medium" if risk_score >= 0.4 else "low")

        result = payment.process_order(order, channels, risk_score, risk_level, rng,
                                       inject_failure_rate=inject_failure_rate)
        record = PaymentOrder(
            code=order["code"],
            merchantCode=order["merchantCode"],
            merchantName=order["merchantName"],
            region=order["region"],
            destRegion=order["destRegion"],
            amount=order["amount"],
            currency=order["currency"],
            channel=result["channel"],
            channelName=result["channelName"],
            status=result["status"],
            riskScore=risk_score,
            riskLevel=risk_level,
            routeScore=result["routeScore"],
            attempts=result["attempts"],
            failureReason=result["failureReason"],
            compensated=result["compensated"],
            events=result["events"],
            durationMs=result["durationMs"],
            finishedAt=now(),
        )
        db.session.add(record)
        created.append(record.to_dict())

    db.session.commit()
    audit_logger.record_from_request(
        "payment.process", target=f"{count} 笔订单", operation="创建",
        detail=f"批量支付处理完成：成功 {len([i for i in created if i['status'] in ('success','retrying')])} 笔，"
               f"拦截 {len([i for i in created if i['status'] == 'blocked'])} 笔",
    )
    return ok({"orders": created, "summary": payment.summarize(created)}, message="支付处理完成")


@bp.get("/payment/orders")
@auth_required
def payment_orders():
    """支付订单列表（支持状态、通道、风险等级、关键字筛选）。"""
    page, size = page_args()
    query = PaymentOrder.query
    status = request.args.get("status")
    channel = request.args.get("channel")
    risk_level = request.args.get("riskLevel")
    keyword = request.args.get("keyword")
    if status and status != "all":
        query = query.filter(PaymentOrder.status == status)
    if channel and channel != "all":
        query = query.filter(PaymentOrder.channel == channel)
    if risk_level and risk_level != "all":
        query = query.filter(PaymentOrder.riskLevel == risk_level)
    if keyword:
        query = query.filter(
            db.or_(PaymentOrder.code.like(f"%{keyword}%"), PaymentOrder.merchantName.like(f"%{keyword}%"))
        )
    query = query.order_by(PaymentOrder.createdAt.desc(), PaymentOrder.id.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.get("/payment/orders/<order_code>")
@auth_required
def payment_order_detail(order_code: str):
    """订单详情：全链路事件（状态跟踪轨迹）。"""
    order = PaymentOrder.query.filter_by(code=order_code).first()
    if order is None:
        raise ApiError(f"订单不存在：{order_code}", code=404)
    data = order.to_dict()
    data["chain"] = [
        {"stage": "接入", "label": "交易接入"},
        {"stage": "风控", "label": "AI 风控前置"},
        {"stage": "路由", "label": "智能路由"},
        {"stage": "处理", "label": "通道处理"},
        {"stage": "重试", "label": "失败重试"},
        {"stage": "补偿", "label": "自动补偿"},
    ]
    return ok(data)


@bp.get("/payment/summary")
@auth_required
def payment_summary():
    """支付链路指标：成功率、平均耗时、路由分布、重试率、补偿率、拦截率。"""
    rows = PaymentOrder.query.order_by(PaymentOrder.createdAt.desc()).limit(500).all()
    orders = [item.to_dict() for item in rows]
    summary = payment.summarize(orders)
    summary["recent"] = orders[:10]
    if not orders:
        summary["note"] = "尚无支付订单，可点击「批量处理」生成演示数据"
    return ok(summary)


# ---------------------------------------------------------------------------
# ② 智能风控与异常监测
# ---------------------------------------------------------------------------


@bp.get("/monitoring/rules")
@auth_required
def monitoring_rules():
    """异常检测规则与统一处置口径。"""
    return ok({"rules": monitoring.rules_meta(), "actions": monitoring.ACTIONS})


@bp.post("/monitoring/detect")
@auth_required
@require_permission("engine:task:manage")
def monitoring_detect():
    """执行异常行为检测：基于交易数据生成预警并落地自动处置结果。"""
    payload = body()
    limit = max(20, min(2000, int(payload.get("limit") or 600)))
    rows = Transaction.query.order_by(Transaction.occurredAt.desc()).limit(limit).all()
    if not rows:
        raise ApiError("没有交易数据可供检测，请先初始化演示数据", code=400)

    merchants = {item.code: {"merchantAge": 12} for item in Merchant.query.all()}
    transactions = [
        {
            "code": item.code,
            "merchantCode": item.merchantCode,
            "merchantName": item.merchantCode,
            "region": item.region,
            "destRegion": item.destRegion,
            "amount": item.amount,
            "category": item.category,
            "counterparties": item.counterparties,
            # 目的地风险来自交易自身的风险标签（而非硬编码地区清单），
            # 保证规则可解释、不与业务数据脱节
            "destRisk": {"high": 0.85, "medium": 0.55, "low": 0.2}.get(item.riskLevel, 0.2),
            "riskLevel": item.riskLevel,
            "hour": item.occurredAt.hour if item.occurredAt else 12,
        }
        for item in rows
    ]

    detected = monitoring.detect(transactions, merchants)
    # 落库：先清空旧的演示预警，避免重复堆积（保留全部检测结果，便于统计处置动作分布）
    MonitoringAlert.query.delete()
    for index, item in enumerate(detected[:200], 1):
        db.session.add(
            MonitoringAlert(
                code=next_code("MON", index),
                ruleCode=item["ruleCode"],
                ruleName=item["ruleName"],
                targetType=item["targetType"],
                targetId=item["targetId"],
                targetName=item["targetName"],
                amount=item.get("amount", 0.0),
                riskLevel=item["riskLevel"],
                riskScore=item["riskScore"],
                evidence=item["evidence"],
                action=item["action"],
                actionLabel=item["actionLabel"],
                status=item["status"],
                handledAt=now() if item["status"] == "handled" else None,
                detail=item["detail"],
            )
        )
    db.session.commit()

    summary = monitoring.summarize_alerts(detected)
    audit_logger.record_from_request(
        "monitoring.detect", target="异常行为检测", operation="查询",
        detail=f"检测 {len(transactions)} 笔交易，生成预警 {len(detected)} 条（高危 {summary.get('high', 0)} 条）",
    )
    return ok({"summary": summary, "alerts": detected[:120], "scanned": len(transactions)}, message="异常检测完成")


@bp.get("/monitoring/alerts")
@auth_required
def monitoring_alerts():
    """实时预警列表（可按风险等级、处置动作、状态筛选）。"""
    page, size = page_args()
    query = MonitoringAlert.query
    risk_level = request.args.get("riskLevel")
    action = request.args.get("action")
    status = request.args.get("status")
    if risk_level and risk_level != "all":
        query = query.filter(MonitoringAlert.riskLevel == risk_level)
    if action and action != "all":
        query = query.filter(MonitoringAlert.action == action)
    if status and status != "all":
        query = query.filter(MonitoringAlert.status == status)
    query = query.order_by(MonitoringAlert.riskScore.desc(), MonitoringAlert.id.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.post("/monitoring/alerts/<int:alert_id>/handle")
@auth_required
@require_permission("engine:task:manage")
def monitoring_handle(alert_id: int):
    """人工确认处置结果（自动处置 + 人工确认闭环）。"""
    alert = MonitoringAlert.query.get(alert_id)
    if alert is None:
        raise ApiError("预警不存在", code=404)
    payload = body()
    alert.status = payload.get("status") or "confirmed"
    if payload.get("action"):
        alert.action = payload["action"]
        alert.actionLabel = dict((item["code"], item["label"]) for item in monitoring.ACTIONS).get(
            payload["action"], payload["action"]
        )
    alert.handledAt = now()
    db.session.commit()
    audit_logger.record_from_request(
        "monitoring.handle", target=alert.code, operation="修改",
        detail=f"预警处置确认：{alert.ruleName} → {alert.actionLabel}",
    )
    return ok(alert.to_dict(), message="处置结果已确认")


@bp.get("/monitoring/summary")
@auth_required
def monitoring_summary():
    """风控汇总：预警分布、处置动作分布、自动化处置率、涉险金额。"""
    rows = [item.to_dict() for item in MonitoringAlert.query.all()]
    summary = monitoring.summarize_alerts(rows)
    summary["accountRisk"] = [
        {
            "merchantCode": code,
            "alerts": len(items),
            "maxScore": round(max(item["riskScore"] for item in items), 4),
            "amount": round(sum(item["amount"] for item in items), 2),
        }
        for code, items in _group_by_merchant(rows).items()
    ][:10]
    return ok(summary)


def _group_by_merchant(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for item in rows:
        grouped.setdefault(item.get("targetId") or "-", []).append(item)
    return grouped


# ---------------------------------------------------------------------------
# ③④ 审核协同与一致性管理
# ---------------------------------------------------------------------------


@bp.post("/review/batch")
@auth_required
@require_permission("engine:task:manage")
def review_batch():
    """跑一批审核：AI 初审 → 人工复核 → 差异标记，落库形成一致性评估数据。"""
    global _POLICY
    payload = body()
    count = max(4, min(60, int(payload.get("count") or 20)))
    rng = random.Random(payload.get("seed") or 20260718)
    # 批次号按「已有批次数 + 1」生成，避免与历史批次冲突
    existing_batches = int(
        db.session.query(db.func.count(db.func.distinct(ReviewRecord.batchCode))).scalar() or 0
    )
    batch_code = next_code("RBAT", existing_batches + 1)

    sources = Transaction.query.order_by(db.func.random()).limit(count).all()
    if not sources:
        raise ApiError("没有可审核的交易数据，请先初始化演示数据", code=400)

    records: list[dict] = []
    for item in sources:
        raw = {
            "code": item.code,
            "name": item.merchantCode,
            "amount": item.amount,
            "destRegion": item.destRegion,
            "merchantAge": rng.randint(1, 60),
            "identityMatch": rng.random() > 0.12,
            "nightRatio": round(rng.random(), 2),
            "sanctionHit": rng.random() < 0.05,
            "historyDeclines": rng.randint(0, 4),
            "velocity1h": rng.randint(1, 8),
        }
        ai_result = review.ai_review(raw, _POLICY, rng)
        human_result = review.human_review(raw, ai_result, current_user().username, rng)

        agreed = ai_result["aiDecision"] == human_result["humanDecision"]
        if agreed:
            diff_type = "none"
        elif ai_result["aiDecision"] == review.AI_APPROVE and human_result["humanDecision"] == review.AI_REJECT:
            diff_type = "false_negative"
        elif ai_result["aiDecision"] == review.AI_REJECT and human_result["humanDecision"] == review.AI_APPROVE:
            diff_type = "false_positive"
        else:
            diff_type = "both_manual"
        severity = "high" if diff_type == "false_negative" else ("medium" if diff_type == "false_positive" else "low")

        record = ReviewRecord(
            code=f"{batch_code}-{len(records) + 1:03d}",
            batchCode=batch_code,
            targetType="payment",
            targetId=raw["code"],
            targetName=raw["name"],
            amount=raw["amount"],
            riskLevel=ai_result["riskLevel"],
            features=raw,
            aiDecision=ai_result["aiDecision"],
            aiConfidence=ai_result["aiConfidence"],
            aiScore=ai_result["aiScore"],
            aiReasons=ai_result["reasons"],
            aiLatencyMs=ai_result["aiLatencyMs"],
            humanDecision=human_result["humanDecision"],
            humanReviewer=human_result["humanReviewer"],
            humanComment=human_result["humanComment"],
            humanLatencyMs=human_result["humanLatencyMs"],
            reviewedAt=now(),
            agreed=agreed,
            diffType=diff_type,
            diffSeverity=severity if not agreed else "",
        )
        db.session.add(record)
        records.append({**record.to_dict(), "raw": raw})

    db.session.commit()
    metrics = review.evaluate_consistency(records)
    audit_logger.record_from_request(
        "review.batch", target=batch_code, operation="创建",
        detail=f"AI 初审 {len(records)} 笔，人工复核 {len(records)} 笔，一致率 {metrics['agreementRate'] * 100:.1f}%",
    )
    return ok({"batchCode": batch_code, "count": len(records), "metrics": metrics}, message="审核批次已完成")


@bp.get("/review/records")
@auth_required
def review_records():
    """审核记录列表（可按批次、是否一致、分歧类型、风险等级筛选）。"""
    page, size = page_args()
    query = ReviewRecord.query
    batch = request.args.get("batchCode")
    agreed = request.args.get("agreed")
    diff_type = request.args.get("diffType")
    risk_level = request.args.get("riskLevel")
    if batch and batch != "all":
        query = query.filter(ReviewRecord.batchCode == batch)
    if agreed in ("true", "false"):
        query = query.filter(ReviewRecord.agreed.is_(agreed == "true"))
    if diff_type and diff_type != "all":
        query = query.filter(ReviewRecord.diffType == diff_type)
    if risk_level and risk_level != "all":
        query = query.filter(ReviewRecord.riskLevel == risk_level)
    query = query.order_by(ReviewRecord.id.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.get("/review/batches")
@auth_required
def review_batches():
    """审核批次列表（用于按批次查看一致性评估结果）。"""
    rows = (
        db.session.query(ReviewRecord.batchCode, db.func.count(ReviewRecord.id))
        .group_by(ReviewRecord.batchCode)
        .order_by(db.func.max(ReviewRecord.id).desc())
        .limit(20)
        .all()
    )
    return ok([{"batchCode": code, "count": int(count)} for code, count in rows if code])


def _load_records(batch_code: str | None) -> list[dict]:
    """载入审核记录；`raw` 使用入库时保存的原始特征，保证策略复盘可复现。"""
    query = ReviewRecord.query
    if batch_code and batch_code != "all":
        query = query.filter(ReviewRecord.batchCode == batch_code)
    rows = query.order_by(ReviewRecord.id.asc()).all()
    records = []
    for item in rows:
        features = item.features or {}
        records.append(
            {
                **item.to_dict(),
                "raw": features
                or {
                    "code": item.targetId,
                    "name": item.targetName,
                    "amount": item.amount,
                    "destRegion": "EU",
                    "merchantAge": 12,
                    "identityMatch": True,
                    "nightRatio": 0.2,
                    "sanctionHit": False,
                    "historyDeclines": 0,
                    "velocity1h": 1,
                },
            }
        )
    return records


@bp.get("/review/consistency")
@auth_required
def review_consistency():
    """一致性评估：一致率、Kappa、混淆矩阵、分歧类型、自动化率、效率对比。"""
    batch = request.args.get("batchCode")
    records = _load_records(batch)
    metrics = review.evaluate_consistency(records)
    metrics["batchCode"] = batch or "all"
    metrics["policy"] = _POLICY
    metrics["diffSamples"] = [item for item in records if not item["agreed"]][:10]
    return ok(metrics)


@bp.get("/review/policy")
@auth_required
def review_policy():
    """当前审核策略（统一审核标准）。"""
    return ok({"policy": _POLICY, "standards": {
        "decisionLabels": review.DECISION_LABELS,
        "riskTags": review.RISK_TAGS,
    }})


@bp.post("/review/optimize")
@auth_required
@require_permission("engine:task:manage")
def review_optimize():
    """差异回流：分析分歧样本并生成策略优化建议（含优化前后指标对比）。"""
    payload = body()
    batch = payload.get("batchCode")
    records = _load_records(batch)
    if not records:
        raise ApiError("没有审核记录可供分析，请先执行审核批次", code=400)

    metrics = review.evaluate_consistency(records)
    suggestion = review.suggest_optimization(metrics, records, _POLICY)

    record = OptimizationRecord(
        code=next_code("OPT", OptimizationRecord.query.count() + 1),
        batchCode=batch or "all",
        suggestion=suggestion["suggestion"],
        beforeConfig=suggestion["beforeConfig"],
        afterConfig=suggestion["afterConfig"],
        beforeMetrics=suggestion["beforeMetrics"],
        afterMetrics=suggestion["afterMetrics"],
        applied=False,
    )
    db.session.add(record)
    db.session.commit()

    audit_logger.record_from_request(
        "review.optimize", target=record.code, operation="创建",
        detail=f"生成策略优化建议：{suggestion['suggestion'][:120]}",
    )
    return ok({**suggestion, "recordCode": record.code}, message="优化建议已生成")


@bp.post("/review/apply")
@auth_required
@require_permission("engine:task:manage")
def review_apply():
    """应用优化建议：更新审核策略，形成「差异回流 → 持续优化」闭环。"""
    global _POLICY
    payload = body()
    record = None
    if payload.get("recordCode"):
        record = OptimizationRecord.query.filter_by(code=payload["recordCode"]).first()
    if record is None:
        record = OptimizationRecord.query.order_by(OptimizationRecord.id.desc()).first()
    if record is None:
        raise ApiError("没有可应用的优化建议，请先生成优化建议", code=400)

    _POLICY = dict(record.afterConfig or _POLICY)
    record.applied = True
    record.appliedBy = current_user().username
    db.session.commit()

    audit_logger.record_from_request(
        "review.apply", target=record.code, operation="修改",
        detail=f"应用策略优化：通过阈值 {_POLICY.get('approveThreshold')}、"
               f"拒绝阈值 {_POLICY.get('rejectThreshold')}、置信度门槛 {_POLICY.get('confidenceFloor')}",
    )
    return ok(
        {"policy": _POLICY, "record": record.to_dict()},
        message="优化策略已应用（后续审核批次将使用新策略）",
    )


@bp.get("/review/optimizations")
@auth_required
def review_optimizations():
    """策略优化记录（差异回流与持续优化的证据链）。"""
    rows = OptimizationRecord.query.order_by(OptimizationRecord.id.desc()).limit(30).all()
    return ok([item.to_dict() for item in rows])


# ---------------------------------------------------------------------------
# ⑤ 运营决策支撑
# ---------------------------------------------------------------------------


@bp.get("/decisions")
@auth_required
def decisions():
    """运营决策建议：指标监控 + 策略评估 + 决策建议输出。"""
    records = _load_records(request.args.get("batchCode"))
    metrics = review.evaluate_consistency(records) if records else {
        "agreementRate": 0, "automationRate": 0, "manualTransferRate": 0,
        "falseNegativeCount": 0, "falsePositiveCount": 0, "kappa": 0,
    }
    orders = [item.to_dict() for item in PaymentOrder.query.order_by(PaymentOrder.id.desc()).limit(500).all()]
    payment_summary = payment.summarize(orders) if orders else {}
    alerts = [item.to_dict() for item in MonitoringAlert.query.limit(200).all()]
    advice = review.decision_advice(metrics, payment_summary, alerts)

    return ok(
        {
            "advice": advice,
            "metrics": {
                "review": {
                    "agreementRate": metrics.get("agreementRate"),
                    "kappa": metrics.get("kappa"),
                    "automationRate": metrics.get("automationRate"),
                    "manualTransferRate": metrics.get("manualTransferRate"),
                },
                "payment": {
                    "total": payment_summary.get("total", 0),
                    "successRate": payment_summary.get("successRate"),
                    "avgDurationMs": payment_summary.get("avgDurationMs"),
                    "compensationRate": payment_summary.get("compensationRate"),
                },
                "monitoring": {
                    "total": len(alerts),
                    "high": len([item for item in alerts if item["riskLevel"] == "high"]),
                    "autoHandledRate": monitoring.summarize_alerts(alerts).get("autoHandledRate", 0),
                },
            },
            "generatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@bp.get("/overview")
@auth_required
def overview():
    """一体化智能支撑总览：五大能力的核心指标（供大脑展板与运营看板使用）。"""
    orders = [item.to_dict() for item in PaymentOrder.query.order_by(PaymentOrder.id.desc()).limit(500).all()]
    payment_summary = payment.summarize(orders) if orders else {"total": 0}
    records = _load_records(None)
    consistency = review.evaluate_consistency(records) if records else {"total": 0}
    alerts = [item.to_dict() for item in MonitoringAlert.query.all()]
    monitoring_summary = monitoring.summarize_alerts(alerts)

    return ok(
        {
            "payment": payment_summary,
            "consistency": {key: consistency.get(key) for key in
                            ("total", "agreementRate", "autoAgreementRate", "automationRate", "kappa",
                             "falseNegativeCount", "falsePositiveCount", "manualTransferRate")},
            "monitoring": monitoring_summary,
            "adviceCount": len(review.decision_advice(consistency, payment_summary, alerts)),
            "generatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
