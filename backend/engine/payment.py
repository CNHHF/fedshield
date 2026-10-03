# -*- coding: utf-8 -*-
"""支付智能处理引擎（对应赛题「建设范围一：支付智能处理能力建设」）。

覆盖赛题要求的能力项：
- 交易接入     ：统一接单入口，落地订单并进入处理链路
- 智能风控前置 ：调用风控评分（规则 + 联邦模型分），高风险直接拦截或转人工
- 智能路由     ：按「成本 / 成功率 / 时效 / 合规」多目标打分选择最优通道，
                受制裁或不合规通道直接排除（合规前置）
- 通道选择     ：支持按节点、币种、目的地、限额、通道健康度过滤
- 状态跟踪     ：received → risk_checked → routed → processing → success/failed
                → retrying → compensated / blocked / manual，全链路事件留痕
- 失败重试     ：指数退避 + 自动切换备用通道，最多 N 次
- 异常处理     ：区分通道故障 / 限额 / 合规拦截 / 网络超时，分类处置
- 自动补偿     ：重试耗尽后自动生成补偿单（改道重发或退款），并标记订单状态

设计说明：通道成功率/时延来自通道配置（可用真实对账数据替换），
路由打分为确定性多目标加权，结果可复现、可解释——每条决策都输出「为什么选它」。
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Sequence

# 路由评分权重（成本 / 成功率 / 时效 / 合规）
ROUTE_WEIGHTS = {"cost": 0.40, "success": 0.30, "latency": 0.20, "compliance": 0.10}

# 重试策略
MAX_RETRY = 2              # 最多重试次数
RETRY_BACKOFF_MS = [200, 600]   # 指数退避（毫秒）

# 风控处置阈值（可由「AI 审核一致性管理」的差异回流动态调整）
RISK_THRESHOLD = {"block": 0.85, "manual": 0.70, "verify": 0.45}

# 通道默认池（演示数据，可替换为真实通道对账结果）
DEFAULT_CHANNELS: List[dict] = [
    {
        "code": "PP-DIRECT", "name": "PingPong 直连通道", "region": "GLOBAL",
        "currencies": ["CNY", "USD", "EUR", "SGD", "GBP"],
        "destinations": ["EU", "US", "SEA", "CN", "ME", "AF"],
        "feeRate": 0.0055, "successRate": 0.982, "avgLatencyMs": 1600,
        "singleLimit": 5_000_000, "status": "available",
        "complianceNote": "自有牌照，支持全球 200+ 国家/地区",
    },
    {
        "code": "EU-SEPA", "name": "欧盟 SEPA 通道", "region": "EU",
        "currencies": ["EUR"], "destinations": ["EU"],
        "feeRate": 0.0032, "successRate": 0.991, "avgLatencyMs": 900,
        "singleLimit": 2_000_000, "status": "available",
        "complianceNote": "欧盟境内清算，需 SCC + DPIA 佐证方可传输 P1 数据",
    },
    {
        "code": "US-ACH", "name": "美国 ACH 通道", "region": "US",
        "currencies": ["USD"], "destinations": ["US"],
        "feeRate": 0.0038, "successRate": 0.975, "avgLatencyMs": 2400,
        "singleLimit": 3_000_000, "status": "available",
        "complianceNote": "受 OFAC 制裁筛查约束，命中清单直接拒绝",
    },
    {
        "code": "SG-FAST", "name": "新加坡 FAST 通道", "region": "SEA",
        "currencies": ["SGD", "USD", "CNY"], "destinations": ["SEA", "CN"],
        "feeRate": 0.0042, "successRate": 0.986, "avgLatencyMs": 1200,
        "singleLimit": 1_500_000, "status": "available",
        "complianceNote": "PDPA 合规，审计留存 3 年",
    },
    {
        "code": "CARD-VISA", "name": "Visa 卡组织通道", "region": "GLOBAL",
        "currencies": ["USD", "EUR", "CNY"], "destinations": ["EU", "US", "SEA", "ME"],
        "feeRate": 0.0125, "successRate": 0.968, "avgLatencyMs": 800,
        "singleLimit": 500_000, "status": "available",
        "complianceNote": "PCI-DSS v4.0，主账号需加密存储",
    },
    {
        "code": "ME-LOCAL", "name": "中东本地清算通道", "region": "ME",
        "currencies": ["USD", "AED"], "destinations": ["ME"],
        "feeRate": 0.0068, "successRate": 0.952, "avgLatencyMs": 2800,
        "singleLimit": 800_000, "status": "degraded",
        "complianceNote": "需本地持牌机构代理，链路时延较高",
    },
    {
        "code": "AF-AGENT", "name": "非洲代理行通道", "region": "AF",
        "currencies": ["USD"], "destinations": ["AF"],
        "feeRate": 0.0095, "successRate": 0.935, "avgLatencyMs": 3600,
        "singleLimit": 600_000, "status": "degraded",
        "complianceNote": "代理行链路，需加强反洗钱监测",
    },
]

# 受限目的地（合规前置：这些目的地不允许直接清算，需转人工合规审核）
RESTRICTED_DESTINATIONS = {"IR", "KP", "SY", "CU"}


def risk_action(score: float) -> tuple[str, str]:
    """把风险评分映射为处置动作。返回 (动作, 中文说明)。"""
    if score >= RISK_THRESHOLD["block"]:
        return "block", "风险评分超拦截阈值：直接拒绝并上链存证"
    if score >= RISK_THRESHOLD["manual"]:
        return "manual", "风险评分超人工复核阈值：转人工合规审核"
    if score >= RISK_THRESHOLD["verify"]:
        return "verify", "风险评分中等：触发二次验证（MFA + 生物核验）"
    return "pass", "风险评分正常：直接放行"


def score_channel(channel: dict, order: dict, risk_level: str) -> dict:
    """对单个通道做多目标打分（0~1，越高越优），并给出可解释的评分明细。"""
    reasons: List[str] = []

    # 1) 硬性可用性过滤（不满足直接返回 0 分并说明原因）
    if channel["status"] == "down":
        return {"score": 0.0, "eligible": False, "reason": "通道已下线"}
    if order["currency"] not in channel["currencies"]:
        return {"score": 0.0, "eligible": False, "reason": f"不支持币种 {order['currency']}"}
    if order["destRegion"] not in channel["destinations"]:
        return {"score": 0.0, "eligible": False, "reason": f"不支持目的地 {order['destRegion']}"}
    if order["amount"] > channel["singleLimit"]:
        return {"score": 0.0, "eligible": False, "reason": "超出单笔限额"}
    if order["destRegion"] in RESTRICTED_DESTINATIONS:
        return {"score": 0.0, "eligible": False, "reason": "目的地属受限地区，需合规专项审批"}

    # 2) 多目标归一化打分
    cost_score = max(0.0, 1 - channel["feeRate"] / 0.015)          # 费率越低越好
    success_score = channel["successRate"]
    latency_score = max(0.0, 1 - channel["avgLatencyMs"] / 4000)    # 时延越低越好
    compliance_score = 0.95 if "P1" not in channel["complianceNote"] else 0.85
    if channel["status"] == "degraded":
        compliance_score -= 0.15
        reasons.append("通道处于降级状态，稳定性风险较高")
    if risk_level == "high":
        # 高风险订单优先选择合规能力更强的通道
        compliance_score += 0.05
        reasons.append("高风险订单，路由偏好合规能力更强的通道")

    score = (
        ROUTE_WEIGHTS["cost"] * cost_score
        + ROUTE_WEIGHTS["success"] * success_score
        + ROUTE_WEIGHTS["latency"] * latency_score
        + ROUTE_WEIGHTS["compliance"] * compliance_score
    )
    reasons.append(
        f"费率 {channel['feeRate'] * 100:.2f}%、历史成功率 {channel['successRate'] * 100:.1f}%、"
        f"平均到账 {channel['avgLatencyMs']}ms"
    )
    return {
        "score": round(min(1.0, max(0.0, score)), 4),
        "eligible": True,
        "reason": "；".join(reasons),
        "breakdown": {
            "cost": round(cost_score, 4),
            "success": round(success_score, 4),
            "latency": round(latency_score, 4),
            "compliance": round(round(compliance_score, 4), 4),
        },
    }


def route_order(order: dict, channels: Sequence[dict], risk_level: str,
                exclude: Sequence[str] = ()) -> dict:
    """智能路由：返回排序后的候选通道与最优选择。"""
    candidates = []
    for channel in channels:
        if channel["code"] in exclude:
            continue
        result = score_channel(channel, order, risk_level)
        candidates.append({**channel, **result})
    candidates.sort(key=lambda item: -item["score"])
    eligible = [item for item in candidates if item["eligible"]]
    return {
        "candidates": candidates,
        "selected": eligible[0] if eligible else None,
        "excluded": [item for item in candidates if not item["eligible"]],
    }


def process_order(order: dict, channels: Sequence[dict], risk_score: float,
                  risk_level: str, rng: random.Random | None = None,
                  inject_failure_rate: float = 0.0) -> dict:
    """完整处理一笔支付订单，返回最终状态与全链路事件。

    该函数是纯逻辑实现（不依赖数据库），便于单元测试与批量回放。

    `inject_failure_rate`：故障演练注入概率（0~1）。设为 0 时按通道真实成功率模拟；
    演示「失败重试 + 自动补偿」能力时可临时调高（前端提供「通道故障演练」开关）。
    """
    rng = rng or random.Random(2026)
    events: List[dict] = []
    started = time.perf_counter()

    def log(stage: str, detail: str, **extra) -> None:
        events.append({"ts": time.strftime("%H:%M:%S"), "stage": stage, "detail": detail, **extra})

    log("接入", f"交易接入成功：{order['merchantName']} {order['amount']:.2f} {order['currency']}"
                f" → {order['destRegion']}")

    # ---------------- 风控前置 ----------------
    action, action_label = risk_action(risk_score)
    log("风控", f"风险评分 {risk_score:.3f}（{risk_level}）→ {action_label}", action=action)
    if action in ("block", "manual"):
        status = "blocked" if action == "block" else "manual"
        log("处置", "订单已拦截，未进入支付链路" if action == "block" else "订单转人工合规审核")
        return {
            "status": status,
            "channel": "",
            "channelName": "",
            "attempts": 0,
            "compensated": False,
            "failureReason": "风控拦截" if action == "block" else "转人工审核",
            "events": events,
            "durationMs": int((time.perf_counter() - started) * 1000) + rng.randint(20, 60),
            "riskAction": action,
            "routeScore": 0.0,
        }

    # ---------------- 智能路由 ----------------
    plan = route_order(order, channels, risk_level)
    if plan["selected"] is None:
        log("路由", "无可用通道：所有候选均被排除（限额/币种/目的地/合规限制）")
        return {
            "status": "failed",
            "channel": "",
            "channelName": "",
            "attempts": 0,
            "compensated": True,
            "failureReason": "无可用通道",
            "events": events,
            "durationMs": int((time.perf_counter() - started) * 1000) + rng.randint(30, 90),
            "riskAction": action,
            "routeScore": 0.0,
        }

    selected = plan["selected"]
    log(
        "路由",
        f"智能路由选中「{selected['name']}」（综合得分 {selected['score']:.4f}，"
        f"候选 {len([c for c in plan['candidates'] if c['eligible']])} 条）",
        channel=selected["code"],
    )

    # ---------------- 处理 + 重试 + 补偿 ----------------
    attempts = 0
    used: List[str] = []
    failure_reason = ""
    while attempts <= MAX_RETRY:
        attempts += 1
        channel = selected if attempts == 1 else _next_channel(order, channels, risk_level, used)
        if channel is None:
            failure_reason = "备用通道耗尽"
            break
        used.append(channel["code"])
        log("处理", f"第 {attempts} 次尝试经「{channel['name']}」提交清算", channel=channel["code"])

        # 结果模拟：以通道历史成功率为概率，并叠加订单金额因子与故障演练注入
        success_probability = channel["successRate"] - (0.08 if order["amount"] > channel["singleLimit"] * 0.8 else 0)
        if inject_failure_rate > 0:
            success_probability = min(success_probability, 1 - inject_failure_rate)
        if rng.random() < success_probability:
            log("成功", f"清算成功，预计 {channel['avgLatencyMs']}ms 内到账", channel=channel["code"])
            return {
                "status": "retrying" if attempts > 1 else "success",
                "channel": channel["code"],
                "channelName": channel["name"],
                "attempts": attempts,
                "compensated": False,
                "failureReason": "",
                "events": events,
                "durationMs": int((time.perf_counter() - started) * 1000)
                + channel["avgLatencyMs"] // 10 * attempts,
                "riskAction": action,
                "routeScore": channel.get("score", 0.0),
            }

        failure_reason = rng.choice(["通道网络超时", "对方行拒付", "通道限额触发", "报文校验失败"])
        log("失败", f"第 {attempts} 次尝试失败：{failure_reason}", channel=channel["code"], level="warning")
        if attempts <= MAX_RETRY:
            backoff = RETRY_BACKOFF_MS[min(attempts - 1, len(RETRY_BACKOFF_MS) - 1)]
            log("重试", f"{backoff}ms 后切换备用通道重试（已排除 {'、'.join(used)}）", level="warning")

    # ---------------- 自动补偿 ----------------
    log(
        "补偿",
        f"重试 {attempts - 1} 次后仍未成功，触发自动补偿：生成补偿单并改道重发/原路退回（原因：{failure_reason}）",
        level="danger",
    )
    return {
        "status": "compensated",
        "channel": used[-1] if used else "",
        "channelName": "",
        "attempts": attempts,
        "compensated": True,
        "failureReason": failure_reason or "处理失败",
        "events": events,
        "durationMs": int((time.perf_counter() - started) * 1000) + 2400,
        "riskAction": action,
        "routeScore": selected["score"],
    }


def _next_channel(order: dict, channels: Sequence[dict], risk_level: str,
                  used: Sequence[str]) -> dict | None:
    """重试时选择备用通道（排除已失败通道）。"""
    plan = route_order(order, channels, risk_level, exclude=list(used))
    return plan["selected"]


def route_preview(order: dict, channels: Sequence[dict], risk_level: str = "low") -> dict:
    """路由预演：展示所有候选通道的评分与排除原因（用于前端「通道选择」面板）。"""
    plan = route_order(order, channels, risk_level)
    return {
        "selected": plan["selected"]["code"] if plan["selected"] else None,
        "selectedName": plan["selected"]["name"] if plan["selected"] else None,
        "candidates": [
            {
                "code": item["code"],
                "name": item["name"],
                "score": item["score"],
                "eligible": item["eligible"],
                "reason": item["reason"],
                "breakdown": item.get("breakdown", {}),
                "feeRate": item["feeRate"],
                "successRate": item["successRate"],
                "avgLatencyMs": item["avgLatencyMs"],
                "status": item["status"],
            }
            for item in plan["candidates"]
        ],
        "weights": ROUTE_WEIGHTS,
    }


def summarize(orders: Sequence[dict]) -> Dict[str, object]:
    """汇总支付链路指标。

    口径说明（避免把风控拦截算作「支付失败」）：
    - `successRate`：**进入支付链路的订单**中成功的比例（分母不含风控拦截/转人工）；
    - `straightThroughRate`：全量订单中「一次通过、无需重试」的比例（直通率）；
    - `riskBlockRate`：风控拦截 + 转人工占比（体现合规前置的强度）。
    """
    total = len(orders)
    if not total:
        return {"total": 0}
    success = [item for item in orders if item["status"] in ("success", "retrying")]
    failed = [item for item in orders if item["status"] in ("failed", "compensated")]
    blocked = [item for item in orders if item["status"] == "blocked"]
    manual = [item for item in orders if item["status"] == "manual"]
    retried = [item for item in orders if item["attempts"] > 1]
    compensated = [item for item in orders if item["compensated"]]
    processed = len(success) + len(failed)

    channel_distribution: Dict[str, dict] = {}
    for item in orders:
        if not item["channel"]:
            continue
        bucket = channel_distribution.setdefault(item["channel"], {"code": item["channel"], "count": 0, "amount": 0.0})
        bucket["count"] += 1
        bucket["amount"] += item["amount"]

    # 逐状态计数（供前端绘制精确的状态分布图，而不是只给 4 个合并桶）
    status_counts: Dict[str, int] = {}
    for item in orders:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

    durations = [item["durationMs"] for item in orders if item["durationMs"]]
    return {
        "total": total,
        "countedOrders": total,
        "scope": f"最近 {total} 笔订单（统计上限 500 笔）",
        "processedCount": processed,
        "successCount": len(success),
        "failedCount": len(failed),
        "blockedCount": len(blocked),
        "manualCount": len(manual),
        "successRate": round(len(success) / processed, 4) if processed else 0.0,
        "straightThroughRate": round(len([item for item in success if item["attempts"] <= 1]) / total, 4),
        "retryRate": round(len(retried) / processed, 4) if processed else 0.0,
        "compensationRate": round(len(compensated) / processed, 4) if processed else 0.0,
        "riskBlockRate": round((len(blocked) + len(manual)) / total, 4),
        "avgDurationMs": round(sum(durations) / len(durations), 1) if durations else 0,
        "p95DurationMs": sorted(durations)[int(len(durations) * 0.95) - 1] if len(durations) > 1 else 0,
        "totalAmount": round(sum(item["amount"] for item in orders), 2),
        "channelDistribution": sorted(channel_distribution.values(), key=lambda item: -item["count"]),
        "statusDistribution": sorted(
            [{"status": key, "count": value} for key, value in status_counts.items()],
            key=lambda item: -item["count"],
        ),
        # 自动化率 = 无需人工介入即可闭环的比例（成功 + 失败补偿 + 风控自动拦截）
        "automationRate": round((len(success) + len(compensated) + len(blocked)) / total, 4),
    }
