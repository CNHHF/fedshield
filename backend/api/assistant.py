"""Local, evidence-grounded risk Q&A and privacy release endpoints."""
import math
import re

from flask import Blueprint, current_app
from sqlalchemy import update

from ..audit import logger as audit_logger
from ..engine.privacy_release import release
from ..extensions import db
from ..models import BudgetItem, BudgetTrend, MonitoringAlert, PaymentOrder, ReviewRecord, now
from ..utils.deps import auth_required, require_permission
from ..utils.response import ApiError, body, ok

bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


@bp.post("/privacy-release")
@auth_required
@require_permission("budget:manage")
def privacy_release():
    payload = body()
    if not isinstance(payload, dict):
        raise ApiError("请求必须是 JSON 对象")
    try:
        raw = payload.get("values")
        if not isinstance(raw, list) or not 2 <= len(raw) <= 1000 or any(isinstance(x, bool) for x in raw):
            raise ValueError("请输入 2 到 1000 个数值")
        values = [float(x) for x in raw]
        epsilon = float(payload.get("epsilon", 1))
        result = release(values, float(payload.get("lower", 0)), float(payload.get("upper", 100)),
                         epsilon, payload.get("statistic", "mean"))
        budget_id = int(payload.get("budgetId"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ApiError(str(exc)) from exc
    # Conditional update prevents concurrent releases from overspending the ledger.
    changed = db.session.execute(update(BudgetItem).where(
        BudgetItem.id == budget_id, BudgetItem.used + epsilon <= BudgetItem.total
    ).values(used=BudgetItem.used + epsilon))
    if changed.rowcount != 1:
        db.session.rollback()
        raise ApiError("预算项目不存在或剩余 ε 不足，未发布结果", code=409)
    item = db.session.get(BudgetItem, budget_id)
    db.session.add(BudgetTrend(month=now().strftime("%Y-%m"), used=item.used,
        remaining=max(0, item.total-item.used), usedRatio=item.used/item.total,
        scene="统计加噪发布"))
    db.session.commit()
    audit_logger.record_from_request("privacy.release", target=str(budget_id), operation="查询",
        detail=f"拉普拉斯统计发布，ε={epsilon}，统计类型={result['statistic']}；不记录原始数据")
    result["budget"] = item.to_dict()
    return ok(result)


@bp.post("/ask")
@auth_required
@require_permission("engine:task:manage")
def ask():
    payload = body()
    question = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise ApiError("问题长度应为 1 到 500 字")
    q = question.strip()
    citations, actions = [], []
    # Follow-up topic is UI context only, never authorization or executable instructions.
    topic = payload.get("topic", "")
    if any(x in q.lower() for x in ("隐私", "加噪", "预算", "epsilon", "ε")) or (topic == "privacy" and len(q) < 15):
        topic = "privacy"
        items = BudgetItem.query.order_by(BudgetItem.id).all()
        total = math.fsum(i.total or 0 for i in items)
        used = math.fsum(i.used or 0 for i in items)
        answer = f"当前隐私预算台账共有 {len(items)} 个项目，总 ε={total:.4f}，已用 {used:.4f}，剩余 {max(0,total-used):.4f}。\n统计加噪先按公开上下界裁剪，再用拉普拉斯机制发布均值或总和。ε 越小，噪声尺度越大。每次发布都扣减所选项目预算；不输出原始统计量和实际噪声。\n这些额度只适用于当前台账，不能据此推断整个平台已完成差分隐私证明。"
        citations = [{"label": "隐私预算台账", "value": f"{len(items)} 项 / 已用 ε {used:.4f}"}]
        actions = [{"label": "打开加噪隐私处理", "path": "/engine/privacy"}]
    elif any(x in q for x in ("支付", "订单", "通道", "重试", "补偿")):
        topic = "payment"
        count = PaymentOrder.query.count()
        blocked = PaymentOrder.query.filter_by(status="blocked").count()
        compensated = PaymentOrder.query.filter_by(compensated=True).count()
        answer = f"当前订单记录共 {count} 笔，其中拦截 {blocked} 笔、已补偿 {compensated} 笔。\n建议先在支付智能处理中查看失败原因和事件轨迹，再核对通道健康度与路由限制；本助手不会执行重试或放行。" if count else "尚无支付订单记录。请先在支付智能处理页面生成演示订单，再查询支付情况。"
        citations = [{"label": "支付订单表（全量）", "value": f"{count} 笔"}]
        actions = [{"label": "查看支付订单", "path": "/ops/payment"}]
    elif any(x in q for x in ("审核", "一致", "漏放", "误拦", "复核")):
        topic = "review"
        count = ReviewRecord.query.count()
        agreed = ReviewRecord.query.filter_by(agreed=True).count()
        missed = ReviewRecord.query.filter_by(diffType="false_negative").count()
        answer = (f"当前审核记录 {count} 条，结论一致 {agreed} 条，一致率 {agreed/count:.1%}，漏放差异 {missed} 条。\n优先复核漏放差异，再分析低置信度记录。演示人工结论为模拟数据，一致率不等同于真实风控准确率。" if count else "尚无审核记录。请先执行审核批次，再分析一致性与漏放差异。")
        citations = [{"label": "审核记录表（全量）", "value": f"{count} 条"}]
        actions = [{"label": "查看审核一致性", "path": "/ops/review"}]
    elif any(x in q for x in ("风险", "风控", "预警", "异常", "为什么", "原因")) or topic == "risk":
        topic = "risk"
        rows = MonitoringAlert.query.order_by(MonitoringAlert.riskScore.desc(), MonitoringAlert.id.desc()).all()
        code = re.search(r"MON-[A-Za-z0-9-]+", q, re.I)
        if code:
            rows = [r for r in rows if r.code.lower() == code.group().lower()]
        high = sum(r.riskLevel == "high" for r in rows)
        answer = f"当前{'指定' if code else '全量'}预警 {len(rows)} 条，其中高风险 {high} 条。"
        if not rows:
            answer += "未找到可解释的预警记录，请先执行异常检测或核对预警编号。"
        for r in rows[:3]:
            answer += f"\n{r.code}：命中“{r.ruleName}”，风险评分 {r.riskScore:.3f}；当前处置为{r.actionLabel or r.action}。依据：{str(r.evidence or r.detail)[:350]}"
            citations.append({"label": r.code, "value": r.ruleName})
        answer += "\n建议核对命中证据后由人工确认处置。本助手只作解释，不自动修改规则或放行交易。"
        actions = [{"label": "查看预警与证据", "path": "/ops/monitoring"}]
    else:
        topic = "help"
        answer = "我可以结合本地记录解释风险预警、支付异常、审核一致性和隐私预算。请问：当前有哪些高风险预警？为什么需要人工复核？加噪的 ε 怎么选择？\n当前采用本地意图识别与业务数据检索，未接入大语言模型；超出这些范围时无法可靠回答。"
    mode, notice = "本地风控问答", ""
    if not current_app.testing:
        from ..engine.llm_assistant import explain
        try:
            generated = explain(q, answer)
            if generated:
                answer = generated
                mode = "DeepSeek 风控助手"
                notice = "由 DeepSeek 根据本地检索摘要生成；依据与业务入口由本地系统提供，请核对后处置。"
        except Exception:
            notice = "大模型服务暂不可用，已返回本地检索结果。"
    return ok({"answer": answer, "topic": topic, "citations": citations, "actions": actions,
        "mode": mode, "notice": notice, "asOf": now().isoformat(), "scope": "当前演示库全量记录；不限定为今日"})
