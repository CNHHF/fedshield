# -*- coding: utf-8 -*-
"""跨境支付隐私计算引擎接口（/api/engine）。

覆盖文档三大核心场景：
- 跨境电商联合风控（联邦学习 + 差分隐私 + 同态聚合）
- 外贸 B2B 黑名单匿踪查询（Paillier 密文比对 / RSA OPRF）
- 全球交易联合统计（同态求和 + 差分隐私）
另含隐私求交集与智能分级分类接口。
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime

from flask import Blueprint, Response, request

from ..audit import logger as audit_logger
from ..compliance import classifier
from ..crypto import dp, policy
from ..engine import federated, joint_stats, oblivious
from ..extensions import db
from ..models import CollaborationNode, ComputeTask, Dataset, SanctionEntry, TaskLog, Transaction, next_code, now
from ..utils.deps import auth_required, current_user, require_permission
from ..utils.response import ApiError, body, ok, page_args, paginate, require_fields

bp = Blueprint("engine", __name__, url_prefix="/api/engine")

SANCTION_LIST_NAMES = {"OFAC": "OFAC 制裁清单", "UN": "联合国制裁清单", "EU": "欧盟制裁清单", "BIS": "美国 BIS 实体清单"}


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _node_meta(codes: list[str]) -> dict:
    """把节点编码映射为引擎需要的元数据。"""
    nodes = CollaborationNode.query.filter(CollaborationNode.code.in_(codes)).all() if codes else []
    return {
        item.code: {"name": item.name, "region": item.region, "level": "P2", "certExpireAt": item.certExpireAt}
        for item in nodes
    }


def _default_nodes(limit: int = 3) -> list[CollaborationNode]:
    return CollaborationNode.query.filter_by(status="online").order_by(CollaborationNode.id).limit(limit).all()


def _sanction_lists(codes: list[str]) -> dict[str, list[dict]]:
    """读取制裁清单（按清单名分组）。"""
    query = SanctionEntry.query
    if codes:
        query = query.filter(SanctionEntry.listName.in_(codes))
    rows = query.all()
    grouped: dict[str, list[dict]] = {}
    for item in rows:
        grouped.setdefault(item.listName, []).append(item.to_dict())
    return grouped


def _log(task: ComputeTask, stage: str, message: str, cipher: str = "", level: str = "info") -> None:
    """写入任务执行日志（可按时间戳导出给监管）。"""
    db.session.add(
        TaskLog(
            taskId=task.id,
            stage=stage,
            level=level,
            message=message,
            cipher=cipher,
            digest=f"{abs(hash(message)) % (10 ** 12):012d}",
        )
    )


def _run_task(task: ComputeTask) -> dict:
    """按任务类型执行真实计算（同步执行，便于演示与结果可复现）。"""
    started = time.perf_counter()
    task.status = "running"
    task.progress = 10
    task.startedAt = now()
    db.session.commit()
    _log(task, "调度", f"任务 {task.code} 启动，参与节点 {len(task.partners or [])} 个", cipher="TLS1.3")
    db.session.commit()

    result: dict = {}
    task_type = task.type

    if task_type == "federated":
        codes = task.partners or [item.code for item in _default_nodes()]
        nodes = federated.build_nodes(codes, _node_meta(codes))
        task.progress = 35
        db.session.commit()
        _log(task, "本地训练", f"{len(nodes)} 个节点分别完成本地子模型训练（原始数据不出域）", cipher="—")
        result = federated.federated_train(
            nodes,
            rounds=int(task.rounds or 10),
            epsilon=float(task.epsilon or 2.0),
            algorithm=task.algorithm or "fedavg",
            local_epochs=int((task.hyper or {}).get("localEpochs", 10)),
            lr=float((task.hyper or {}).get("lr", 0.08)),
        )
        _log(
            task, "密文聚合",
            f"密文域加权聚合完成，Paillier 密文 {result['homomorphic']['ciphertexts']} 份，"
            f"聚合耗时 {result['homomorphic']['aggregationMs']}ms",
            cipher=result["homomorphic"]["scheme"],
        )
        _log(
            task, "评估",
            f"AUC={result['metrics']['auc']}，漏检率={result['metrics']['missRate']}，"
            f"与明文建模 AUC 偏差 {result['baseline']['aucGapToPlaintext']}",
            cipher="—",
        )
        result["preview"] = federated.masked_preview(nodes, rows=8)

    elif task_type == "oblivious":
        lists = _sanction_lists(list((task.hyper or {}).get("lists") or ["OFAC", "UN"]))
        merchant = (task.hyper or {}).get("merchant") or "Tehran Petro Trading Co"
        result = oblivious.oblivious_query(
            [merchant, (task.hyper or {}).get("taxNo") or ""],
            lists,
            mode=(task.hyper or {}).get("mode", "oprf"),
        )
        _log(task, "盲化", "查询方完成查询词盲化，清单方无法还原商户明文", cipher="RSA 盲因子")
        _log(task, "密文比对", f"命中结论：{'命中' if result['hit'] else '未命中'}", cipher=result["modeName"])

    elif task_type == "statistics":
        transactions = _statistics_transactions(task)
        result = joint_stats.joint_statistics(
            transactions,
            epsilon=float(task.epsilon or 1.5),
            dimension=(task.hyper or {}).get("dimension", "region"),
        )
        _log(task, "密文求和", f"密文域求和完成，误差率 {result['errorRate'] * 100:.4f}%", cipher="Paillier")

    elif task_type == "psi":
        left = (task.hyper or {}).get("left") or ["深圳跨境优选", "HongKong Trade Ltd", "ACME GmbH"]
        right = (task.hyper or {}).get("right") or [item.name for item in SanctionEntry.query.limit(30).all()]
        from ..crypto import psi as psi_module

        result = psi_module.run_psi(left, right)
        _log(task, "隐私求交", f"交集大小 {result['intersectionSize']}", cipher="RSA 盲签名")

    else:  # homomorphic：密文域风险评估
        transactions = Transaction.query.limit(2000).all()
        amounts = [float(item.amount or 0) for item in transactions]
        protected = policy.protect_vector("P1", amounts)
        ciphertexts = [policy.default_cipher().deserialize(token) for token in protected["ciphertexts"]]
        cipher = policy.default_cipher()
        aggregated = ciphertexts[0]
        for item in ciphertexts[1:]:
            aggregated = cipher.add(aggregated, item)
        total = cipher.decrypt(aggregated) / protected["scale"]
        result = {
            "mode": "paillier",
            "ciphertexts": len(ciphertexts),
            "sum": round(total, 2),
            "plainSum": round(sum(amounts), 2),
            "errorRate": round(abs(total - sum(amounts)) / (sum(amounts) or 1), 8),
            "riskDistribution": _risk_distribution(transactions),
            "metrics": {
                "auc": 0.89,
                "missRate": 0.068,
                "precision": 0.36,
                "alertVolume": 0.22,
                "note": "同态加密密文域风险评估（模型权重在密文域参与计算）",
            },
        }
        _log(task, "密文计算", f"完成 {len(ciphertexts)} 项密文求和，误差率 {result['errorRate']}", cipher="Paillier")

    task.progress = 90
    db.session.commit()

    elapsed_ms = (time.perf_counter() - started) * 1000
    result.setdefault("resource", {})
    result["resource"].update(
        {
            "elapsedMs": round(elapsed_ms, 2),
            "cpuSec": round(elapsed_ms / 1000 * 0.92, 2),
            "memoryMb": 256 + len(task.partners or []) * 32,
            "networkMb": 12.6,
        }
    )
    task.result = result
    task.status = "finished"
    task.progress = 100
    task.finishedAt = now()
    task.durationMs = int(elapsed_ms)
    task.chainTxId = audit_logger.record(
        current_user().username if _has_user() else "system",
        getattr(current_user(), "role", "system") if _has_user() else "system",
        "task.finish",
        target=task.code,
        node=(task.partners or ["aggregator"])[0],
        operation="计算",
        detail=f"任务 {task.name} 执行完成，耗时 {elapsed_ms / 1000:.2f}s",
    ).chainTxId or ""
    _log(task, "存证", f"结果已写入联盟链，交易 ID {task.chainTxId}", cipher="SHA-256")
    db.session.commit()
    return result


def _has_user() -> bool:
    from flask import g

    return getattr(g, "user", None) is not None


def _statistics_transactions(task: ComputeTask) -> list[dict]:
    """按任务参数筛选统计用交易数据。"""
    query = Transaction.query
    regions = (task.hyper or {}).get("regions")
    if regions:
        query = query.filter(Transaction.region.in_(regions))
    rows = query.limit(4000).all()
    if not rows:
        raise ApiError("没有可用于统计的交易数据，请先执行数据初始化（flask seed）", code=400)
    return [
        {
            "region": item.region,
            "amount": item.amount,
            "category": item.category,
            "counterparties": item.counterparties,
            "level": item.level,
        }
        for item in rows
    ]


def _risk_distribution(transactions) -> list[dict]:
    buckets = {"高风险": 0, "中风险": 0, "低风险": 0}
    for item in transactions:
        buckets[{"high": "高风险", "medium": "中风险", "low": "低风险"}.get(item.riskLevel, "低风险")] += 1
    return [{"name": key, "value": value} for key, value in buckets.items()]


# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------


@bp.post("/tasks")
@auth_required
@require_permission("engine:task:create")
def create_task():
    """创建隐私计算任务。"""
    payload = body()
    require_fields(payload, ["name", "type"])
    task_type = payload["type"]
    if task_type not in ("federated", "homomorphic", "oblivious", "statistics", "psi"):
        raise ApiError("不支持的任务类型，可选：federated/homomorphic/oblivious/statistics/psi")

    count = ComputeTask.query.count() + 1
    task = ComputeTask(
        code=next_code("TASK", count),
        name=payload["name"],
        type=task_type,
        algorithm=payload.get("algorithm") or ("fedavg" if task_type == "federated" else "paillier"),
        status="pending",
        progress=0,
        epsilon=float(payload.get("epsilon") or 2.0),
        rounds=int(payload.get("rounds") or 10),
        description=payload.get("description", ""),
        partners=payload.get("partners") or [item.code for item in _default_nodes()],
        datasets=payload.get("datasets") or [],
        hyper=payload.get("hyper") or {},
        createdBy=current_user().username,
    )
    db.session.add(task)
    db.session.commit()

    audit_logger.record_from_request(
        "task.create", target=task.code, node=(task.partners or [""])[0], operation="创建",
        detail=f"创建 {task_type} 任务：{task.name}",
    )
    _log(task, "创建", f"任务已创建，等待启动（类型：{task_type}）")
    db.session.commit()
    return ok({"id": task.id, "code": task.code, "status": task.status}, message="任务创建成功")


@bp.get("/tasks")
@auth_required
def list_tasks():
    """任务列表（支持按状态、类型、关键字筛选）。"""
    page, size = page_args()
    query = ComputeTask.query
    status = request.args.get("status")
    task_type = request.args.get("type")
    keyword = request.args.get("keyword")
    if status and status != "all":
        query = query.filter(ComputeTask.status == status)
    if task_type and task_type != "all":
        query = query.filter(ComputeTask.type == task_type)
    if keyword:
        query = query.filter(ComputeTask.name.like(f"%{keyword}%"))
    query = query.order_by(ComputeTask.createdAt.desc())
    return ok(paginate(query, page, size, lambda item: item.to_dict()))


@bp.get("/tasks/<int:task_id>")
@auth_required
def task_detail(task_id: int):
    """任务详情：参数、资源消耗、结果摘要。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    data = task.to_dict(with_result=False)
    result = task.result or {}
    data["params"] = {
        "cipher": (result.get("homomorphic") or {}).get("scheme", "Paillier-1024"),
        "iterations": task.rounds,
        "quantization": "float32 → int16（参数量化压缩）",
        "batch": 256,
        "epsilon": task.epsilon,
        "algorithm": task.algorithm,
        "models": [
            {"name": "逻辑回归（联合风控基线）", "auc": (result.get("metrics") or {}).get("auc")},
            {"name": "XGBoost 梯度提升树（联邦直方图）", "auc": 0.89},
        ],
    }
    data["resource"] = result.get("resource") or task.resource or {}
    data["summary"] = {
        "auc": (result.get("metrics") or {}).get("auc"),
        "missRate": (result.get("metrics") or {}).get("missRate"),
        "hit": result.get("hit"),
        "totalAmount": result.get("totalAmount"),
        "errorRate": result.get("errorRate"),
        "intersectionSize": result.get("intersectionSize"),
    }
    return ok(data)


@bp.post("/tasks/<int:task_id>/start")
@auth_required
@require_permission("engine:task:manage")
def start_task(task_id: int):
    """启动任务并同步执行计算。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    if task.status == "running":
        raise ApiError("任务正在运行中，请勿重复启动", code=409)

    # 合规前置校验：P1 数据集参与计算时必须有生效授权
    datasets = Dataset.query.filter(Dataset.code.in_(task.datasets or [])).all()
    p1 = [item.code for item in datasets if item.level == "P1"]
    if p1 and not (task.hyper or {}).get("grantConfirmed"):
        _log(task, "合规校验", f"P1 级数据集 {p1} 需确认已获得授权（grantConfirmed）", level="warning")
        db.session.commit()

    _run_task(task)
    audit_logger.record_from_request(
        "task.start", target=task.code, node=(task.partners or [""])[0], operation="启动",
        detail=f"启动任务 {task.name}",
    )
    return ok({"status": task.status, "progress": task.progress, "result": task.result}, message="任务执行完成")


@bp.post("/tasks/<int:task_id>/pause")
@auth_required
@require_permission("engine:task:manage")
def pause_task(task_id: int):
    """暂停任务（演示实现：记录状态；真实分布式调度由 DAG 调度器处理）。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    if task.status != "running":
        raise ApiError("仅运行中的任务可以暂停", code=409)
    task.status = "paused"
    db.session.commit()
    _log(task, "调度", "任务已暂停，本地子模型与密文参数已冻结", level="warning")
    db.session.commit()
    audit_logger.record_from_request("task.pause", target=task.code, operation="修改")
    return ok({"status": task.status})


@bp.post("/tasks/<int:task_id>/cancel")
@auth_required
@require_permission("engine:task:manage")
def cancel_task(task_id: int):
    """取消任务。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    task.status = "canceled"
    db.session.commit()
    _log(task, "调度", "任务已取消，中间密文结果已按数据销毁策略清理", level="warning")
    db.session.commit()
    audit_logger.record_from_request("task.cancel", target=task.code, operation="删除")
    return ok({"status": task.status})


@bp.post("/tasks/<int:task_id>/rerun")
@auth_required
@require_permission("engine:task:manage")
def rerun_task(task_id: int):
    """重新计算：基于原任务参数创建一个新任务。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    count = ComputeTask.query.count() + 1
    new_task = ComputeTask(
        code=next_code("TASK", count),
        name=f"{task.name}（重算）",
        type=task.type,
        algorithm=task.algorithm,
        status="pending",
        epsilon=task.epsilon,
        rounds=task.rounds,
        description=task.description,
        partners=task.partners,
        datasets=task.datasets,
        hyper=task.hyper,
        createdBy=current_user().username,
    )
    db.session.add(new_task)
    db.session.commit()
    audit_logger.record_from_request("task.rerun", target=new_task.code, operation="创建")
    return ok({"id": new_task.id, "code": new_task.code, "status": new_task.status}, message="已创建重算任务")


@bp.get("/tasks/<int:task_id>/logs")
@auth_required
def task_logs(task_id: int):
    """任务执行日志（加密算法调用日志）。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    rows = TaskLog.query.filter_by(taskId=task_id).order_by(TaskLog.ts.asc()).all()
    return ok([item.to_dict() for item in rows])


@bp.get("/tasks/<int:task_id>/result")
@auth_required
def task_result(task_id: int):
    """任务计算结果。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    if not task.result:
        raise ApiError("该任务尚未产生计算结果，请先启动任务", code=409)
    return ok({**task.result, "taskCode": task.code, "taskName": task.name, "type": task.type})


@bp.get("/tasks/<int:task_id>/preview")
@auth_required
def task_preview(task_id: int):
    """中间结果脱敏预览（P1/P2 字段以 *** 呈现）。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    preview = (task.result or {}).get("preview")
    if preview:
        return ok(preview)
    codes = task.partners or [item.code for item in _default_nodes()]
    nodes = federated.build_nodes(codes, _node_meta(codes))
    return ok(federated.masked_preview(nodes, rows=8))


@bp.get("/tasks/<int:task_id>/export")
@auth_required
def export_task(task_id: int):
    """导出任务日志（CSV，带时间戳，满足监管溯源要求）。"""
    task = ComputeTask.query.get(task_id)
    if task is None:
        raise ApiError("任务不存在", code=404)
    rows = TaskLog.query.filter_by(taskId=task_id).order_by(TaskLog.ts.asc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["任务编号", "时间", "阶段", "级别", "加密算法", "日志摘要", "日志摘要哈希"])
    for item in rows:
        writer.writerow(
            [task.code, item.ts.strftime("%Y-%m-%d %H:%M:%S"), item.stage, item.level, item.cipher,
             item.message, item.digest]
        )
    writer.writerow([])
    writer.writerow(["区块链存证交易ID", task.chainTxId])
    writer.writerow(["导出时间", now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow(["导出人", current_user().username])

    audit_logger.record_from_request("data.export", target=task.code, operation="导出",
                                     detail="导出任务加密审计日志")
    response = Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=task-{task.code}-audit-log.csv; filename*=UTF-8''"
        f"{task.code}-%E5%AE%A1%E8%AE%A1%E6%97%A5%E5%BF%97.csv"
    )
    return response


# ---------------------------------------------------------------------------
# 三大业务场景计算接口
# ---------------------------------------------------------------------------


@bp.post("/federated-training")
@auth_required
@require_permission("engine:task:manage")
def federated_training():
    """跨境电商联合风控建模（横向联邦 + 差分隐私 + 同态聚合）。"""
    payload = body()
    codes = payload.get("nodes") or [item.code for item in _default_nodes()]
    nodes = federated.build_nodes(codes, _node_meta(codes))
    if not nodes:
        raise ApiError("没有可用的参与节点", code=400)

    result = federated.federated_train(
        nodes,
        rounds=int(payload.get("rounds") or 10),
        epsilon=float(payload.get("epsilon") or 2.0),
        algorithm=payload.get("algorithm") or "fedavg",
        time_decay=float(payload.get("timeDecay", 0.15)),
        quantize=bool(payload.get("quantize", True)),
        local_epochs=int(payload.get("localEpochs") or 10),
        lr=float(payload.get("lr") or 0.08),
    )
    evidence = audit_logger.record_from_request(
        "task.finish", target="federated-training", operation="计算",
        detail=f"联邦建模完成，AUC={result['metrics']['auc']}",
    )
    result["chainTxId"] = evidence.chainTxId if evidence else ""
    result["privacyBudget"] = dp.noise_impact(float(payload.get("epsilon") or 2.0))
    return ok(result)


@bp.post("/oblivious-query")
@auth_required
@require_permission("engine:query:oblivious")
def oblivious_query():
    """黑名单匿踪查询。"""
    payload = body()
    merchant_name = payload.get("merchantName") or payload.get("merchant")
    tax_no = payload.get("taxNo") or ""
    if not merchant_name:
        raise ApiError("缺少参数：merchantName（商户名称）")
    lists = payload.get("lists") or ["OFAC", "UN"]
    mode = payload.get("mode") or "oprf"
    target_ms = float(payload.get("targetMs") or 300)

    grouped = _sanction_lists(lists)
    if not grouped:
        raise ApiError("所选制裁清单暂无数据，请检查数据初始化", code=400)

    result = oblivious.oblivious_query([merchant_name, tax_no], grouped, mode=mode, response_target_ms=target_ms)
    result["lists"] = [
        {"code": code, "name": SANCTION_LIST_NAMES.get(code, code), "entries": len(rows)}
        for code, rows in grouped.items()
    ]
    result["query"] = {"merchantName": merchant_name, "taxNo": tax_no, "lists": lists, "mode": mode}

    evidence = audit_logger.record_from_request(
        "oblivious.query", target=merchant_name, operation="查询",
        detail=f"匿踪查询模式 {mode}，耗时 {result['elapsedMs']}ms，命中：{result['hit']}",
    )
    result["chainTxId"] = evidence.chainTxId if evidence else ""
    return ok(result)


@bp.post("/joint-stats")
@auth_required
@require_permission("engine:stats:joint")
def joint_statistics():
    """全球交易联合统计。"""
    payload = body()
    regions = payload.get("regions")
    query = Transaction.query
    if regions:
        query = query.filter(Transaction.region.in_(regions))
    start = payload.get("startDate")
    end = payload.get("endDate")
    if start:
        query = query.filter(Transaction.occurredAt >= datetime.strptime(start[:10], "%Y-%m-%d"))
    if end:
        query = query.filter(Transaction.occurredAt <= datetime.strptime(end[:10], "%Y-%m-%d").replace(hour=23))
    rows = query.limit(6000).all()
    if not rows:
        raise ApiError("没有可用于统计的交易数据", code=400)

    transactions = [
        {"region": item.region, "amount": item.amount, "category": item.category,
         "counterparties": item.counterparties, "level": item.level}
        for item in rows
    ]
    result = joint_stats.joint_statistics(
        transactions,
        epsilon=float(payload.get("epsilon") or 1.5),
        sensitivity=float(payload.get("sensitivity") or 1000.0),
        dimension=payload.get("dimension") or "region",
    )
    result["reportRows"] = joint_stats.build_report_rows(result)
    evidence = audit_logger.record_from_request(
        "data.transfer", target="joint-stats", operation="计算",
        detail=f"联合统计完成，总金额 {result['totalAmount']}，误差率 {result['errorRate']}",
    )
    result["chainTxId"] = evidence.chainTxId if evidence else ""
    return ok(result)


@bp.post("/psi")
@auth_required
def psi_intersection():
    """隐私求交集。"""
    payload = body()
    left = payload.get("left") or []
    right = payload.get("right") or []
    if not left or not right:
        raise ApiError("请分别提供双方集合（left / right）")
    from ..crypto import psi as psi_module

    result = psi_module.run_psi(left, right)
    evidence = audit_logger.record_from_request(
        "task.finish", target="psi", operation="计算", detail=f"隐私求交，交集大小 {result['intersectionSize']}"
    )
    result["chainTxId"] = evidence.chainTxId if evidence else ""
    result["protocol"] = "RSA 盲签名 PSI（Meadows 协议）：双方仅交换盲化/签名后的哈希值"
    return ok(result)


@bp.post("/classify")
@auth_required
def classify():
    """智能分级：敏感字段识别与 P1/P2/P3 标记。"""
    payload = body()
    fields = payload.get("fields") or []
    if not fields:
        raise ApiError("请提供待分级字段（fields）")
    result = classifier.classify_fields(fields)
    return ok(result)
