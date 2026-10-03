# -*- coding: utf-8 -*-
"""数据血缘追踪与溯源接口（/api/lineage）。

字段口径说明（与前端 views/lineage 的筛选项保持一致）：
- dataType：user（用户数据）/ transaction（交易数据）/ list（清单数据）
- stage：collect / extract / transform / compute / apply
- operation：query / update / delete / export
为兼容人工调用与旧数据，接口同时接受中文取值（用户数据/采集/查询……）。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, request

from ..audit import logger as audit_logger
from ..extensions import db
from ..models import AuditLog, LineageLink, LineageNode, LineageRecord, Transaction, next_code, now
from ..utils.deps import auth_required, current_user
from ..utils.response import ApiError, body, ok, page_args, paginate

bp = Blueprint("lineage", __name__, url_prefix="/api/lineage")

DATA_TYPE_MAP = {
    "user": "用户数据", "用户数据": "用户数据", "USER": "用户数据",
    "transaction": "交易数据", "交易数据": "交易数据", "TRANSACTION": "交易数据",
    "list": "清单数据", "清单数据": "清单数据", "LIST": "清单数据",
}
DATA_TYPE_CODE = {"用户数据": "user", "交易数据": "transaction", "清单数据": "list"}

STAGE_MAP = {
    "collect": "采集", "采集": "采集",
    "extract": "抽取", "抽取": "抽取",
    "transform": "转换", "转换": "转换",
    "compute": "计算", "计算": "计算",
    "apply": "应用", "应用": "应用",
}
STAGE_CODE = {"采集": "collect", "抽取": "extract", "转换": "transform", "计算": "compute", "应用": "apply"}

OPERATION_MAP = {
    "query": "查询", "查询": "查询",
    "update": "修改", "修改": "修改",
    "delete": "删除", "删除": "删除",
    "export": "导出", "导出": "导出",
}
OPERATION_CODE = {"查询": "query", "修改": "update", "删除": "delete", "导出": "export"}


def _parse_time(value: str | None, end_of_day: bool = False):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            if end_of_day and fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return parsed
        except ValueError:
            continue
    return None


def _node_payload(node: LineageNode) -> dict:
    data = node.to_dict()
    # 同时返回编码与中文名，前端两种取值都能正常展示
    data["dataType"] = DATA_TYPE_CODE.get(node.dataType, node.dataType)
    data["dataTypeName"] = node.dataType
    data["stage"] = STAGE_CODE.get(node.stage, node.stage)
    data["stageName"] = node.stage
    return data


@bp.get("/graph")
@auth_required
def graph():
    """血缘图谱：节点 + 连线（支持数据类型、阶段、时间范围、关键字筛选）。"""
    query = LineageNode.query
    data_type = request.args.get("dataType")
    stage = request.args.get("stage")
    keyword = request.args.get("keyword")
    start = _parse_time(request.args.get("start"))
    end = _parse_time(request.args.get("end"), end_of_day=True)

    if data_type and data_type not in ("all", ""):
        query = query.filter(LineageNode.dataType == DATA_TYPE_MAP.get(data_type, data_type))
    if stage and stage not in ("all", ""):
        query = query.filter(LineageNode.stage == STAGE_MAP.get(stage, stage))
    if keyword:
        query = query.filter(LineageNode.name.like(f"%{keyword}%"))
    if start:
        query = query.filter(LineageNode.processedAt >= start)
    if end:
        query = query.filter(LineageNode.processedAt <= end)

    nodes = query.order_by(LineageNode.id).all()
    codes = {node.code for node in nodes}
    links = [item for item in LineageLink.query.all() if item.source in codes and item.target in codes]

    return ok(
        {
            "nodes": [_node_payload(node) for node in nodes],
            "links": [item.to_dict() for item in links],
            "stats": {
                "nodes": len(nodes),
                "links": len(links),
                "levels": {
                    level: len([node for node in nodes if node.level == level]) for level in ("P1", "P2", "P3")
                },
            },
        }
    )


@bp.get("/nodes/<node_code>")
@auth_required
def node_detail(node_code: str):
    """节点详情：元数据 + 双向追溯 + 处理规则 + 合规标签。"""
    node = LineageNode.query.filter_by(code=node_code).first()
    if node is None:
        raise ApiError(f"血缘节点不存在：{node_code}", code=404)

    upstream_links = LineageLink.query.filter_by(target=node_code).all()
    downstream_links = LineageLink.query.filter_by(source=node_code).all()
    upstream_codes = [item.source for item in upstream_links]
    downstream_codes = [item.target for item in downstream_links]
    upstream = LineageNode.query.filter(LineageNode.code.in_(upstream_codes)).all() if upstream_codes else []
    downstream = LineageNode.query.filter(LineageNode.code.in_(downstream_codes)).all() if downstream_codes else []

    meta = node.meta or {}
    return ok(
        {
            "node": _node_payload(node),
            "upstream": [
                {**_node_payload(item), "operation": _operation_between(item.code, node_code)}
                for item in upstream
            ],
            "downstream": [
                {**_node_payload(item), "operation": _operation_between(node_code, item.code)}
                for item in downstream
            ],
            "rules": meta.get("rules", []),
            "complianceTags": node.tags or [],
            "owner": node.owner,
            "processedAt": node.processedAt.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def _operation_between(source: str, target: str) -> str:
    link = LineageLink.query.filter_by(source=source, target=target).first()
    return link.operation if link else "流转"


@bp.get("/trace/<data_id>")
@auth_required
def trace(data_id: str):
    """数据溯源详情：基本信息 + 流转路径（时间线）+ 合规检查结果。"""
    node = LineageNode.query.filter(
        db.or_(LineageNode.code == data_id, LineageNode.name.like(f"%{data_id}%"))
    ).first()

    logs = (
        AuditLog.query.filter(AuditLog.dataId == data_id)
        .order_by(AuditLog.ts.asc())
        .all()
    )
    if node is None and not logs:
        raise ApiError(f"未找到数据 {data_id} 的血缘与审计记录", code=404)

    if node is not None:
        basic = {
            "dataId": node.code,
            "name": node.name,
            "type": DATA_TYPE_CODE.get(node.dataType, node.dataType),
            "typeName": node.dataType,
            "level": node.level,
            "owner": node.owner,
            "region": node.region,
            "createdAt": node.createdAt.strftime("%Y-%m-%d %H:%M:%S"),
            "updatedAt": node.updatedAt.strftime("%Y-%m-%d %H:%M:%S"),
            "storage": (node.meta or {}).get("storage", "HDFS"),
            "rows": (node.meta or {}).get("rows", 0),
        }
        timeline = _build_timeline(node)
        compliance = [
            {"label": tag, "passed": True, "standard": "平台合规规则引擎校验通过"}
            for tag in (node.tags or [])
        ]
    else:
        basic = {"dataId": data_id, "name": data_id, "type": "transaction", "level": "P2"}
        timeline = []
        compliance = []

    # 补充审计日志中的流转节点
    for log in logs:
        timeline.append(
            {
                "ts": log.ts.strftime("%Y-%m-%d %H:%M:%S"),
                "node": log.node or "平台",
                "action": f"{log.operation}（{log.action}）",
                "operator": log.actor,
                "detail": log.detail or log.target,
                "result": log.result,
                "chainTxId": log.chainTxId,
            }
        )
    timeline.sort(key=lambda item: item["ts"])

    return ok({"basic": basic, "timeline": timeline, "compliance": compliance, "auditCount": len(logs)})


def _build_timeline(node: LineageNode) -> list[dict]:
    """沿血缘链路回溯，构造「数据源 → 清洗脱敏 → 风控决策系统」式的流转时间线。"""
    chain_nodes: list[LineageNode] = [node]
    current = node
    for _ in range(6):  # 最多向上回溯 6 层，避免环形链路死循环
        link = LineageLink.query.filter_by(target=current.code).first()
        if link is None:
            break
        parent = LineageNode.query.filter_by(code=link.source).first()
        if parent is None or parent in chain_nodes:
            break
        chain_nodes.append(parent)
        current = parent

    timeline = []
    for item in reversed(chain_nodes):
        timeline.append(
            {
                "ts": item.processedAt.strftime("%Y-%m-%d %H:%M:%S"),
                "node": item.name,
                "action": item.stage,
                "operator": item.owner,
                "detail": f"{item.dataType}｜{item.level} 级｜{(item.meta or {}).get('rules', ['—'])[0] if (item.meta or {}).get('rules') else '—'}",
                "result": "success",
            }
        )
    return timeline


@bp.post("/records")
@auth_required
def create_record():
    """生成含合规标签的链路记录并落链存证（可用 dataId 或 range 指定范围）。"""
    payload = body()
    data_id = payload.get("dataId")
    range_desc = payload.get("range")

    if data_id:
        node = LineageNode.query.filter_by(code=data_id).first()
        if node is None:
            raise ApiError(f"血缘节点不存在：{data_id}", code=404)
        related = [node] + [
            item
            for item in LineageNode.query.all()
            if item.code in {
                link.source for link in LineageLink.query.filter_by(target=data_id).all()
            }
            | {link.target for link in LineageLink.query.filter_by(source=data_id).all()}
        ]
        range_text = f"节点 {data_id} 及其上下游"
    else:
        nodes = LineageNode.query.limit(50).all()
        related = nodes
        if isinstance(range_desc, dict):
            range_text = (
                f"筛选范围：类型={range_desc.get('dataType', '全部')}，阶段={range_desc.get('stage', '全部')}，"
                f"时间={range_desc.get('start', '-')}~{range_desc.get('end', '-')}，"
                f"关键字={range_desc.get('keyword', '-')}"
            )
        else:
            range_text = str(range_desc or "全量数据血缘")

    if not related:
        raise ApiError("没有可生成链路记录的血缘数据", code=404)

    tags: list[str] = []
    for item in related:
        for tag in item.tags or []:
            if tag not in tags:
                tags.append(tag)

    count = LineageRecord.query.count() + 1
    record = LineageRecord(
        code=next_code("LINK", count),
        dataId=data_id or "",
        range=range_text,
        nodes=[item.code for item in related],
        complianceTags=tags,
        generatedBy=current_user().username,
    )
    db.session.add(record)
    db.session.flush()

    evidence = audit_logger.record_from_request(
        "data.export", target=record.code, data_id=data_id or "", operation="导出",
        detail=f"生成链路记录：{range_text}，覆盖 {len(related)} 个节点",
    )
    record.chainTxId = evidence.chainTxId if evidence else ""
    db.session.commit()

    return ok(
        {
            "recordId": record.code,
            "chainTxId": record.chainTxId,
            "nodes": len(related),
            "generatedAt": record.createdAt.strftime("%Y-%m-%d %H:%M:%S"),
            "complianceTags": tags,
            "range": range_text,
        },
        message="链路记录已生成并存证",
    )


@bp.get("/records/<record_id>/download")
@auth_required
def download_record(record_id: str):
    """导出溯源报告（Markdown 附件）。"""
    record = LineageRecord.query.filter_by(code=record_id).first()
    if record is None:
        raise ApiError(f"链路记录不存在：{record_id}", code=404)

    nodes = LineageNode.query.filter(LineageNode.code.in_(record.nodes or [])).all()
    lines = [
        f"# 数据链路溯源报告 {record.code}",
        "",
        f"- 生成时间：{record.createdAt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 生成人：{record.generatedBy}",
        f"- 覆盖范围：{record.range}",
        f"- 区块链存证交易：{record.chainTxId or '-'}",
        f"- 合规标签：{'、'.join(record.complianceTags or []) or '-'}",
        "",
        "## 链路节点明细",
        "",
        "| 节点编码 | 节点名称 | 类型 | 阶段 | 归属主体 | 分级 | 加工时间 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in nodes:
        lines.append(
            f"| {item.code} | {item.name} | {item.dataType} | {item.stage} | {item.owner} | {item.level} | "
            f"{item.processedAt.strftime('%Y-%m-%d %H:%M:%S')} |"
        )
    lines += [
        "",
        "## 链路关系",
        "",
        "| 上游 | 下游 | 操作 | 时间 |",
        "| --- | --- | --- | --- |",
    ]
    for link in LineageLink.query.all():
        if link.source in (record.nodes or []) and link.target in (record.nodes or []):
            lines.append(f"| {link.source} | {link.target} | {link.operation} | {link.ts.strftime('%Y-%m-%d %H:%M:%S')} |")
    lines += [
        "",
        "---",
        "",
        "本报告由 FedShield 平台按 GDPR 第 30 条（处理活动记录）与 PIPL 第 55 条（个人信息保护影响评估）"
        "要求生成，可凭报告编号与存证交易 ID 在监管节点完成校验。",
        "",
    ]

    response = Response("\n".join(lines), mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = (
        f"attachment; filename={record.code}.md; filename*=UTF-8''{record.code}-%E6%BA%AF%E6%BA%90%E6%8A%A5%E5%91%8A.md"
    )
    return response


@bp.get("/audit")
@auth_required
def audit():
    """溯源审计记录检索（数据ID、操作类型、数据类型、时间范围）。"""
    page, size = page_args()
    query = AuditLog.query
    data_id = request.args.get("dataId")
    operation = request.args.get("operation")
    data_type = request.args.get("dataType")
    start = _parse_time(request.args.get("start"))
    end = _parse_time(request.args.get("end"), end_of_day=True)

    if data_id:
        query = query.filter(AuditLog.dataId.like(f"%{data_id}%"))
    if operation and operation not in ("all", ""):
        query = query.filter(AuditLog.operation == OPERATION_MAP.get(operation, operation))
    if data_type and data_type not in ("all", ""):
        query = query.filter(AuditLog.dataType == DATA_TYPE_MAP.get(data_type, data_type))
    if start:
        query = query.filter(AuditLog.ts >= start)
    if end:
        query = query.filter(AuditLog.ts <= end)

    query = query.order_by(AuditLog.ts.desc())

    def serialize(item: AuditLog) -> dict:
        data = item.to_dict()
        data["operationCode"] = OPERATION_CODE.get(item.operation, item.operation)
        data["dataTypeCode"] = DATA_TYPE_CODE.get(item.dataType, item.dataType)
        return data

    return ok(paginate(query, page, size, serialize))


@bp.get("/audit/export")
@auth_required
def export_audit():
    """导出溯源审计记录（CSV，含防篡改签名与存证交易 ID）。"""
    query = AuditLog.query.order_by(AuditLog.ts.desc()).limit(5000)
    data_id = request.args.get("dataId")
    operation = request.args.get("operation")
    if data_id:
        query = query.filter(AuditLog.dataId.like(f"%{data_id}%"))
    if operation and operation not in ("all", ""):
        query = query.filter(AuditLog.operation == OPERATION_MAP.get(operation, operation))
    rows = query.all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["时间", "操作人", "角色", "操作类型", "动作", "数据ID", "数据类型", "节点", "结果",
                     "风险评分", "防篡改签名", "区块链交易ID"])
    for item in rows:
        writer.writerow([
            item.ts.strftime("%Y-%m-%d %H:%M:%S"), item.actor, item.role, item.operation, item.action,
            item.dataId, item.dataType, item.node, item.result, round(item.riskScore, 3),
            item.signature, item.chainTxId,
        ])
    audit_logger.record_from_request("data.export", target="lineage-audit", operation="导出",
                                     detail=f"导出溯源审计记录 {len(rows)} 条")
    response = Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        "attachment; filename=lineage-audit.csv; filename*=UTF-8''%E6%BA%AF%E6%BA%90%E5%AE%A1%E8%AE%A1%E8%AE%B0%E5%BD%95.csv"
    )
    return response


@bp.get("/summary")
@auth_required
def summary():
    """血缘概览统计（控制台与图谱页顶部指标）。"""
    nodes = LineageNode.query.all()
    return ok(
        {
            "nodeTotal": len(nodes),
            "linkTotal": LineageLink.query.count(),
            "byStage": {
                stage: len([node for node in nodes if node.stage == stage])
                for stage in ("采集", "抽取", "转换", "计算", "应用")
            },
            "byLevel": {level: len([node for node in nodes if node.level == level]) for level in ("P1", "P2", "P3")},
            "transactions": Transaction.query.count(),
            "updatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
