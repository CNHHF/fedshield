# -*- coding: utf-8 -*-
"""审计日志：业务操作留痕 + 风险评分 + 防篡改签名 + 链上存证。

对应文档「审计模块升级」：在 ELK 日志方案基础上新增风险评分与防篡改签名字段，
所有高敏感操作同时写入联盟链，满足 GDPR（7 年）/ PIPL（5 年）留存与监管调证要求。
"""

from __future__ import annotations

from typing import Optional

from flask import g, has_request_context, request

from ..extensions import db
from ..models import AuditLog, now
from ..utils.security import hash_chain, sign_payload
from . import chain

# 需要强制上链存证的动作（高敏感操作）
ON_CHAIN_ACTIONS = {
    "crypto.decrypt", "oblivious.query", "task.create", "task.finish", "report.generate",
    "grant.create", "grant.revoke", "rule.update", "data.transfer", "data.export",
    "chain.verify", "budget.adjust",
}


def record(actor: str, role: str, action: str, *, target: str = "", data_id: str = "",
           data_type: str = "", node: str = "", operation: str = "查询", result: str = "success",
           risk_score: float = 0.0, detail: str = "", on_chain: Optional[bool] = None) -> AuditLog:
    """写入一条审计日志。

    参数说明：
    - action：动作标识（login / task.create / oblivious.query / crypto.decrypt …）
    - operation：监管检索口径的操作类型（查询/修改/删除/导出）
    - risk_score：零信任风险评分（0~1），由 utils.deps.evaluate_risk 计算
    - on_chain：是否强制上链；默认按 ON_CHAIN_ACTIONS 判断
    """
    previous = AuditLog.query.order_by(AuditLog.id.desc()).first()
    prev_hash = previous.hash if previous and previous.hash else chain.GENESIS_HASH

    signature = sign_payload(
        {"actor": actor, "action": action, "target": target, "ts": now().strftime("%Y-%m-%d %H:%M:%S")}
    )

    log = AuditLog(
        actor=actor,
        role=role,
        action=action,
        target=target,
        dataId=data_id,
        dataType=data_type,
        node=node,
        operation=operation,
        result=result,
        riskScore=risk_score,
        signature=signature[:32],
        prevHash=prev_hash,
    )
    log.hash = hash_chain(prev_hash, {"actor": actor, "action": action, "target": target, "signature": signature})
    if has_request_context():
        log.detail = (detail or "")[:500]
        forwarded = request.headers.get("X-Forwarded-For", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
        if client_ip and not data_id:
            log.detail = (log.detail + f" [ip={client_ip}]").strip()[:500]
    else:
        log.detail = (detail or "")[:500]

    db.session.add(log)
    db.session.flush()

    should_chain = (action in ON_CHAIN_ACTIONS) if on_chain is None else bool(on_chain)
    if should_chain:
        block = chain.append_block(
            {
                "action": action,
                "actor": actor,
                "role": role,
                "target": target,
                "dataId": data_id,
                "result": result,
                "logHash": log.hash,
            }
        )
        log.chainTxId = block.txId

    db.session.commit()
    return log


def record_from_request(action: str, **kwargs) -> Optional[AuditLog]:
    """在请求上下文中记录当前登录用户的审计日志。"""
    user = getattr(g, "user", None)
    role = getattr(g, "role", "")
    if user is None:
        return None
    return record(user.username, role, action, **kwargs)
