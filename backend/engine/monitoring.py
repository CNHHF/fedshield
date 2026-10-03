# -*- coding: utf-8 -*-
"""异常行为检测与自动处置（对应赛题「建设范围二：智能风控能力建设」）。

赛题原文要求：支持**交易风险识别、账户风险评估、商户风险识别、异常行为检测、
实时预警和自动处置**，形成风险识别与处置闭环。

本模块用可解释的规则 + 统计特征实现异常检测（每条预警都给出证据链），
并按风险等级给出统一的自动处置口径（pass / verify / block / manual），
与 `engine.review` 的审核口径共用同一套风险标签体系。
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Sequence

# 统一处置口径（与 review.RISK_TAGS 一致）
ACTIONS = [
    {"code": "pass", "label": "自动放行", "level": "low"},
    {"code": "verify", "label": "二次验证", "level": "medium"},
    {"code": "manual", "label": "转人工复核", "level": "high"},
    {"code": "block", "label": "自动拦截", "level": "high"},
]

# 检测规则（规则名、说明、基础分、阈值）
DETECTION_RULES = [
    {
        "code": "VELOCITY", "name": "短时高频交易",
        "desc": "同一商户 1 小时内交易笔数异常，存在拆分交易规避监管特征",
        "baseScore": 0.42, "threshold": "≥5 笔/小时",
    },
    {
        "code": "AMOUNT_SURGE", "name": "金额突增",
        "desc": "单笔金额显著高于该商户历史均值（>3 倍），疑似资金异常归集",
        "baseScore": 0.38, "threshold": ">均值×3",
    },
    {
        "code": "HIGH_RISK_DEST", "name": "高风险地区/高风险交易",
        "desc": "该商户存在流向高风险地区或被标注为高风险的交易，需强化尽职调查",
        "baseScore": 0.35, "threshold": "高风险交易 ≥1 笔",
    },
    {
        "code": "NIGHT_BURST", "name": "夜间集中交易",
        "desc": "非营业时段集中交易，与正常经营模式不符",
        "baseScore": 0.28, "threshold": "夜间占比 >50%",
    },
    {
        "code": "COUNTERPARTY_SPREAD", "name": "收款人分散度异常",
        "desc": "短期内对公付款方数量激增，疑似分销式洗钱",
        "baseScore": 0.30, "threshold": "≥6 个付款方",
    },
    {
        "code": "NEW_MERCHANT_LARGE", "name": "新商户大额交易",
        "desc": "新入驻商户短期内出现大额交易，需核验贸易背景真实性",
        "baseScore": 0.33, "threshold": "入驻<3 个月且金额>50 万",
    },
]


def _level_of(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def action_for(score: float) -> tuple[str, str]:
    """统一处置口径：按总风险分给出动作与中文标签。"""
    if score >= 0.85:
        return "block", "自动拦截"
    if score >= 0.7:
        return "manual", "转人工复核"
    if score >= 0.45:
        return "verify", "二次验证"
    return "pass", "自动放行"


def detect(transactions: Sequence[dict], merchants: Dict[str, dict] | None = None) -> List[dict]:
    """对一批交易做异常检测，返回预警列表（含证据链与处置建议）。

    transactions 每项：{code, merchantCode, merchantName, region, destRegion, amount,
                       category, counterparties, occurredAt, destRisk, hour}
    """
    merchants = merchants or {}
    alerts: List[dict] = []

    # 1) 按商户聚合，计算统计基线
    by_merchant: Dict[str, List[dict]] = {}
    for item in transactions:
        by_merchant.setdefault(item["merchantCode"], []).append(item)

    for merchant_code, items in by_merchant.items():
        merchant = merchants.get(merchant_code, {})
        amounts = [float(item.get("amount") or 0) for item in items]
        mean_amount = statistics.mean(amounts) if amounts else 0.0
        night_items = [item for item in items if int(item.get("hour") or 12) >= 22 or int(item.get("hour") or 12) <= 5]

        # ---------------- 规则 1：短时高频（按「商户 × 小时」时间窗口统计） ----------------
        by_hour: Dict[int, List[dict]] = {}
        for item in items:
            by_hour.setdefault(int(item.get("hour") or 12), []).append(item)
        for hour, bucket in by_hour.items():
            if len(bucket) < 5:
                continue
            score = DETECTION_RULES[0]["baseScore"] + min(0.3, (len(bucket) - 5) * 0.05)
            alerts.append(
                _build_alert(
                    DETECTION_RULES[0], score, bucket[0],
                    evidence=[
                        f"{hour:02d}:00-{hour + 1:02d}:00 时段交易 {len(bucket)} 笔"
                        f"（阈值 {DETECTION_RULES[0]['threshold']}）",
                        f"该时段金额合计 {sum(float(i.get('amount') or 0) for i in bucket):,.0f} 元",
                    ],
                    detail="疑似拆分交易，建议核查交易背景与上下游关系",
                )
            )

        # ---------------- 规则 2：金额突增（按偏离倍数取前 2 笔，避免刷屏） ----------------
        surges = []
        for item in items:
            amount = float(item.get("amount") or 0)
            if mean_amount and amount > mean_amount * 3 and amount > 100_000:
                surges.append((amount / mean_amount, item))
        for ratio, item in sorted(surges, key=lambda row: -row[0])[:2]:
            score = DETECTION_RULES[1]["baseScore"] + min(0.25, (ratio - 3) * 0.05)
            alerts.append(
                _build_alert(
                    DETECTION_RULES[1], score, item,
                    evidence=[
                        f"本笔金额 {float(item.get('amount') or 0):,.0f} 元，该商户历史均值 {mean_amount:,.0f} 元",
                        f"偏离倍数 {ratio:.1f}×（阈值 ×3）",
                    ],
                    detail="大额异常交易，建议核实贸易单据与资金用途",
                )
            )

        # ---------------- 规则 3：高风险地区/高风险标签交易（按商户聚合） ----------------
        risky = [item for item in items if float(item.get("destRisk") or 0) >= 0.7]
        if risky:
            destinations = sorted({item.get("destRegion") for item in risky})
            total_risky = sum(float(item.get("amount") or 0) for item in risky)
            score = DETECTION_RULES[2]["baseScore"] + min(0.3, 0.05 * len(risky))
            alerts.append(
                _build_alert(
                    DETECTION_RULES[2], score, risky[0],
                    evidence=[
                        f"{len(risky)} 笔交易被标注为高风险，流向 {'、'.join(destinations)}",
                        f"涉险金额合计 {total_risky:,.0f} 元",
                    ],
                    detail="高风险地区/高风险交易，需强化客户尽职调查（EDD）与贸易背景核验",
                )
            )

        # ---------------- 规则 4：夜间集中交易 ----------------
        if items and len(night_items) / len(items) > 0.5:
            alerts.append(
                _build_alert(
                    DETECTION_RULES[3], DETECTION_RULES[3]["baseScore"] + 0.1, night_items[0],
                    evidence=[
                        f"夜间交易 {len(night_items)}/{len(items)} 笔，占比 {len(night_items) / len(items) * 100:.0f}%",
                        "与该商户经营时段特征不符",
                    ],
                    detail="交易时段异常，建议纳入持续监测名单",
                )
            )

        # ---------------- 规则 5：收款人分散度 ----------------
        max_counterparties = max((int(item.get("counterparties") or 1) for item in items), default=0)
        if max_counterparties >= 6:
            alerts.append(
                _build_alert(
                    DETECTION_RULES[4], DETECTION_RULES[4]["baseScore"] + min(0.2, max_counterparties * 0.02), items[0],
                    evidence=[
                        f"对公付款方数量达到 {max_counterparties} 个（阈值 ≥6）",
                        "付款方之间无公开关联关系",
                    ],
                    detail="疑似分销式资金归集，建议穿透核查最终受益人",
                )
            )

        # ---------------- 规则 6：新商户大额 ----------------
        age = int(merchant.get("merchantAge") or 12)
        big = [item for item in items if float(item.get("amount") or 0) > 500_000]
        if age <= 3 and big:
            alerts.append(
                _build_alert(
                    DETECTION_RULES[5], DETECTION_RULES[5]["baseScore"] + 0.15, big[0],
                    evidence=[
                        f"商户入驻 {age} 个月（阈值 <3 个月）",
                        f"出现 {len(big)} 笔 50 万元以上交易，最大 {max(float(i.get('amount') or 0) for i in big):,.0f} 元",
                    ],
                    detail="新商户大额交易，建议核验贸易背景与报关单据",
                )
            )

    # 组合风险加成：同一商户同时命中多条规则时，风险显著上升
    # （跨境反洗钱实务中「多红旗叠加」是升级为高危与上报可疑交易的主要依据）
    merchant_hits: Dict[str, int] = {}
    for item in alerts:
        key = item.get("merchantCode") or item.get("targetName") or "-"
        merchant_hits[key] = merchant_hits.get(key, 0) + 1
    for item in alerts:
        key = item.get("merchantCode") or item.get("targetName") or "-"
        hits = merchant_hits.get(key, 1)
        if hits >= 2:
            bonus = min(0.18, 0.07 * (hits - 1))
            item["riskScore"] = round(min(0.99, item["riskScore"] + bonus), 4)
            item["riskLevel"] = _level_of(item["riskScore"])
            item["action"], item["actionLabel"] = action_for(item["riskScore"])
            item["status"] = "handled" if item["action"] in ("pass", "block") else "pending"
            item["evidence"] = list(item["evidence"]) + [f"该商户同期命中 {hits} 条异常规则，组合风险加成 +{bonus:.2f}"]

    # 按风险分排序并去重（同一订单+规则只保留最高分预警）
    dedup: Dict[str, dict] = {}
    for item in sorted(alerts, key=lambda row: -row["riskScore"]):
        key = f"{item['targetId']}-{item['ruleCode']}"
        if key not in dedup:
            dedup[key] = item
    result = sorted(dedup.values(), key=lambda row: -row["riskScore"])
    for index, item in enumerate(result, 1):
        item["code"] = f"MON-{index:04d}"
    return result


def _build_alert(rule: dict, score: float, item: dict, evidence: List[str], detail: str) -> dict:
    score = round(min(0.99, max(0.05, score)), 4)
    level = _level_of(score)
    action, action_label = action_for(score)
    return {
        "code": "",
        "ruleCode": rule["code"],
        "ruleName": rule["name"],
        "ruleDesc": rule["desc"],
        "targetType": "payment",
        "targetId": item.get("code") or item.get("merchantCode") or "",
        "targetName": item.get("merchantName") or item.get("merchantCode") or "",
        "merchantCode": item.get("merchantCode") or "",
        "amount": float(item.get("amount") or 0),
        "riskLevel": level,
        "riskScore": score,
        "evidence": evidence,
        "action": action,
        "actionLabel": action_label,
        "status": "handled" if action in ("pass", "block") else "pending",
        "detail": detail,
    }


def summarize_alerts(alerts: Sequence[dict]) -> dict:
    """预警汇总（供监控看板与决策建议使用）。"""
    total = len(alerts)
    if not total:
        return {"total": 0, "high": 0, "medium": 0, "low": 0}
    by_level = {level: len([item for item in alerts if item["riskLevel"] == level])
                for level in ("high", "medium", "low")}
    by_rule: Dict[str, dict] = {}
    for item in alerts:
        bucket = by_rule.setdefault(item["ruleCode"], {"ruleCode": item["ruleCode"], "ruleName": item["ruleName"], "count": 0})
        bucket["count"] += 1
    by_action: Dict[str, int] = {}
    for item in alerts:
        by_action[item["actionLabel"]] = by_action.get(item["actionLabel"], 0) + 1
    return {
        "total": total,
        **by_level,
        "amountAtRisk": round(sum(float(item.get("amount") or 0) for item in alerts), 2),
        "byRule": sorted(by_rule.values(), key=lambda row: -row["count"]),
        "byAction": [{"action": key, "count": value} for key, value in by_action.items()],
        "autoHandledRate": round(
            len([item for item in alerts if item["action"] in ("pass", "block")]) / total, 4
        ),
        "manualPendingRate": round(len([item for item in alerts if item["action"] == "manual"]) / total, 4),
    }


def rules_meta() -> List[dict]:
    return DETECTION_RULES
