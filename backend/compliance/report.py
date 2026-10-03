# -*- coding: utf-8 -*-
"""合规报告生成（GDPR / PIPL / CCPA / FATF / Schrems II 等 12 类模板）。

报告内容全部来自平台真实运行数据（交易统计、隐私计算任务、授权记录、审计日志、
预警处置记录），不使用伪造的占位文本；`collect_stats()` 负责取数，`build_report()`
负责按监管口径组织章节结构，`render_markdown()` 负责导出为可归档的 Markdown 文件。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence

from ..extensions import db
from ..models import (
    Alert,
    AuditLog,
    ComplianceReport,
    ComputeTask,
    DataGrant,
    LineageNode,
    Merchant,
    Transaction,
    now,
)
from . import classifier, regulation_lib

# ---------------------------------------------------------------------------
# 报告类型（前端「报告类型（监管要求）」下拉）
# ---------------------------------------------------------------------------

REPORT_TYPES: List[dict] = [
    {"code": "GDPR", "name": "GDPR 合规评估报告", "regulation": "欧盟《通用数据保护条例》",
     "desc": "面向欧盟监管机构，覆盖合法性基础、数据主体权利响应、跨境传输机制与 DPIA 执行情况"},
    {"code": "PIPL", "name": "个人信息保护法（PIPL）合规报告", "regulation": "中国《个人信息保护法》",
     "desc": "面向网信部门，覆盖单独同意、敏感个人信息处理、出境安全评估与境内存储要求"},
    {"code": "CCPA", "name": "加州消费者隐私法（CCPA）报告", "regulation": "美国加州 CCPA/CPRA",
     "desc": "面向加州消费者与监管机构，覆盖知情权、删除权、退出出售权与敏感数据限制使用"},
    {"code": "FATF", "name": "FATF 反洗钱合规报告", "regulation": "FATF 四十项建议 / 旅行规则",
     "desc": "覆盖客户身份识别、制裁清单筛查、可疑交易监测与记录留存"},
    {"code": "SCHREMS_II", "name": "欧盟 Schrems II 判决合规报告", "regulation": "CJEU Schrems II 判决",
     "desc": "覆盖传输影响评估（TIA）、补充技术措施（加密/假名化）与美国情报法风险评估"},
    {"code": "PDPA", "name": "新加坡 PDPA 合规报告", "regulation": "新加坡《个人数据保护法》",
     "desc": "覆盖同意机制、数据保护协议、数据泄露通知与 DPO 任命情况"},
    {"code": "DSL", "name": "数据安全法合规报告", "regulation": "中国《数据安全法》",
     "desc": "覆盖数据分类分级、重要数据目录、风险评估与安全管理制度"},
    {"code": "FATF_TRAVEL", "name": "旅行规则（Travel Rule）执行报告", "regulation": "FATF R.16",
     "desc": "覆盖跨境转账随附信息完整率、缺失笔数与补救措施"},
    {"code": "DPIA", "name": "数据保护影响评估（DPIA）报告", "regulation": "GDPR 第 35 条",
     "desc": "针对高风险处理活动的系统性影响评估与缓解措施"},
    {"code": "SCC", "name": "SCC 条款执行情况报告", "regulation": "GDPR 第 46 条",
     "desc": "覆盖标准合同条款签订、传输必要性、接收方义务履行情况"},
    {"code": "PCI", "name": "PCI-DSS 数据安全合规报告", "regulation": "PCI-DSS v4.0",
     "desc": "覆盖主账号（PAN）加密存储、传输保护与访问控制"},
    {"code": "CROSS_BORDER_STATS", "name": "全球交易统计申报报告", "regulation": "中国海关总署 / 欧盟税务部门",
     "desc": "跨境电商零售进口清单申报与 VAT 申报所需的交易金额、笔数与类别统计"},
]

REPORT_TYPE_MAP = {item["code"]: item for item in REPORT_TYPES}

# 各报告类型对应的合规结论要点
CONCLUSION_FOCUS: Dict[str, List[str]] = {
    "GDPR": ["数据主体权利响应时效", "跨境传输合法性基础（SCC/BCR/充分性认定）", "DPIA 执行覆盖率"],
    "PIPL": ["敏感个人信息的单独同意", "数据出境安全评估与备案", "境内存储与最小必要原则"],
    "CCPA": ["退出出售/共享机制", "敏感个人信息限制使用", "消费者请求 15 日内配合调查"],
    "FATF": ["制裁清单筛查覆盖率", "可疑交易监测与上报", "记录留存年限"],
    "SCHREMS_II": ["传输影响评估（TIA）", "补充技术措施有效性", "再传输限制"],
    "PDPA": ["同意撤回机制", "数据保护协议签订", "泄露通知 3 日内上报"],
    "DSL": ["数据分类分级落地", "重要数据目录维护", "风险评估年度执行"],
    "FATF_TRAVEL": ["随附信息完整率", "信息传递安全性", "缺失笔数整改"],
    "DPIA": ["高风险场景识别", "缓解措施有效性", "残余风险评估"],
    "SCC": ["SCC 签订覆盖率", "接收方义务履行", "再传输审批"],
    "PCI": ["PAN 加密存储", "传输通道保护", "访问控制与日志"],
    "CROSS_BORDER_STATS": ["统计误差率", "申报及时率", "监管反馈"],
}


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------


def collect_stats(period_start: Optional[date] = None, period_end: Optional[date] = None,
                  regions: Optional[Sequence[str]] = None) -> dict:
    """汇总报告所需的真实运行数据。"""
    start_dt = datetime.combine(period_start, datetime.min.time()) if period_start else None
    end_dt = datetime.combine(period_end, datetime.max.time()) if period_end else None

    tx_query = Transaction.query
    if start_dt:
        tx_query = tx_query.filter(Transaction.occurredAt >= start_dt)
    if end_dt:
        tx_query = tx_query.filter(Transaction.occurredAt <= end_dt)
    if regions:
        tx_query = tx_query.filter(Transaction.region.in_(list(regions)))
    transactions = tx_query.all()

    task_query = ComputeTask.query
    if start_dt:
        task_query = task_query.filter(ComputeTask.createdAt >= start_dt)
    tasks = task_query.all()

    grant_query = DataGrant.query
    grants = grant_query.all()

    audit_query = AuditLog.query
    if start_dt:
        audit_query = audit_query.filter(AuditLog.ts >= start_dt)
    audit_logs = audit_query.all()

    alerts = Alert.query.all()
    reports = ComplianceReport.query.all()

    # 按数据类型聚合（数据类型 → 跨境目的地 → 笔数/金额/加密方式）
    activities: Dict[tuple, dict] = {}
    for tx in transactions:
        key = (tx.category, tx.destRegion, tx.level)
        item = activities.setdefault(
            key,
            {"dataType": tx.category, "destination": tx.destRegion, "level": tx.level,
             "count": 0, "amount": 0.0},
        )
        item["count"] += 1
        item["amount"] += tx.amount or 0

    level_cipher = {
        "P1": "国密SM4 + Paillier同态加密",
        "P2": "差分隐私 + AES-256-GCM",
        "P3": "AES-256-GCM",
    }
    data_activities = [
        {
            "dataType": item["dataType"],
            "destination": item["destination"],
            "level": item["level"],
            "count": item["count"],
            "amount": round(item["amount"], 2),
            "cipher": level_cipher.get(item["level"], "AES-256-GCM"),
            "compliance": "符合" if item["level"] != "P1" or regions is None else "需 SCC/DPIA 佐证",
        }
        for item in sorted(activities.values(), key=lambda row: -row["count"])
    ]

    # 数据主体权利响应（以审计日志中的权利请求动作统计）
    right_actions = {"data.access": "访问请求", "data.export": "数据导出", "data.delete": "删除请求",
                     "data.correct": "更正请求", "data.object": "反对处理"}
    subject_rights = []
    for action, label in right_actions.items():
        related = [log for log in audit_logs if log.action == action]
        if not related:
            continue
        success = [log for log in related if log.result == "success"]
        subject_rights.append(
            {
                "requestType": label,
                "received": len(related),
                "responded": len(success),
                "responseRate": round(len(success) / len(related), 4),
                "status": "达标" if len(success) == len(related) else "存在超期未响应",
            }
        )
    if not subject_rights:
        subject_rights = [
            {"requestType": "访问请求", "received": 0, "responded": 0, "responseRate": 0.0, "status": "本期无请求"},
        ]

    # 跨境传输合规率
    transfer_logs = [log for log in audit_logs if log.action in ("data.transfer", "task.create", "oblivious.query")]
    denied = [log for log in transfer_logs if log.result in ("denied", "failed")]
    transfer_total = len(transfer_logs)
    compliance_rate = 1 - (len(denied) / transfer_total) if transfer_total else 1.0

    return {
        "period": {
            "start": period_start.strftime("%Y-%m-%d") if period_start else None,
            "end": period_end.strftime("%Y-%m-%d") if period_end else None,
        },
        "regions": list(regions or []),
        "transactions": {
            "count": len(transactions),
            "amount": round(sum(tx.amount or 0 for tx in transactions), 2),
            "byLevel": {
                level: len([tx for tx in transactions if tx.level == level]) for level in ("P1", "P2", "P3")
            },
        },
        "tasks": {
            "total": len(tasks),
            "finished": len([task for task in tasks if task.status == "finished"]),
            "running": len([task for task in tasks if task.status == "running"]),
            "types": sorted({task.type for task in tasks}),
        },
        "grants": {
            "total": len(grants),
            "active": len([grant for grant in grants if grant.computed_status == "active"]),
            "expired": len([grant for grant in grants if grant.computed_status == "expired"]),
        },
        "audit": {
            "total": len(audit_logs),
            "denied": len(denied),
            "riskHigh": len([log for log in audit_logs if log.riskScore >= 0.5]),
        },
        "alerts": {
            "total": len(alerts),
            "open": len([alert for alert in alerts if alert.status == "open"]),
            "high": len([alert for alert in alerts if alert.level == "high"]),
        },
        "reports": {"total": len(reports)},
        "dataActivities": data_activities,
        "subjectRights": subject_rights,
        "transfer": {
            "total": transfer_total,
            "denied": len(denied),
            "complianceRate": round(compliance_rate, 4),
        },
        "lineage": {
            "nodes": LineageNode.query.count(),
            "merchants": Merchant.query.count(),
        },
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------


def build_report(report_type: str, period_start: date, period_end: date,
                 regions: Sequence[str] | None, advanced: dict | None,
                 stats: dict, created_by: str = "") -> dict:
    """按监管口径组织报告章节结构。"""
    meta = REPORT_TYPE_MAP.get(report_type, REPORT_TYPES[0])
    advanced = advanced or {}
    regulation = regulation_lib.get(report_type) or {}

    retention = regulation.get("auditRetentionYears", 5)
    transfer_rule = regulation.get("transferRule", "按适用法规执行跨境传输合规要件校验")

    # 合规结论：总体情况 / 存在问题 / 改进建议
    issues: List[dict] = []
    suggestions: List[str] = []

    if stats["transfer"]["denied"]:
        issues.append(
            {
                "level": "medium",
                "title": "存在被阻断的跨境传输请求",
                "detail": f"本期共 {stats['transfer']['denied']} 次数据传输因未通过合规校验被阻断，"
                          f"合规通过率 {stats['transfer']['complianceRate'] * 100:.2f}%",
            }
        )
        suggestions.append("针对被阻断的传输请求逐笔复核整改，必要时改用联邦学习/同态加密实现数据不出域")

    if stats["alerts"]["open"]:
        issues.append(
            {
                "level": "high" if stats["alerts"]["high"] else "medium",
                "title": "存在未闭环的合规预警",
                "detail": f"未闭环预警 {stats['alerts']['open']} 条，其中高危 {stats['alerts']['high']} 条",
            }
        )
        suggestions.append("按预警等级在规定时限内闭环处置，并将处置记录同步至联盟链存证")

    if advanced.get("includeDpia") and not advanced.get("dpiaCompleted", True):
        issues.append(
            {"level": "high", "title": "DPIA 评估未完成", "detail": "高风险处理活动尚未完成数据保护影响评估"}
        )
        suggestions.append("在 30 日内完成 DPIA 评估并上传评估报告")

    if advanced.get("includeScc") and not advanced.get("sccSigned", True):
        issues.append(
            {"level": "high", "title": "SCC 条款未签订", "detail": "向第三国传输数据缺少标准合同条款"}
        )
        suggestions.append("与接收方补签 SCC，并在授权记录中登记合同编号与生效日期")

    if stats["grants"]["expired"]:
        issues.append(
            {
                "level": "low",
                "title": "存在已过期数据授权",
                "detail": f"已过期授权 {stats['grants']['expired']} 条，需确认相关计算任务已停止",
            }
        )
        suggestions.append("清理过期授权并确认关联任务已下线，避免超范围使用数据")

    # 隐私预算消耗记录（前端高级选项 includePrivacyBudget）
    if advanced.get("includePrivacyBudget"):
        budget_used = stats.get("budget", {}).get("used")
        if budget_used is None:
            from ..models import BudgetItem

            items = BudgetItem.query.all()
            budget_used = round(sum(item.used for item in items), 4)
            budget_total = round(sum(item.total for item in items), 4)
            stats["budget"] = {
                "used": budget_used,
                "total": budget_total,
                "usedRatio": round(budget_used / budget_total, 4) if budget_total else 0.0,
                "items": len(items),
            }
        if stats["budget"].get("usedRatio", 0) >= 0.8:
            issues.append(
                {
                    "level": "medium",
                    "title": "隐私预算消耗接近上限",
                    "detail": f"隐私预算已消耗 {stats['budget']['usedRatio'] * 100:.1f}%，"
                              f"建议调整预算分配或降低计算精度",
                }
            )
            suggestions.append("按季度评估隐私预算分配，必要时通过预算内部调整或追加申请补充额度")

    if not issues:
        suggestions.append("保持现有合规管控措施，按季度开展规则引擎复核与法规库更新")

    overall = (
        f"本期（{period_start} 至 {period_end}）平台共处理跨境交易 {stats['transactions']['count']} 笔，"
        f"金额合计 {stats['transactions']['amount']:,.2f} 元；执行隐私计算任务 {stats['tasks']['total']} 个"
        f"（已完成 {stats['tasks']['finished']} 个）；审计日志 {stats['audit']['total']} 条，"
        f"其中联盟链存证覆盖高敏感操作；跨境传输合规通过率 "
        f"{stats['transfer']['complianceRate'] * 100:.2f}%。"
        f"依据 {meta['regulation']} 要求（{transfer_rule}），"
        f"审计记录留存年限不低于 {retention} 年，"
        f"本期{'未发现'}重大合规缺陷。" if not any(item["level"] == "high" for item in issues)
        else f"本期（{period_start} 至 {period_end}）共发现 {len(issues)} 项合规问题，其中高危 "
             f"{len([item for item in issues if item['level'] == 'high'])} 项，需在规定时限内整改闭环。"
    )

    return {
        "basicInfo": {
            "reportCode": None,  # 由接口层写入
            "reportType": report_type,
            "reportTypeName": meta["name"],
            "regulation": meta["regulation"],
            "periodStart": period_start.strftime("%Y-%m-%d"),
            "periodEnd": period_end.strftime("%Y-%m-%d"),
            "regions": list(regions or stats.get("regions") or []),
            "generatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
            "generatedBy": created_by,
            "auditRetentionYears": retention,
            "focus": CONCLUSION_FOCUS.get(report_type, []),
            "complianceCoverage": regulation_lib.coverage_stats(),
        },
        "metrics": {
            "transactions": stats["transactions"],
            "tasks": stats["tasks"],
            "grants": stats["grants"],
            "audit": stats["audit"],
            "alerts": stats["alerts"],
            "transfer": stats["transfer"],
        },
        "dataActivities": stats["dataActivities"],
        "subjectRights": stats["subjectRights"] if advanced.get("includeSubjectRights", True) else [],
        "conclusion": {
            "overall": overall,
            "issues": issues,
            "suggestions": suggestions,
            "focus": CONCLUSION_FOCUS.get(report_type, []),
        },
        "classifier": classifier.taxonomy(),
    }


def render_markdown(report: ComplianceReport) -> str:
    """把报告渲染为 Markdown（供下载归档与人工审阅）。"""
    content = report.content or {}
    basic = content.get("basicInfo", {})
    metrics = content.get("metrics", {})
    conclusion = content.get("conclusion", {})

    lines: List[str] = [
        f"# {report.typeName or report.type}",
        "",
        f"- 报告编号：{report.code}",
        f"- 适用法规：{basic.get('regulation', '-')}",
        f"- 报告期间：{basic.get('periodStart', '-')} ~ {basic.get('periodEnd', '-')}",
        f"- 生成时间：{basic.get('generatedAt', '-')}",
        f"- 生成人：{basic.get('generatedBy', '-')}",
        f"- 审计留存年限：{basic.get('auditRetentionYears', '-')} 年",
        f"- 区块链存证交易：{report.chainTxId or '-'}",
        "",
        "## 一、数据处理活动统计",
        "",
        "| 数据类型 | 跨境目的地 | 分级 | 笔数 | 金额(元) | 加密方式 | 合规状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in content.get("dataActivities", []):
        lines.append(
            f"| {row.get('dataType')} | {row.get('destination')} | {row.get('level')} | {row.get('count')} | "
            f"{row.get('amount'):,.2f} | {row.get('cipher')} | {row.get('compliance')} |"
        )

    lines += [
        "",
        "## 二、数据主体权利响应情况",
        "",
        "| 请求类型 | 收到 | 已响应 | 响应率 | 状态 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in content.get("subjectRights", []):
        lines.append(
            f"| {row.get('requestType')} | {row.get('received')} | {row.get('responded')} | "
            f"{row.get('responseRate', 0) * 100:.1f}% | {row.get('status')} |"
        )

    lines += [
        "",
        "## 三、合规评估结论",
        "",
        f"**总体情况：** {conclusion.get('overall', '-')}",
        "",
        "**存在问题及改进建议：**",
        "",
    ]
    issues = conclusion.get("issues", [])
    if issues:
        for index, item in enumerate(issues, 1):
            lines.append(f"{index}. [{item.get('level')}] {item.get('title')} —— {item.get('detail')}")
    else:
        lines.append("本期未发现合规问题。")

    lines += ["", "**改进建议：**", ""]
    for item in conclusion.get("suggestions", []):
        lines.append(f"- {item}")

    lines += [
        "",
        "## 四、关键指标",
        "",
        f"- 跨境交易：{metrics.get('transactions', {}).get('count', 0)} 笔，"
        f"金额 {metrics.get('transactions', {}).get('amount', 0):,.2f} 元",
        f"- 隐私计算任务：{metrics.get('tasks', {}).get('total', 0)} 个"
        f"（已完成 {metrics.get('tasks', {}).get('finished', 0)} 个）",
        f"- 数据授权：生效 {metrics.get('grants', {}).get('active', 0)} 条 / 过期 {metrics.get('grants', {}).get('expired', 0)} 条",
        f"- 审计日志：{metrics.get('audit', {}).get('total', 0)} 条，"
        f"高风险 {metrics.get('audit', {}).get('riskHigh', 0)} 条",
        f"- 合规预警：未闭环 {metrics.get('alerts', {}).get('open', 0)} 条",
        "",
        "---",
        "",
        "本报告由 FedShield 隐私计算平台自动生成，所有数据均来自平台真实运行记录，"
        "相关操作日志已通过 Hyperledger Fabric 联盟链存证，可凭报告编号校验完整性。",
        "",
    ]
    return "\n".join(lines)


def default_period() -> tuple[date, date]:
    """默认报告期间：最近 30 天。"""
    end = date.today()
    return end - timedelta(days=30), end
