# -*- coding: utf-8 -*-
"""AI 审核一致性管理引擎（对应赛题「实现目标 3」与「建设范围四」）。

赛题原文要求：建立统一审核标准、统一风险标签、统一处置口径和一致性评估机制，
形成「**AI 初审、人工复核、差异回流、持续优化**」的协同审核模式。

本模块实现该闭环的四段：
1. `ai_review`       —— AI 初审：输出审核结论（approve/reject/manual）、置信度与命中证据；
2. `human_review`    —— 人工复核：模拟审核员的独立判断（口径更严、结论带噪声），
                        并遵循「低置信度必转人工」「高风险必转人工」的协同规则；
3. `evaluate_consistency` —— 一致性评估：一致率、混淆矩阵、Cohen's Kappa、
                        分歧类型（漏放/误拦）、按风险等级与置信度区间的一致性、
                        自动化率（AI 可独立决策的比例）；
4. `suggest_optimization` —— 差异回流与策略优化：基于分歧样本给出阈值/权重调整建议，
                        并可对比优化前后的指标，形成「持续优化」证据链。

另外提供 `decision_advice`：把指标转成面向运营的决策建议（赛题建设范围五：
「指标监控、风险分析、策略评估、决策建议输出」）。
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Sequence

# ---------------- 统一审核标准（赛题要求「统一审核标准、统一风险标签、统一处置口径」） ----------------

# 审核结论口径：三分类，AI 与人工使用完全相同的取值
AI_APPROVE, AI_REJECT, AI_MANUAL = "approve", "reject", "manual"
DECISION_LABELS = {
    AI_APPROVE: "通过",
    AI_REJECT: "拒绝",
    AI_MANUAL: "转人工/需补充材料",
}

# 统一风险标签体系（等级 → 标签 → 建议处置）
RISK_TAGS = [
    {"level": "high", "tag": "高风险", "color": "#e5484d", "action": "拒绝 / 转人工复核"},
    {"level": "medium", "tag": "中风险", "color": "#f5a623", "action": "二次验证 / 抽检"},
    {"level": "low", "tag": "低风险", "color": "#14a37f", "action": "自动通过"},
]

# 默认审核策略（可被差异回流动态调整）
DEFAULT_POLICY = {
    "approveThreshold": 0.35,     # AI 评分低于该值 → 通过
    "rejectThreshold": 0.72,      # AI 评分高于该值 → 拒绝
    "confidenceFloor": 0.55,      # 置信度低于该值 → 强制转人工（越低自动化率越高、一致性略降）
    "ruleWeights": {              # 规则权重（差异回流会调整）
        "sanctionHit": 3.0,
        "highRiskRegion": 1.2,
        "amountAnomaly": 1.0,
        "velocity": 0.9,
        "identityMismatch": 1.1,
        "newMerchant": 0.4,
        "nightTrade": 0.3,
    },
}


def _risk_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def ai_review(item: dict, policy: dict | None = None, rng: random.Random | None = None) -> dict:
    """AI 初审：按统一标准给出结论、评分、置信度与命中证据。

    item 字段：{code, name, amount, destRegion, merchantAge, identityMatch,
               nightRatio, sanctionHit, historyDeclines, velocity1h}
    """
    policy = policy or DEFAULT_POLICY
    rng = rng or random.Random(2026)
    started = time.perf_counter()
    weights = policy["ruleWeights"]

    reasons: List[str] = []
    score = 0.06 + rng.uniform(-0.02, 0.06)  # 基线噪声（体现模型固有不确定性）

    if item.get("sanctionHit"):
        score += 0.55 * weights["sanctionHit"] / 3.0
        reasons.append({"rule": "sanctionHit", "text": "命中 OFAC/联合国制裁清单", "weight": weights["sanctionHit"]})
    if item.get("destRegion") in ("ME", "AF"):
        score += 0.12 * weights["highRiskRegion"]
        reasons.append({"rule": "highRiskRegion", "text": f"目的地 {item['destRegion']} 属高风险地区",
                        "weight": weights["highRiskRegion"]})
    amount = float(item.get("amount") or 0)
    if amount > 800_000:
        score += 0.18 * weights["amountAnomaly"]
        reasons.append({"rule": "amountAnomaly", "text": f"单笔金额 {amount:,.0f} 显著高于同层级商户均值",
                        "weight": weights["amountAnomaly"]})
    if int(item.get("velocity1h") or 0) >= 5:
        score += 0.16 * weights["velocity"]
        reasons.append({"rule": "velocity", "text": f"1 小时内交易 {item['velocity1h']} 笔，存在拆分交易特征",
                        "weight": weights["velocity"]})
    if item.get("identityMatch") is False:
        score += 0.20 * weights["identityMismatch"]
        reasons.append({"rule": "identityMismatch", "text": "KYC 身份信息与结算账户不一致",
                        "weight": weights["identityMismatch"]})
    if int(item.get("merchantAge") or 12) <= 3:
        score += 0.10 * weights["newMerchant"]
        reasons.append({"rule": "newMerchant", "text": f"商户入驻仅 {item.get('merchantAge')} 个月",
                        "weight": weights["newMerchant"]})
    if float(item.get("nightRatio") or 0) > 0.5:
        score += 0.08 * weights["nightTrade"]
        reasons.append({"rule": "nightTrade", "text": "夜间交易占比超过 50%", "weight": weights["nightTrade"]})
    if int(item.get("historyDeclines") or 0) > 2:
        score += 0.10
        reasons.append({"rule": "historyDeclines", "text": f"历史拒付 {item['historyDeclines']} 笔", "weight": 1.0})

    score = round(min(0.99, max(0.01, score)), 4)

    # 结论：按统一阈值的三分类
    if score <= policy["approveThreshold"]:
        decision = AI_APPROVE
    elif score >= policy["rejectThreshold"]:
        decision = AI_REJECT
    else:
        decision = AI_MANUAL

    # 置信度：距离决策边界越远越自信；命中制裁清单等强证据则更自信
    distance = min(abs(score - policy["approveThreshold"]), abs(score - policy["rejectThreshold"]))
    confidence = round(min(0.99, 0.55 + distance * 1.6), 4)
    if item.get("sanctionHit"):
        confidence = max(confidence, 0.96)
    if len(reasons) == 0:
        confidence = max(confidence, 0.9)  # 无命中证据时结论很确定（低风险）

    # 协同规则：低置信度强制转人工（赛题「低置信度转人工」）
    forced = False
    if confidence < policy["confidenceFloor"] and decision in (AI_APPROVE, AI_REJECT):
        decision = AI_MANUAL
        forced = True
        reasons.append({"rule": "lowConfidence", "text": f"置信度 {confidence:.2f} 低于阈值 "
                                                        f"{policy['confidenceFloor']}，强制转人工", "weight": 1.0})

    return {
        "aiDecision": decision,
        "aiDecisionLabel": DECISION_LABELS[decision],
        "aiScore": score,
        "aiConfidence": confidence,
        "riskLevel": _risk_level(score),
        "reasons": reasons,
        "forcedManual": forced,
        "aiLatencyMs": int((time.perf_counter() - started) * 1000) + rng.randint(35, 160),
    }


def human_review(item: dict, ai_result: dict, reviewer: str = "human.reviewer",
                 rng: random.Random | None = None) -> dict:
    """人工复核：独立给出结论（口径更严格 + 少量人为噪声）。

    模拟真实人工审核的两个特征：
    1) 对高风险更敏感（宁可错杀）：高风险样本更倾向拒绝；
    2) 存在个体差异噪声：约 8% 的样本会与「理性结论」不同。
    """
    rng = rng or random.Random(90210)
    score = ai_result["aiScore"]
    amount = float(item.get("amount") or 0)

    # 人工的判断基准：更强调强证据
    strict = score
    if item.get("sanctionHit"):
        strict = max(strict, 0.95)
    if item.get("identityMatch") is False:
        strict = max(strict, 0.8)
    if amount > 1_500_000 and score > 0.4:
        strict = min(0.99, strict + 0.08)

    strict += rng.uniform(-0.10, 0.10)  # 人为噪声（真实人工复核存在个体差异）

    if strict >= 0.70:
        decision = AI_REJECT
    elif strict <= 0.38:
        decision = AI_APPROVE
    else:
        decision = AI_MANUAL

    comments = {
        AI_APPROVE: "资料齐全，交易背景真实，同意通过",
        AI_REJECT: "存在制裁/身份不一致等实质风险，拒绝并上报",
        AI_MANUAL: "证据不足以直接判定，需商户补充贸易背景材料后再审",
    }
    return {
        "humanDecision": decision,
        "humanDecisionLabel": DECISION_LABELS[decision],
        "humanReviewer": reviewer,
        "humanComment": comments[decision],
        "humanLatencyMs": rng.randint(45_000, 240_000),  # 人工审核耗时（毫秒）
    }


def evaluate_consistency(records: Sequence[dict]) -> dict:
    """一致性评估：AI 初审与人工复核的结果比对（赛题「一致性评估机制」核心指标）。

    口径说明（关键，避免把「转人工」误算成分歧）：
    - 样品分为两类：**AI 独立决策**（approve/reject）与 **AI 转人工**（manual，属于协同而非分歧）；
    - `agreementRate`（核心一致性指标）= AI 独立决策样本中与人工结论一致的比例；
    - `overallAlignmentRate` = 含转人工样本的总体协同率（转人工视为已协同处理）；
    - 漏放/误拦仅在 AI 独立决策样本上统计，因为它们才代表 AI 的自主判断风险。
    """
    total = len(records)
    if not total:
        return {"total": 0}

    auto = [item for item in records if item["aiDecision"] in (AI_APPROVE, AI_REJECT)]
    manual_transferred = [item for item in records if item["aiDecision"] == AI_MANUAL]
    auto_agreed = [item for item in auto if item["agreed"]]
    overall_agreed = len(auto_agreed) + len(manual_transferred)  # 转人工视为协同成功

    matrix = {ai: {human: 0 for human in DECISION_LABELS} for ai in DECISION_LABELS}
    for item in records:
        matrix[item["aiDecision"]][item["humanDecision"]] = matrix[item["aiDecision"]].get(item["humanDecision"], 0) + 1

    kappa = _cohen_kappa([item for item in auto] or records)

    # 分歧只统计 AI 自主决策的样本
    false_negative = [item for item in auto if item["diffType"] == "false_negative"]
    false_positive = [item for item in auto if item["diffType"] == "false_positive"]

    by_risk = {}
    for level in ("high", "medium", "low"):
        subset = [item for item in auto if item["riskLevel"] == level]
        if subset:
            by_risk[level] = {
                "total": len(subset),
                "agreed": len([item for item in subset if item["agreed"]]),
                "agreementRate": round(len([item for item in subset if item["agreed"]]) / len(subset), 4),
            }

    buckets = [(0.0, 0.6), (0.6, 0.75), (0.75, 0.9), (0.9, 1.01)]
    by_confidence = []
    for low, high in buckets:
        subset = [item for item in auto if low <= item["aiConfidence"] < high]
        if not subset:
            continue
        by_confidence.append(
            {
                "range": f"{low:.2f}~{min(high, 1.0):.2f}",
                "total": len(subset),
                "agreementRate": round(len([item for item in subset if item["agreed"]]) / len(subset), 4),
            }
        )

    ai_avg_latency = sum(item["aiLatencyMs"] for item in records) / total
    human_avg_latency = sum(item["humanLatencyMs"] for item in records) / total

    return {
        "total": total,
        "agreedCount": len(auto_agreed),
        "agreementRate": round(len(auto_agreed) / len(auto), 4) if auto else 0.0,
        "overallAlignmentRate": round(overall_agreed / total, 4),
        "manualTransferredCount": len(manual_transferred),
        "autoReviewedCount": len(auto),
        "autoAgreementRate": round(len(auto_agreed) / len(auto), 4) if auto else 0.0,
        "automationRate": round(len(auto) / total, 4),
        "manualTransferRate": round(len(manual_transferred) / total, 4),
        "kappa": kappa,
        "kappaLevel": _kappa_level(kappa),
        "confusionMatrix": matrix,
        "falseNegativeCount": len(false_negative),
        "falsePositiveCount": len(false_positive),
        "falseNegativeRate": round(len(false_negative) / len(auto), 4) if auto else 0.0,
        "falsePositiveRate": round(len(false_positive) / len(auto), 4) if auto else 0.0,
        "byRiskLevel": by_risk,
        "byConfidence": by_confidence,
        "efficiency": {
            "aiAvgLatencyMs": round(ai_avg_latency, 1),
            "humanAvgLatencyMs": round(human_avg_latency, 1),
            "speedup": round(human_avg_latency / ai_avg_latency, 1) if ai_avg_latency else 0,
        },
        "standards": {
            "decisionLabels": DECISION_LABELS,
            "riskTags": RISK_TAGS,
            "note": "AI 与人工使用完全相同的审核结论口径与风险标签体系；"
                    "转人工样本计入协同率而不计入分歧，一致性以 AI 自主决策样本为准",
        },
    }


def _cohen_kappa(records: Sequence[dict]) -> float:
    """计算 Cohen's Kappa：排除随机一致后的真实一致性水平。"""
    total = len(records)
    if not total:
        return 0.0
    observed = len([item for item in records if item["agreed"]]) / total
    expected = 0.0
    for decision in DECISION_LABELS:
        ai_count = len([item for item in records if item["aiDecision"] == decision]) / total
        human_count = len([item for item in records if item["humanDecision"] == decision]) / total
        expected += ai_count * human_count
    if expected >= 1:
        return 0.0
    return round((observed - expected) / (1 - expected), 4)


def _kappa_level(kappa: float) -> str:
    if kappa >= 0.8:
        return "几乎完全一致（Almost perfect）"
    if kappa >= 0.6:
        return "高度一致（Substantial）"
    if kappa >= 0.4:
        return "中等一致（Moderate）"
    if kappa >= 0.2:
        return "一般一致（Fair）"
    return "一致性偏低（Slight）"


def _replay(records: Sequence[dict], policy: dict) -> list[dict]:
    """用给定策略在同一批样本上复盘（保证「优化前后」可比）。"""
    replay = []
    for index, item in enumerate(records):
        raw = item.get("raw") or {"code": item.get("targetId", f"S{index}"), "amount": item.get("amount", 0)}
        new_ai = ai_review(raw, policy, random.Random(abs(index * 7919 + 13) % 10000))
        agrees = new_ai["aiDecision"] == item["humanDecision"]
        if agrees:
            diff = "none"
        elif new_ai["aiDecision"] == AI_APPROVE and item["humanDecision"] == AI_REJECT:
            diff = "false_negative"
        elif new_ai["aiDecision"] == AI_REJECT and item["humanDecision"] == AI_APPROVE:
            diff = "false_positive"
        else:
            diff = "both_manual"
        replay.append(
            {
                **item,
                "aiDecision": new_ai["aiDecision"],
                "aiConfidence": new_ai["aiConfidence"],
                "aiScore": new_ai["aiScore"],
                "agreed": agrees,
                "diffType": diff,
            }
        )
    return replay


def _objective(metrics: dict) -> float:
    """优化目标：在保证一致性与不漏放的前提下提升自动化率。

    综合得分 = 0.6×一致性 + 0.25×自动化率 − 1.0×漏放率
    （漏放权重最高，体现「宁可转人工，不可放过风险」的跨境合规底线）
    """
    return (
        0.6 * metrics.get("agreementRate", 0)
        + 0.25 * metrics.get("automationRate", 0)
        - 1.0 * metrics.get("falseNegativeRate", 0)
    )


def optimize_policy(records: Sequence[dict], policy: dict | None = None) -> dict:
    """策略寻优：在候选阈值网格上复盘，选出综合得分最高的策略。

    与「拍脑袋调参数」不同，这里对每个候选策略都用**同一批真实样本**复盘并量化对比，
    候选策略必须同时满足两条硬约束，否则直接淘汰：
      ① 漏放率不得高于当前策略；② 一致性不得低于当前策略的 98%。
    """
    policy = policy or default_policy()
    baseline_metrics = evaluate_consistency(records)
    baseline_score = _objective(baseline_metrics)

    candidates = []
    for approve in (0.25, 0.30, 0.35, 0.40, 0.45):
        for floor in (0.45, 0.50, 0.55, 0.60):
            candidate = {
                "approveThreshold": approve,
                "rejectThreshold": policy["rejectThreshold"],
                "confidenceFloor": floor,
                "ruleWeights": dict(policy["ruleWeights"]),
            }
            if approve == policy["approveThreshold"] and floor == policy["confidenceFloor"]:
                continue
            metrics = evaluate_consistency(_replay(records, candidate))
            constraint_ok = (
                metrics["falseNegativeRate"] <= baseline_metrics["falseNegativeRate"] + 1e-9
                and metrics["agreementRate"] >= baseline_metrics["agreementRate"] * 0.98
            )
            candidates.append(
                {
                    "config": candidate,
                    "metrics": metrics,
                    "score": round(_objective(metrics), 4),
                    "constraintOk": constraint_ok,
                }
            )

    feasible = [item for item in candidates if item["constraintOk"]]
    best = max(feasible, key=lambda item: item["score"]) if feasible else None
    if best and best["score"] <= baseline_score:
        best = None  # 没有更优解则维持现状，避免为改而改

    return {
        "baselineMetrics": baseline_metrics,
        "baselineScore": round(baseline_score, 4),
        "candidates": sorted(candidates, key=lambda item: -item["score"])[:6],
        "best": best,
    }


def suggest_optimization(metrics: dict, records: Sequence[dict],
                         policy: dict | None = None) -> dict:
    """差异回流与策略优化：基于分歧样本寻找更优策略，并给出量化对比。

    返回 {suggestion, points, beforeConfig, afterConfig, beforeMetrics, afterMetrics}
    """
    policy = policy or default_policy()
    result = optimize_policy(records, policy)
    before = result["baselineMetrics"]
    best = result["best"]

    points: List[str] = []
    if before.get("falseNegativeCount"):
        points.append(
            f"本期存在 {before['falseNegativeCount']} 笔漏放（AI 通过但人工拒绝），"
            f"漏放率 {before['falseNegativeRate'] * 100:.1f}%，建议提高「身份不一致」「拆分交易」规则权重"
        )
    if before.get("falsePositiveCount"):
        points.append(
            f"本期存在 {before['falsePositiveCount']} 笔误拦（AI 拒绝但人工通过），"
            f"建议放缓拒绝阈值以降低对优质商户的误伤"
        )
    if before.get("manualTransferRate", 0) > 0.3:
        points.append(
            f"转人工比例 {before['manualTransferRate'] * 100:.1f}% 偏高："
            f"在一致性不受损的前提下可下调置信度门槛以提升自动化率"
        )
    if before.get("byConfidence"):
        low_bucket = min(before["byConfidence"], key=lambda item: item["agreementRate"])
        points.append(
            f"置信度区间 {low_bucket['range']} 的一致率最低（{low_bucket['agreementRate'] * 100:.0f}%），"
            f"说明该区间样本应由人工把关，是转人工策略的重点区域"
        )

    if best:
        after_config = best["config"]
        after_metrics = best["metrics"]
        points.insert(
            0,
            f"已通过 {len(result['candidates'])} 组候选策略复盘，选出综合得分最优策略："
            f"通过阈值 {policy['approveThreshold']} → {after_config['approveThreshold']}、"
            f"置信度门槛 {policy['confidenceFloor']} → {after_config['confidenceFloor']}，"
            f"预计一致性 {before['agreementRate'] * 100:.1f}% → {after_metrics['agreementRate'] * 100:.1f}%、"
            f"自动化率 {before['automationRate'] * 100:.1f}% → {after_metrics['automationRate'] * 100:.1f}%",
        )
    else:
        after_config = dict(policy)
        after_metrics = before
        points.insert(
            0,
            "已对多组候选策略复盘，当前策略在「一致性 / 自动化率 / 漏放率」综合目标下已是最优，"
            "建议维持现有阈值，继续抽样复核积累样本",
        )

    return {
        "suggestion": "；".join(points),
        "points": points,
        "beforeConfig": policy,
        "afterConfig": after_config,
        "beforeMetrics": {
            "agreementRate": before.get("agreementRate"),
            "overallAlignmentRate": before.get("overallAlignmentRate"),
            "automationRate": before.get("automationRate"),
            "manualTransferRate": before.get("manualTransferRate"),
            "kappa": before.get("kappa"),
            "falseNegativeCount": before.get("falseNegativeCount"),
            "falsePositiveCount": before.get("falsePositiveCount"),
        },
        "afterMetrics": {
            "agreementRate": after_metrics.get("agreementRate"),
            "overallAlignmentRate": after_metrics.get("overallAlignmentRate"),
            "automationRate": after_metrics.get("automationRate"),
            "manualTransferRate": after_metrics.get("manualTransferRate"),
            "kappa": after_metrics.get("kappa"),
            "falseNegativeCount": after_metrics.get("falseNegativeCount"),
            "falsePositiveCount": after_metrics.get("falsePositiveCount"),
        },
        "candidates": result["candidates"],
        "improved": bool(best),
    }


def decision_advice(metrics: dict, payment_summary: dict | None = None,
                    alerts: Sequence[dict] | None = None) -> List[dict]:
    """运营决策建议输出（赛题建设范围五：策略评估与决策建议）。

    把指标转成带优先级、预期收益与责任角色的可执行建议。
    """
    advice: List[dict] = []
    alerts = alerts or []

    if metrics.get("falseNegativeCount", 0) > 0:
        advice.append(
            {
                "priority": "P0",
                "title": "收紧 AI 通过阈值，压降漏放风险",
                "basis": f"本期漏放 {metrics['falseNegativeCount']} 笔（一致率 {metrics['agreementRate'] * 100:.1f}%）",
                "action": "在「审核一致性管理」中执行策略优化，通过阈值下调 0.04 并提高身份核验规则权重",
                "owner": "风控策略岗",
                "expected": "预计漏放笔数下降，人工复核工作量增加约 3%~5%",
            }
        )
    if metrics.get("manualTransferRate", 0) > 0.3:
        advice.append(
            {
                "priority": "P1",
                "title": "降低转人工比例，提升自动化率",
                "basis": f"当前转人工比例 {metrics['manualTransferRate'] * 100:.1f}%，自动化率 {metrics['automationRate'] * 100:.1f}%",
                "action": "下调置信度门槛，并对中低风险样本启用抽检而非全量复核",
                "owner": "运营管理岗",
                "expected": f"自动化率有望提升至 {(min(0.9, metrics['automationRate'] + 0.1)) * 100:.0f}% 以上",
            }
        )
    if payment_summary and payment_summary.get("compensationRate", 0) > 0.02:
        advice.append(
            {
                "priority": "P1",
                "title": "优化通道选择，降低补偿率",
                "basis": f"支付补偿率 {payment_summary['compensationRate'] * 100:.2f}%，平均处理耗时 {payment_summary['avgDurationMs']:.0f}ms",
                "action": "对降级通道（中东/非洲代理行）下调路由权重，优先使用成功率更高的直连通道",
                "owner": "支付运营岗",
                "expected": "补偿率预计下降 30%~50%，成功率提升约 1 个百分点",
            }
        )
    if payment_summary and payment_summary.get("riskBlockRate", 0) > 0.05:
        advice.append(
            {
                "priority": "P2",
                "title": "复核风险拦截口径，避免误伤优质商户",
                "basis": f"风险拦截率 {payment_summary['riskBlockRate'] * 100:.2f}%，拦截 {payment_summary['blockedCount']} 笔",
                "action": "对拦截样本开展人工抽检，把确认误拦的样本回流至模型训练集",
                "owner": "风控策略岗",
                "expected": "减少优质商户误伤，提升支付成功率与客户满意度",
            }
        )
    if alerts:
        high = [item for item in alerts if item.get("riskLevel") == "high"]
        if high:
            advice.append(
                {
                    "priority": "P0",
                    "title": "处置高危异常交易",
                    "basis": f"异常监测发现 {len(high)} 条高风险预警，涉及金额 "
                             f"{sum(item.get('amount', 0) for item in high):,.0f} 元",
                    "action": "按「自动处置 + 人工确认」流程在 30 分钟内闭环，并同步联盟链存证",
                    "owner": "反洗钱岗",
                    "expected": "阻断可疑资金链路，满足 FATF 可疑交易报告时限要求",
                }
            )

    if not advice:
        advice.append(
            {
                "priority": "P2",
                "title": "保持当前策略并持续抽检",
                "basis": "本期一致性与支付指标均在目标区间内",
                "action": "维持现有阈值与路由权重，按周开展抽样复核",
                "owner": "风控策略岗",
                "expected": "保持稳定性，积累优化样本",
            }
        )
    return advice


def default_policy() -> dict:
    return {
        "approveThreshold": DEFAULT_POLICY["approveThreshold"],
        "rejectThreshold": DEFAULT_POLICY["rejectThreshold"],
        "confidenceFloor": DEFAULT_POLICY["confidenceFloor"],
        "ruleWeights": dict(DEFAULT_POLICY["ruleWeights"]),
    }
