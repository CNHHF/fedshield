# -*- coding: utf-8 -*-
"""AI 风控合规智能大脑接口（/api/brain）。

对应赛题「面向全球支付场景的 AI 驱动风控合规智能大脑框架」：
把平台六大功能模块映射为**脑区图谱**（Brain Atlas），并以实时业务数据驱动
「感知输入 → 脑区计算 → 决策输出」的数据流动画，形成可视化展板。

- 感知层（sensory）：全球交易流、监管制裁清单、商户主数据、法规更新
- 脑区（cortex）：联合风控决策核、合规判断核、密文计算核、隐私预算调度核、
                数据血缘记忆核、联盟链存证核
- 输出层（motor）：风险评分与标签、拦截与告警指令、监管合规报告

各区负载（load 0~1）由真实业务指标折算，前端据此调整节点尺寸与颜色深浅，
脉冲动画的流量来自实际数据规模，而不是写死的演示值。
"""

from __future__ import annotations

from flask import Blueprint

from ..compliance import regulation_lib
from ..extensions import db
from ..models import (
    Alert,
    AuditLog,
    BudgetItem,
    ChainBlock,
    CollaborationNode,
    ComplianceReport,
    ComplianceRule,
    ComputeTask,
    DataGrant,
    Dataset,
    LineageLink,
    LineageNode,
    SanctionEntry,
    Transaction,
    now,
)
from ..utils.deps import auth_required
from ..utils.response import ok

bp = Blueprint("brain", __name__, url_prefix="/api/brain")

# 画布坐标系：1000 × 620（前端按容器等比缩放）
CANVAS = {"width": 1000, "height": 620}

# 脑区图谱：坐标经过人工排布，形成「左右半球 + 中央核团」的脑机结构
BRAIN_ATLAS = [
    # ---------------- 感知输入层（左） ----------------
    {"id": "src_tx", "name": "全球交易流", "group": "sensory", "x": 96, "y": 128,
     "desc": "各地区节点跨境交易明细（金额、笔数、商品类别）"},
    {"id": "src_sanction", "name": "监管制裁清单", "group": "sensory", "x": 96, "y": 276,
     "desc": "OFAC / 联合国 / 欧盟制裁清单，每日同步并密文化"},
    {"id": "src_merchant", "name": "商户主数据", "group": "sensory", "x": 96, "y": 424,
     "desc": "商户实名、税号、结算账户等 P1/P2 级数据"},
    {"id": "src_regulation", "name": "全球法规更新", "group": "sensory", "x": 96, "y": 556,
     "desc": "全球数据隐私法规库，新规发布后转化为自动化规则"},

    # ---------------- 脑区（中央核团） ----------------
    {"id": "core_risk", "name": "联合风控决策核", "group": "cortex", "x": 372, "y": 158,
     "desc": "横向联邦学习联合建模，输出风险评分与标签"},
    {"id": "core_compliance", "name": "合规判断核", "group": "cortex", "x": 628, "y": 158,
     "desc": "规则引擎自动校验跨境传输、授权与脱敏合规性"},
    {"id": "core_crypto", "name": "密文计算核", "group": "cortex", "x": 500, "y": 300,
     "desc": "Paillier 同态加密 / RSA 盲签名 / SM4 国密，数据可用不可见"},
    {"id": "core_budget", "name": "隐私预算调度核", "group": "cortex", "x": 372, "y": 442,
     "desc": "按场景动态分配 ε，超阈值预警，防止原始数据被反推"},
    {"id": "core_lineage", "name": "数据血缘记忆核", "group": "cortex", "x": 628, "y": 442,
     "desc": "全链路流转图谱与溯源审计，支撑监管调证"},
    {"id": "core_chain", "name": "联盟链存证核", "group": "cortex", "x": 500, "y": 556,
     "desc": "Hyperledger Fabric 语义的哈希存证，操作不可篡改"},

    # ---------------- 决策输出层（右） ----------------
    {"id": "out_score", "name": "风险评分与标签", "group": "motor", "x": 906, "y": 190,
     "desc": "输出商户风险评分、风险等级与命中规则"},
    {"id": "out_action", "name": "拦截与告警指令", "group": "motor", "x": 906, "y": 330,
     "desc": "实时拦截高风险交易、触发分级告警与整改清单"},
    {"id": "out_report", "name": "监管合规报告", "group": "motor", "x": 906, "y": 470,
     "desc": "自动生成 12 类合规报告并对接监管机构归档"},
]

# 数据流向（脉冲动画沿这些链路流动）
BRAIN_FLOWS = [
    # 感知 → 脑区
    {"source": "src_tx", "target": "core_risk", "label": "交易特征"},
    {"source": "src_tx", "target": "core_crypto", "label": "密文上传"},
    {"source": "src_sanction", "target": "core_crypto", "label": "清单密文化"},
    {"source": "src_sanction", "target": "core_compliance", "label": "制裁核验"},
    {"source": "src_merchant", "target": "core_risk", "label": "商户画像"},
    {"source": "src_merchant", "target": "core_budget", "label": "分级标注"},
    {"source": "src_regulation", "target": "core_compliance", "label": "规则下发"},
    {"source": "src_regulation", "target": "core_lineage", "label": "合规标签"},

    # 脑区之间的协同（神经通路）
    {"source": "core_crypto", "target": "core_risk", "label": "密文聚合"},
    {"source": "core_budget", "target": "core_crypto", "label": "预算授权"},
    {"source": "core_lineage", "target": "core_compliance", "label": "流转轨迹"},
    {"source": "core_compliance", "target": "core_chain", "label": "校验结论"},
    {"source": "core_risk", "target": "core_lineage", "label": "特征血缘"},
    {"source": "core_crypto", "target": "core_chain", "label": "参数摘要"},

    # 脑区 → 决策输出
    {"source": "core_risk", "target": "out_score", "label": "评分下发"},
    {"source": "core_compliance", "target": "out_action", "label": "阻断/放行"},
    {"source": "core_chain", "target": "out_report", "label": "存证编号"},
    {"source": "core_lineage", "target": "out_report", "label": "溯源证据"},
    {"source": "core_budget", "target": "out_action", "label": "额度熔断"},
]

GROUP_LABELS = {
    "sensory": "感知输入层",
    "cortex": "脑区计算层",
    "motor": "决策输出层",
}


def _count(model, *criteria) -> int:
    query = db.session.query(db.func.count(model.id))
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def _sum(model, column) -> float:
    return float(db.session.query(db.func.coalesce(db.func.sum(column), 0.0)).scalar() or 0.0)


def _ratio(value: float, total: float, default: float = 0.2) -> float:
    """折算负载比例（0.05~1），用于节点尺寸与颜色深浅。"""
    if not total:
        return default
    return round(max(0.05, min(1.0, value / total)), 4)


def collect_brain_metrics() -> dict:
    """采集各脑区的实时业务指标与负载。"""
    tx_count = _count(Transaction)
    tx_amount = _sum(Transaction, Transaction.amount)
    sanction_count = _count(SanctionEntry)
    dataset_count = _count(Dataset)
    regulation_stats = regulation_lib.coverage_stats()

    task_total = _count(ComputeTask)
    task_finished = _count(ComputeTask, ComputeTask.status == "finished")
    last_task = (
        ComputeTask.query.filter(ComputeTask.status == "finished")
        .order_by(ComputeTask.finishedAt.desc())
        .first()
    )
    metrics_result = (last_task.result or {}).get("metrics", {}) if last_task else {}
    auc = metrics_result.get("auc")
    miss_rate = metrics_result.get("missRate")

    rule_total = _count(ComplianceRule)
    rule_enabled = _count(ComplianceRule, ComplianceRule.enabled.is_(True))
    rule_hits = int(db.session.query(db.func.coalesce(db.func.sum(ComplianceRule.hitCount), 0)).scalar() or 0)

    budget_total = _sum(BudgetItem, BudgetItem.total)
    budget_used = _sum(BudgetItem, BudgetItem.used)

    lineage_nodes = _count(LineageNode)
    lineage_links = _count(LineageLink)

    chain_blocks = _count(ChainBlock)
    audit_total = _count(AuditLog)

    alert_total = _count(Alert)
    alert_open = _count(Alert, Alert.status == "open")
    report_total = _count(ComplianceReport)
    grant_active = len([g for g in DataGrant.query.all() if g.computed_status == "active"])
    node_online = _count(CollaborationNode, CollaborationNode.status == "online")

    return {
        "src_tx": {
            "load": _ratio(tx_count, 3000),
            "metrics": [
                {"label": "交易笔数", "value": tx_count, "unit": "笔"},
                {"label": "金额合计", "value": round(tx_amount / 1e4, 2), "unit": "万元"},
            ],
        },
        "src_sanction": {
            "load": _ratio(sanction_count, 120),
            "metrics": [
                {"label": "清单条目", "value": sanction_count, "unit": "条"},
                {"label": "清单类型", "value": 3, "unit": "类"},
            ],
        },
        "src_merchant": {
            "load": _ratio(dataset_count, 12),
            "metrics": [
                {"label": "数据集", "value": dataset_count, "unit": "个"},
                {"label": "P1 级数据集", "value": _count(Dataset, Dataset.level == "P1"), "unit": "个"},
            ],
        },
        "src_regulation": {
            "load": _ratio(regulation_stats["total"], 250),
            "metrics": [
                {"label": "法规条目", "value": regulation_stats["total"], "unit": "条"},
                {"label": "覆盖辖区", "value": regulation_stats["jurisdictions"], "unit": "个"},
            ],
        },
        "core_risk": {
            "load": _ratio(task_total, 12),
            "metrics": [
                {"label": "建模任务", "value": f"{task_finished}/{task_total}", "unit": "完成/总"},
                {"label": "模型 AUC", "value": auc if auc is not None else "—", "unit": ""},
                {"label": "漏检率", "value": miss_rate if miss_rate is not None else "—", "unit": ""},
            ],
        },
        "core_compliance": {
            "load": _ratio(rule_hits + rule_total * 3, 60),
            "metrics": [
                {"label": "规则条数", "value": f"{rule_enabled}/{rule_total}", "unit": "启用/总"},
                {"label": "规则命中", "value": rule_hits, "unit": "次"},
                {"label": "生效授权", "value": grant_active, "unit": "条"},
            ],
        },
        "core_crypto": {
            "load": _ratio(task_total * 4 + sanction_count, 200),
            "metrics": [
                {"label": "密文运算任务", "value": task_total, "unit": "个"},
                {"label": "同态加密算法", "value": "Paillier-1024", "unit": ""},
                {"label": "国密算法", "value": "SM4-CBC+HMAC", "unit": ""},
            ],
        },
        "core_budget": {
            "load": _ratio(budget_used, budget_total),
            "metrics": [
                {"label": "总预算 ε", "value": round(budget_total, 2), "unit": ""},
                {"label": "已消耗", "value": round(budget_used, 2), "unit": ""},
                {"label": "消耗占比", "value": round(budget_used / budget_total * 100, 1) if budget_total else 0, "unit": "%"},
            ],
        },
        "core_lineage": {
            "load": _ratio(lineage_nodes, 20),
            "metrics": [
                {"label": "血缘节点", "value": lineage_nodes, "unit": "个"},
                {"label": "流转连线", "value": lineage_links, "unit": "条"},
            ],
        },
        "core_chain": {
            "load": _ratio(chain_blocks, 30),
            "metrics": [
                {"label": "区块高度", "value": chain_blocks, "unit": ""},
                {"label": "存证日志", "value": audit_total, "unit": "条"},
                {"label": "共识机制", "value": "Raft", "unit": ""},
            ],
        },
        "out_score": {
            "load": _ratio(task_total, 10),
            "metrics": [
                {"label": "风险评分模型", "value": auc if auc is not None else "—", "unit": "AUC"},
                {"label": "风险等级", "value": "高/中/低", "unit": "三级"},
            ],
        },
        "out_action": {
            "load": _ratio(alert_total, 12),
            "metrics": [
                {"label": "预警总数", "value": alert_total, "unit": "条"},
                {"label": "未闭环", "value": alert_open, "unit": "条"},
            ],
        },
        "out_report": {
            "load": _ratio(report_total, 10),
            "metrics": [
                {"label": "合规报告", "value": report_total, "unit": "份"},
                {"label": "报告模板", "value": 12, "unit": "类"},
            ],
        },
    }


@bp.get("/overview")
@auth_required
def overview():
    """AI 风控大脑总览：脑区图谱 + 数据流 + 关键指标 + 实时脉冲事件。"""
    metrics = collect_brain_metrics()

    regions = []
    for item in BRAIN_ATLAS:
        payload = metrics.get(item["id"], {})
        load = float(payload.get("load", 0.2))
        regions.append(
            {
                **item,
                "groupLabel": GROUP_LABELS.get(item["group"], item["group"]),
                "load": load,
                "status": "busy" if load >= 0.7 else ("active" if load >= 0.35 else "idle"),
                # 前端据此设置节点尺寸（脑区越大代表当前负载越高）
                "symbolSize": round(26 + load * 26, 1),
                "metrics": payload.get("metrics", []),
            }
        )

    # 数据流的脉冲强度：由目标脑区的负载决定，负载越高脉冲越密集
    region_load = {item["id"]: item["load"] for item in regions}
    flows = [
        {
            **flow,
            "value": round(0.4 + region_load.get(flow["target"], 0.3) * 0.6, 3),
            "throughput": int(30 + region_load.get(flow["target"], 0.3) * 260),
        }
        for flow in BRAIN_FLOWS
    ]

    # 实时脉冲事件（取最近审计日志，作为「神经脉冲」展示）
    events = []
    for log in AuditLog.query.order_by(AuditLog.ts.desc()).limit(12).all():
        events.append(
            {
                "ts": log.ts.strftime("%H:%M:%S"),
                "actor": log.actor,
                "action": log.action,
                "target": log.target,
                "result": log.result,
                "detail": log.detail or "",
                "chainTxId": log.chainTxId,
            }
        )

    last_task = (
        ComputeTask.query.filter(ComputeTask.status == "finished")
        .order_by(ComputeTask.finishedAt.desc())
        .first()
    )
    result = (last_task.result or {}) if last_task else {}
    homomorphic = result.get("homomorphic") or {}
    node_online = _count(CollaborationNode, CollaborationNode.status == "online")
    chain_blocks = _count(ChainBlock)
    audit_total = _count(AuditLog)
    performance_items = []
    if result:
        performance_items = [
            {"label": "密文聚合耗时", "value": homomorphic.get("aggregationMs", "—"), "unit": "ms"},
            {"label": "密文份数", "value": homomorphic.get("ciphertexts", "—"), "unit": "份"},
            {"label": "传输量压缩", "value": (result.get("traffic") or {}).get("savedPercent", "—"), "unit": "%"},
        ]

    kpis = [
        {"key": "regions", "label": "在线脑区", "value": len(regions), "unit": "个",
         "sub": f"感知 {len([r for r in regions if r['group'] == 'sensory'])} · "
                f"计算 {len([r for r in regions if r['group'] == 'cortex'])} · "
                f"输出 {len([r for r in regions if r['group'] == 'motor'])}"},
        {"key": "flows", "label": "数据通路", "value": len(flows), "unit": "条",
         "sub": "感知→脑区→决策全链路脉冲"},
        {"key": "nodes", "label": "在线协作节点", "value": node_online, "unit": "个",
         "sub": "跨境多活节点，TLS1.3 双向认证"},
        {"key": "tasks", "label": "大脑决策任务", "value": last_task.code if last_task else 0, "unit": "",
         "sub": f"已完成 {result.get('metrics', {}).get('auc', '—')} AUC 的联合建模" if result else "尚未执行联邦建模"},
        {"key": "audit", "label": "神经脉冲（审计）", "value": audit_total, "unit": "条",
         "sub": f"其中上链存证 {chain_blocks} 笔"},
    ]

    return ok(
        {
            "canvas": CANVAS,
            "title": "AI 风控合规智能大脑",
            "subtitle": "面向全球支付场景 · 数据可用不可见 · 合规可追溯",
            "groups": [{"code": code, "name": name} for code, name in GROUP_LABELS.items()],
            "regions": regions,
            "flows": flows,
            "kpis": kpis,
            "events": events,
            "performance": performance_items,
            "updatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@bp.get("/atlas")
@auth_required
def atlas():
    """脑区图谱静态定义（供前端布局调试或离线渲染使用）。"""
    return ok({"canvas": CANVAS, "regions": BRAIN_ATLAS, "flows": BRAIN_FLOWS,
               "groups": [{"code": code, "name": name} for code, name in GROUP_LABELS.items()]})
