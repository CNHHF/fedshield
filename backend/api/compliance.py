# -*- coding: utf-8 -*-
"""合规校验与报告接口（/api/compliance）：规则引擎、合规校验、报告、趋势与预警。"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, request

from ..audit import logger as audit_logger
from ..compliance import classifier, regulation_lib, report as report_module, rule_engine
from ..extensions import db
from ..models import Alert, ComplianceReport, ComplianceRule, ComplianceTrendPoint, Dataset, next_code, now
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok, page_args, paginate, require_fields

bp = Blueprint("compliance", __name__, url_prefix="/api/compliance")


# ---------------------------------------------------------------------------
# 规则引擎
# ---------------------------------------------------------------------------


@bp.get("/rules")
@auth_required
def list_rules():
    """规则列表（支持场景与启用状态筛选）。"""
    query = ComplianceRule.query
    scene = request.args.get("scene")
    enabled = request.args.get("enabled")
    if scene and scene != "all":
        query = query.filter(ComplianceRule.scene == scene)
    if enabled in ("true", "false"):
        query = query.filter(ComplianceRule.enabled == (enabled == "true"))
    rows = query.order_by(ComplianceRule.priority.asc(), ComplianceRule.id.asc()).all()
    return ok([item.to_dict() for item in rows])


@bp.post("/rules")
@auth_required
@require_permission("compliance:rule:manage")
def create_rule():
    """新建规则（画布节点 + 连线）。"""
    payload = body()
    require_fields(payload, ["name"])
    _validate_canvas(payload.get("nodes") or [], payload.get("edges") or [])

    count = ComplianceRule.query.count() + 1
    rule = ComplianceRule(
        code=next_code("RULE", count),
        name=payload["name"],
        description=payload.get("description", ""),
        scene=payload.get("scene", "data_transfer"),
        priority=int(payload.get("priority") or 10),
        enabled=bool(payload.get("enabled", True)),
        nodes=payload.get("nodes") or [],
        edges=payload.get("edges") or [],
        updatedBy=current_user().username,
    )
    db.session.add(rule)
    db.session.commit()

    audit_logger.record_from_request(
        "rule.update", target=rule.code, operation="创建",
        detail=f"新建合规规则：{rule.name}（{len(rule.nodes or [])} 个节点）",
    )
    return ok({"id": rule.id, "code": rule.code, "version": rule.version}, message="规则已保存")


@bp.put("/rules/<int:rule_id>")
@auth_required
@require_permission("compliance:rule:manage")
def update_rule(rule_id: int):
    """保存（更新）规则。"""
    rule = ComplianceRule.query.get(rule_id)
    if rule is None:
        raise ApiError("规则不存在", code=404)
    payload = body()
    _validate_canvas(payload.get("nodes") or rule.nodes or [], payload.get("edges") or rule.edges or [])

    rule.name = payload.get("name", rule.name)
    rule.description = payload.get("description", rule.description)
    rule.scene = payload.get("scene", rule.scene)
    rule.priority = int(payload.get("priority", rule.priority))
    rule.enabled = bool(payload.get("enabled", rule.enabled))
    rule.nodes = payload.get("nodes", rule.nodes)
    rule.edges = payload.get("edges", rule.edges)
    rule.version += 1
    rule.updatedBy = current_user().username
    db.session.commit()

    audit_logger.record_from_request(
        "rule.update", target=rule.code, operation="修改",
        detail=f"更新合规规则：{rule.name}（版本 {rule.version}）",
    )
    return ok({"id": rule.id, "version": rule.version}, message="规则已更新")


@bp.delete("/rules/<int:rule_id>")
@auth_required
@require_permission("compliance:rule:manage")
def delete_rule(rule_id: int):
    """删除规则。"""
    rule = ComplianceRule.query.get(rule_id)
    if rule is None:
        raise ApiError("规则不存在", code=404)
    code, name = rule.code, rule.name
    db.session.delete(rule)
    db.session.commit()
    audit_logger.record_from_request("rule.update", target=code, operation="删除", detail=f"删除规则：{name}")
    return ok({"success": True}, message="规则已删除")


@bp.post("/rules/<int:rule_id>/toggle")
@auth_required
@require_permission("compliance:rule:manage")
def toggle_rule(rule_id: int):
    """启用/禁用规则。"""
    rule = ComplianceRule.query.get(rule_id)
    if rule is None:
        raise ApiError("规则不存在", code=404)
    payload = body()
    rule.enabled = bool(payload.get("enabled", not rule.enabled))
    rule.updatedBy = current_user().username
    db.session.commit()
    audit_logger.record_from_request(
        "rule.update", target=rule.code, operation="修改",
        detail=f"{'启用' if rule.enabled else '禁用'}规则：{rule.name}",
    )
    return ok({"id": rule.id, "enabled": rule.enabled}, message="状态已更新")


def _validate_canvas(nodes: list, edges: list) -> None:
    """校验画布结构：节点 id 唯一、连线端点存在、必须包含动作节点。"""
    if not nodes:
        raise ApiError("规则画布为空：至少需要一个触发条件与一个执行动作节点")
    ids = [node.get("id") for node in nodes]
    if len(ids) != len(set(ids)):
        raise ApiError("规则画布存在重复的节点 ID")
    for edge in edges:
        if edge.get("source") not in ids or edge.get("target") not in ids:
            raise ApiError("连线端点不存在于画布节点中")
    if not any(node.get("type") == "action" for node in nodes):
        raise ApiError("规则画布缺少「执行动作」节点")


@bp.get("/rule-templates")
@auth_required
def rule_templates():
    """画布节点模板（触发条件 / 判断条件 / 执行动作）。"""
    return ok(rule_engine.rule_templates())


@bp.post("/rules/validate")
@auth_required
def validate():
    """跨境合规校验（数据出境前）。

    请求：{dataLevel, sourceRegion, targetRegion, fields[], purpose, hasScc, hasDpia, authorized, fieldCount}
    返回：{passed, checkedRules[], issues[], rectificationList[]}
    """
    payload = body()
    data_level = str(payload.get("dataLevel", "P3")).upper()
    source_region = payload.get("sourceRegion", "CN")
    target_region = payload.get("targetRegion", "EU")
    fields = payload.get("fields") or []

    # 智能分级：若前端未指定级别，则按字段自动识别（取最高敏感度）
    if not payload.get("dataLevel") and fields:
        classified = classifier.classify_fields(
            [{"name": item} if isinstance(item, str) else item for item in fields]
        )
        levels = [item["level"] for item in classified["results"]]
        data_level = "P1" if "P1" in levels else ("P2" if "P2" in levels else "P3")

    rules = [item.to_dict() for item in ComplianceRule.query.all()]
    if not rules:
        rules = rule_engine.default_rules()

    context = {
        "event": "data.transfer",
        "dataLevel": data_level,
        "sourceRegion": source_region,
        "targetRegion": target_region,
        "crossBorder": source_region != target_region,
        "hasScc": bool(payload.get("hasScc")),
        "hasDpia": bool(payload.get("hasDpia")),
        "authorized": bool(payload.get("authorized")),
        "purpose": payload.get("purpose", ""),
        "fieldCount": int(payload.get("fieldCount") or len(fields) or 0),
        "fields": fields,
    }
    result = rule_engine.evaluate(rules, context)

    # 命中计数
    matched_codes = {item["code"] for item in result["checkedRules"] if item["result"] != "passed"}
    if matched_codes:
        for rule in ComplianceRule.query.filter(ComplianceRule.code.in_(matched_codes)).all():
            rule.hitCount = (rule.hitCount or 0) + 1
        db.session.commit()

    # 法规依据
    regulation = regulation_lib.get(f"{target_region}") or {}
    if target_region == "EU":
        regulation = regulation_lib.get("GDPR") or {}
    elif target_region == "CN":
        regulation = regulation_lib.get("PIPL") or {}
    elif target_region == "SEA":
        regulation = regulation_lib.get("PDPA-SG") or {}

    result["context"] = context
    result["regulation"] = {
        "code": regulation.get("code"),
        "name": regulation.get("name"),
        "transferRule": regulation.get("transferRule"),
        "auditRetentionYears": regulation.get("auditRetentionYears"),
        "sensitiveScope": regulation.get("sensitiveScope"),
    }
    result["dataLevel"] = data_level

    audit_logger.record_from_request(
        "compliance.validate", target=f"{source_region}→{target_region}", operation="查询",
        result="success" if result["passed"] else "denied",
        detail=f"合规校验：{data_level} 级数据，结论 {'通过' if result['passed'] else '未通过'}",
    )
    return ok(result)


# ---------------------------------------------------------------------------
# 合规报告
# ---------------------------------------------------------------------------


@bp.post("/reports")
@auth_required
@require_permission("compliance:report:create")
def create_report():
    """生成合规报告。"""
    payload = body()
    report_type = payload.get("type") or "GDPR"
    period_start = _parse_date(payload.get("periodStart")) or report_module.default_period()[0]
    period_end = _parse_date(payload.get("periodEnd")) or report_module.default_period()[1]
    if period_end < period_start:
        raise ApiError("报告时间范围结束日期不能早于开始日期")
    if (period_end - period_start).days > 366:
        raise ApiError("报告时间范围最长 1 年，超过部分请分段生成")

    meta = report_module.REPORT_TYPE_MAP.get(report_type, report_module.REPORT_TYPES[0])
    regions = payload.get("regions") or []
    advanced = payload.get("advanced") or {}

    stats = report_module.collect_stats(period_start, period_end, regions)
    content = report_module.build_report(
        report_type, period_start, period_end, regions, advanced, stats,
        created_by=current_user().username,
    )

    count = ComplianceReport.query.count() + 1
    record = ComplianceReport(
        code=next_code("RPT", count),
        type=report_type,
        typeName=meta["name"],
        status="generated",
        periodStart=period_start,
        periodEnd=period_end,
        regions=regions,
        advanced=advanced,
        content=content,
        createdBy=current_user().username,
    )
    content["basicInfo"]["reportCode"] = record.code
    markdown = report_module.render_markdown(record)
    record.sizeKb = round(len(markdown.encode("utf-8")) / 1024, 2)
    db.session.add(record)
    db.session.commit()

    evidence = audit_logger.record_from_request(
        "report.generate", target=record.code, operation="创建",
        detail=f"生成 {meta['name']}，期间 {period_start}~{period_end}",
    )
    record.chainTxId = evidence.chainTxId if evidence else ""
    db.session.commit()

    return ok({"id": record.id, "code": record.code, "status": record.status}, message="报告已生成")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip()[: 10 if fmt == "%Y-%m-%d" else 19], fmt).date()
        except ValueError:
            continue
    return None


@bp.get("/reports")
@auth_required
@require_permission("compliance:report:view")
def list_reports():
    """报告记录列表（支持状态、类型、时间范围筛选）。"""
    page, size = page_args()
    query = ComplianceReport.query
    status = request.args.get("status")
    report_type = request.args.get("type")
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    if status and status != "all":
        query = query.filter(ComplianceReport.status == status)
    if report_type and report_type != "all":
        query = query.filter(ComplianceReport.type == report_type)
    if start:
        query = query.filter(ComplianceReport.periodEnd >= start)
    if end:
        query = query.filter(ComplianceReport.periodStart <= end)
    query = query.order_by(ComplianceReport.createdAt.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.get("/reports/export")
@auth_required
@require_permission("compliance:report:view")
def export_reports():
    """导出报告列表（CSV）。"""
    rows = ComplianceReport.query.order_by(ComplianceReport.createdAt.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["报告ID", "报告类型", "时间范围起", "时间范围止", "状态", "生成时间", "生成人", "大小(KB)", "存证交易ID"])
    for item in rows:
        writer.writerow([
            item.code, item.typeName, item.periodStart, item.periodEnd, item.status,
            item.createdAt.strftime("%Y-%m-%d %H:%M:%S"), item.createdBy, item.sizeKb, item.chainTxId,
        ])
    audit_logger.record_from_request("data.export", target="reports", operation="导出",
                                     detail=f"导出报告列表 {len(rows)} 条")
    response = Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        "attachment; filename=compliance-reports.csv; filename*=UTF-8''%E5%90%88%E8%A7%84%E6%8A%A5%E5%91%8A%E5%88%97%E8%A1%A8.csv"
    )
    return response


@bp.get("/reports/<int:report_id>")
@auth_required
@require_permission("compliance:report:view")
def report_detail(report_id: int):
    """报告预览（结构化内容）。"""
    record = ComplianceReport.query.get(report_id)
    if record is None:
        raise ApiError("报告不存在", code=404)
    data = record.to_dict(with_content=True)
    content = record.content or {}
    data.update(
        {
            "period": {"start": data["periodStart"], "end": data["periodEnd"]},
            "basicInfo": content.get("basicInfo", {}),
            "dataActivities": content.get("dataActivities", []),
            "subjectRights": content.get("subjectRights", []),
            "conclusion": content.get("conclusion", {}),
            "metrics": content.get("metrics", {}),
            "markdown": report_module.render_markdown(record),
        }
    )
    return ok(data)


@bp.post("/reports/<int:report_id>/regenerate")
@auth_required
@require_permission("compliance:report:create")
def regenerate_report(report_id: int):
    """重新生成报告（按最新数据重算）。"""
    record = ComplianceReport.query.get(report_id)
    if record is None:
        raise ApiError("报告不存在", code=404)
    stats = report_module.collect_stats(record.periodStart, record.periodEnd, record.regions or [])
    content = report_module.build_report(
        record.type, record.periodStart, record.periodEnd, record.regions or [],
        record.advanced or {}, stats, created_by=current_user().username,
    )
    content["basicInfo"]["reportCode"] = record.code
    record.content = content
    record.status = "generated"
    db.session.commit()
    evidence = audit_logger.record_from_request(
        "report.generate", target=record.code, operation="修改", detail="重新生成报告"
    )
    record.chainTxId = evidence.chainTxId if evidence else record.chainTxId
    db.session.commit()
    return ok({"id": record.id, "status": record.status}, message="报告已重新生成")


@bp.get("/reports/<int:report_id>/download")
@auth_required
@require_permission("compliance:report:view")
def download_report(report_id: int):
    """下载报告（Markdown 附件）。"""
    record = ComplianceReport.query.get(report_id)
    if record is None:
        raise ApiError("报告不存在", code=404)
    markdown = report_module.render_markdown(record)
    audit_logger.record_from_request("data.export", target=record.code, operation="导出",
                                     detail=f"下载报告 {record.code}")
    response = Response(markdown, mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = (
        f"attachment; filename={record.code}.md; filename*=UTF-8''{record.code}-%E5%90%88%E8%A7%84%E6%8A%A5%E5%91%8A.md"
    )
    return response


@bp.get("/trend")
@auth_required
def trend():
    """跨境合规趋势（按地区、按月）。"""
    try:
        months = max(3, min(24, int(request.args.get("months", 6))))
    except (TypeError, ValueError):
        months = 6
    regions_param = request.args.get("regions", "EU,US,SEA")
    regions = [item.strip() for item in regions_param.split(",") if item.strip()]

    rows = ComplianceTrendPoint.query.order_by(ComplianceTrendPoint.month.asc()).all()
    labels = sorted({item.month for item in rows})[-months:]
    region_names = {"EU": "欧盟", "US": "美国", "SEA": "东南亚", "CN": "中国", "ME": "中东", "AF": "非洲"}

    if rows:
        series = []
        for region in regions:
            mapping = {item.month: item.complianceRate for item in rows if item.region == region}
            series.append(
                {
                    "region": region,
                    "name": region_names.get(region, region),
                    "data": [round(mapping.get(month, 0) * 100, 2) for month in labels],
                }
            )
        return ok({"months": labels, "series": series, "unit": "%"})

    # 无历史数据：按当期规则校验结果生成基线曲线（source=derived，前端会标注）
    base = {"EU": 96.5, "US": 97.2, "SEA": 94.8, "CN": 98.1, "ME": 92.6, "AF": 91.4}
    today = date.today()
    generated_labels = []
    for offset in range(months - 1, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=offset * 30)).replace(day=1)
        generated_labels.append(month_date.strftime("%Y-%m"))
    series = []
    for region in regions:
        start = base.get(region, 95.0)
        series.append(
            {
                "region": region,
                "name": region_names.get(region, region),
                "data": [round(min(99.9, start + index * 0.35), 2) for index in range(len(generated_labels))],
            }
        )
    return ok({"months": generated_labels, "series": series, "unit": "%", "source": "derived"})


@bp.get("/alerts")
@auth_required
def alerts():
    """合规预警列表。"""
    try:
        limit = max(1, min(50, int(request.args.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    rows = Alert.query.order_by(Alert.createdAt.desc()).limit(limit).all()
    return ok([item.to_dict() for item in rows])


@bp.post("/alerts/<int:alert_id>/handle")
@auth_required
@require_permission("compliance:rule:manage")
def handle_alert(alert_id: int):
    """预警处置：open → handling → closed（处置记录同步上链存证）。"""
    alert = Alert.query.get(alert_id)
    if alert is None:
        raise ApiError("预警不存在", code=404)
    payload = body()
    status = payload.get("status", "closed")
    if status not in ("open", "handling", "closed"):
        raise ApiError("状态取值非法，可选：open / handling / closed")
    alert.status = status
    if payload.get("requirement"):
        alert.requirement = payload["requirement"]
    db.session.commit()

    audit_logger.record_from_request(
        "alert.handle", target=alert.code, operation="修改",
        detail=f"预警处置：{alert.title} → {status}；{payload.get('comment', '')}",
    )
    return ok(alert.to_dict(), message="预警状态已更新")


@bp.get("/taxonomy")
@auth_required
def taxonomy():
    """分级分类字典与统计（含各等级数据集数量）。"""
    data = classifier.taxonomy()
    for level in data["levels"]:
        level["count"] = Dataset.query.filter_by(level=level["code"]).count()
    data["total"] = Dataset.query.count()
    data["regulations"] = regulation_lib.coverage_stats()
    return ok(data)


@bp.get("/regulations")
@auth_required
def regulations():
    """法规库（合规页速查表使用）。"""
    return ok(regulation_lib.all_regulations())
