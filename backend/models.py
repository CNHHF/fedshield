# -*- coding: utf-8 -*-
"""数据模型层（SQLAlchemy ORM）。

设计说明
--------
- 表前缀统一为 `fs_`，便于与 PingPong 既有库表共存；
- 复杂结构（规则画布节点、任务结果、密文信封）使用 JSON 列，兼容 SQLite 与 MySQL 5.7+；
- 所有时间字段使用本地时区的 datetime，序列化时统一格式化为 `YYYY-MM-DD HH:MM:SS`。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .extensions import db


def now() -> datetime:
    return datetime.now()


def iso(value: Optional[datetime]) -> Optional[str]:
    """统一时间序列化格式。"""
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


class TimestampMixin:
    createdAt = db.Column(db.DateTime, default=now, nullable=False)
    updatedAt = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)


# ---------------------------------------------------------------------------
# 用户与认证
# ---------------------------------------------------------------------------


class User(TimestampMixin, db.Model):
    """平台用户：PingPong 内部角色 / 商户 / 监管机构 / 数据安全管理员。"""

    __tablename__ = "fs_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    passwordHash = db.Column(db.String(255), nullable=False)
    displayName = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(32), nullable=False, index=True)  # pingpong/merchant/regulator/admin
    org = db.Column(db.String(128), default="")
    region = db.Column(db.String(16), default="CN")
    email = db.Column(db.String(128), default="")
    phone = db.Column(db.String(32), default="")
    # 数字证书与多因素认证（零信任架构的身份要素）
    certNo = db.Column(db.String(64), default="")
    certExpireAt = db.Column(db.DateTime)
    mfaEnabled = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(16), default="active")  # active / locked / disabled
    lastLoginAt = db.Column(db.DateTime)
    lastLoginIp = db.Column(db.String(64), default="")

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "displayName": self.displayName,
            "role": self.role,
            "org": self.org,
            "region": self.region,
            "email": self.email,
            "certNo": self.certNo,
            "certExpireAt": iso(self.certExpireAt),
            "mfaEnabled": self.mfaEnabled,
            "status": self.status,
            "lastLoginAt": iso(self.lastLoginAt),
        }


class LoginSession(TimestampMixin, db.Model):
    """登录会话：用于异常登录检测（跨地区同时登录等）。"""

    __tablename__ = "fs_login_session"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, index=True)
    role = db.Column(db.String(32), default="")
    region = db.Column(db.String(32), default="")
    ip = db.Column(db.String(64), default="")
    loginAt = db.Column(db.DateTime, default=now)
    risk = db.Column(db.String(16), default="normal")  # normal / medium / high
    note = db.Column(db.String(255), default="")
    active = db.Column(db.Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "region": self.region,
            "ip": self.ip,
            "loginAt": iso(self.loginAt),
            "risk": self.risk,
            "note": self.note,
        }


class TokenBlacklist(db.Model):
    """JWT 黑名单（登出/熔断后令牌立即失效）。"""

    __tablename__ = "fs_token_blacklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    username = db.Column(db.String(64), default="")
    reason = db.Column(db.String(128), default="logout")
    expireAt = db.Column(db.DateTime)
    createdAt = db.Column(db.DateTime, default=now)


# ---------------------------------------------------------------------------
# 节点、数据集与合作方
# ---------------------------------------------------------------------------


class CollaborationNode(TimestampMixin, db.Model):
    """跨境协作节点（欧盟法兰克福、中国杭州、新加坡等）。"""

    __tablename__ = "fs_node"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    region = db.Column(db.String(16), default="CN")
    endpoint = db.Column(db.String(128), default="")
    status = db.Column(db.String(16), default="online")  # online / degraded / offline
    latencyMs = db.Column(db.Integer, default=40)
    bandwidthMbps = db.Column(db.Integer, default=10)
    certNo = db.Column(db.String(64), default="")
    certExpireAt = db.Column(db.DateTime)
    tlsVersion = db.Column(db.String(16), default="TLSv1.3")
    role = db.Column(db.String(32), default="participant")  # participant / aggregator / regulator

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "region": self.region,
            "endpoint": self.endpoint,
            "status": self.status,
            "latencyMs": self.latencyMs,
            "bandwidthMbps": self.bandwidthMbps,
            "certNo": self.certNo,
            "certExpireAt": iso(self.certExpireAt),
            "tlsVersion": self.tlsVersion,
            "role": self.role,
        }


class Dataset(TimestampMixin, db.Model):
    """数据集（含敏感度分级 P1/P2/P3 与字段清单）。"""

    __tablename__ = "fs_dataset"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(48), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    level = db.Column(db.String(4), default="P2", index=True)
    owner = db.Column(db.String(64), default="")
    region = db.Column(db.String(16), default="CN")
    category = db.Column(db.String(32), default="交易数据")  # 交易数据 / 用户数据 / 清单数据
    rows = db.Column(db.Integer, default=0)
    fields = db.Column(db.JSON, default=list)
    storage = db.Column(db.String(32), default="HDFS")
    description = db.Column(db.String(255), default="")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "owner": self.owner,
            "region": self.region,
            "category": self.category,
            "rows": self.rows,
            "fields": self.fields or [],
            "storage": self.storage,
            "description": self.description,
        }


class Partner(TimestampMixin, db.Model):
    """已认证合作方（银行、支付机构、监管清单服务方）。"""

    __tablename__ = "fs_partner"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(48), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    region = db.Column(db.String(16), default="EU")
    orgType = db.Column(db.String(32), default="银行")
    certNo = db.Column(db.String(64), default="")
    certExpireAt = db.Column(db.DateTime)
    verified = db.Column(db.Boolean, default=True)
    nodeCode = db.Column(db.String(32), default="")

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "region": self.region,
            "orgType": self.orgType,
            "certNo": self.certNo,
            "certExpireAt": iso(self.certExpireAt),
            "verified": self.verified,
            "nodeCode": self.nodeCode,
        }


# ---------------------------------------------------------------------------
# 隐私计算任务
# ---------------------------------------------------------------------------


class ComputeTask(TimestampMixin, db.Model):
    """隐私计算任务（联邦学习 / 同态加密计算 / 隐匿查询 / 联合统计 / 隐私求交）。"""

    __tablename__ = "fs_task"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    type = db.Column(db.String(32), default="federated", index=True)
    algorithm = db.Column(db.String(32), default="fedavg")
    status = db.Column(db.String(16), default="pending", index=True)
    progress = db.Column(db.Integer, default=0)
    epsilon = db.Column(db.Float, default=2.0)
    rounds = db.Column(db.Integer, default=10)
    description = db.Column(db.String(255), default="")
    partners = db.Column(db.JSON, default=list)   # 参与节点编码
    datasets = db.Column(db.JSON, default=list)   # 数据集编码
    hyper = db.Column(db.JSON, default=dict)      # 超参数
    resource = db.Column(db.JSON, default=dict)   # 资源消耗
    result = db.Column(db.JSON, default=dict)     # 计算结果
    createdBy = db.Column(db.String(64), default="")
    startedAt = db.Column(db.DateTime)
    finishedAt = db.Column(db.DateTime)
    durationMs = db.Column(db.Integer, default=0)
    chainTxId = db.Column(db.String(64), default="")

    def to_dict(self, with_result: bool = False) -> dict:
        data = {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "algorithm": self.algorithm,
            "status": self.status,
            "progress": self.progress,
            "epsilon": self.epsilon,
            "rounds": self.rounds,
            "description": self.description,
            "partners": self.partners or [],
            "datasets": self.datasets or [],
            "hyper": self.hyper or {},
            "resource": self.resource or {},
            "createdBy": self.createdBy,
            "createdAt": iso(self.createdAt),
            "startedAt": iso(self.startedAt),
            "finishedAt": iso(self.finishedAt),
            "durationMs": self.durationMs,
            "chainTxId": self.chainTxId,
        }
        if with_result:
            data["result"] = self.result or {}
        return data


class TaskLog(db.Model):
    """任务执行日志（加密算法调用日志，可按时间戳导出给监管）。"""

    __tablename__ = "fs_task_log"

    id = db.Column(db.Integer, primary_key=True)
    taskId = db.Column(db.Integer, db.ForeignKey("fs_task.id"), index=True)
    ts = db.Column(db.DateTime, default=now)
    stage = db.Column(db.String(32), default="")
    level = db.Column(db.String(16), default="info")
    message = db.Column(db.String(512), default="")
    cipher = db.Column(db.String(64), default="")
    digest = db.Column(db.String(64), default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": iso(self.ts),
            "stage": self.stage,
            "level": self.level,
            "message": self.message,
            "cipher": self.cipher,
            "digest": self.digest,
        }


# ---------------------------------------------------------------------------
# 合规规则与报告
# ---------------------------------------------------------------------------


class ComplianceRule(TimestampMixin, db.Model):
    """合规规则（可视化画布节点 + 连线，落库为 JSON）。"""

    __tablename__ = "fs_rule"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(512), default="")
    scene = db.Column(db.String(32), default="data_transfer")  # data_transfer/authorization/compute/masking
    priority = db.Column(db.Integer, default=10)
    enabled = db.Column(db.Boolean, default=True, index=True)
    version = db.Column(db.Integer, default=1)
    nodes = db.Column(db.JSON, default=list)
    edges = db.Column(db.JSON, default=list)
    updatedBy = db.Column(db.String(64), default="")
    hitCount = db.Column(db.Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "scene": self.scene,
            "priority": self.priority,
            "enabled": self.enabled,
            "version": self.version,
            "nodes": self.nodes or [],
            "edges": self.edges or [],
            "updatedBy": self.updatedBy,
            "updatedAt": iso(self.updatedAt),
            "hitCount": self.hitCount,
        }


class ComplianceReport(TimestampMixin, db.Model):
    """合规报告（GDPR / PIPL / CCPA / FATF / SchremsII 等）。"""

    __tablename__ = "fs_report"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    type = db.Column(db.String(32), nullable=False, index=True)
    typeName = db.Column(db.String(64), default="")
    status = db.Column(db.String(16), default="generated", index=True)
    periodStart = db.Column(db.Date)
    periodEnd = db.Column(db.Date)
    regions = db.Column(db.JSON, default=list)
    advanced = db.Column(db.JSON, default=dict)
    content = db.Column(db.JSON, default=dict)
    sizeKb = db.Column(db.Float, default=0)
    createdBy = db.Column(db.String(64), default="")
    chainTxId = db.Column(db.String(64), default="")

    def to_dict(self, with_content: bool = False) -> dict:
        data = {
            "id": self.id,
            "code": self.code,
            "type": self.type,
            "typeName": self.typeName,
            "status": self.status,
            "periodStart": self.periodStart.strftime("%Y-%m-%d") if self.periodStart else None,
            "periodEnd": self.periodEnd.strftime("%Y-%m-%d") if self.periodEnd else None,
            "regions": self.regions or [],
            "createdAt": iso(self.createdAt),
            "createdBy": self.createdBy,
            "sizeKb": self.sizeKb,
            "chainTxId": self.chainTxId,
        }
        if with_content:
            data["content"] = self.content or {}
        return data


class ComplianceTrendPoint(db.Model):
    """跨境合规趋势（按地区、按月）。"""

    __tablename__ = "fs_compliance_trend"

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.String(7), index=True)  # YYYY-MM
    region = db.Column(db.String(16), index=True)
    complianceRate = db.Column(db.Float, default=0.9)
    issues = db.Column(db.Integer, default=0)
    reports = db.Column(db.Integer, default=0)


class Alert(TimestampMixin, db.Model):
    """合规/风险预警。"""

    __tablename__ = "fs_alert"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    level = db.Column(db.String(16), default="medium")  # high / medium / low
    title = db.Column(db.String(128), default="")
    content = db.Column(db.String(512), default="")
    requirement = db.Column(db.String(255), default="")
    source = db.Column(db.String(64), default="合规规则引擎")
    status = db.Column(db.String(16), default="open")  # open / handling / closed
    createdBy = db.Column(db.String(64), default="system")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "level": self.level,
            "title": self.title,
            "content": self.content,
            "requirement": self.requirement,
            "source": self.source,
            "status": self.status,
            "createdAt": iso(self.createdAt),
        }


# ---------------------------------------------------------------------------
# 授权（多方协同权限管控）
# ---------------------------------------------------------------------------


class DataGrant(TimestampMixin, db.Model):
    """数据授权记录（零信任动态授权的载体）。"""

    __tablename__ = "fs_grant"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    partner = db.Column(db.String(128), nullable=False)
    partnerRegion = db.Column(db.String(16), default="EU")
    datasetScope = db.Column(db.JSON, default=list)
    purpose = db.Column(db.String(64), default="")
    level = db.Column(db.String(32), default="readonly")  # readonly / result_only / compute
    permissions = db.Column(db.JSON, default=list)
    validFrom = db.Column(db.DateTime)
    validTo = db.Column(db.DateTime)
    status = db.Column(db.String(16), default="pending", index=True)  # pending/active/expired/revoked
    remark = db.Column(db.String(255), default="")
    applicant = db.Column(db.String(64), default="")
    approver = db.Column(db.String(64), default="")
    history = db.Column(db.JSON, default=list)
    certExpireAt = db.Column(db.DateTime)

    @property
    def computed_status(self) -> str:
        """按有效期实时推导状态（已过期的授权不依赖定时任务修正）。"""
        if self.status in ("revoked", "pending"):
            return self.status
        if self.validTo and self.validTo < now():
            return "expired"
        return self.status

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "partner": self.partner,
            "partnerRegion": self.partnerRegion,
            "datasetScope": self.datasetScope or [],
            "purpose": self.purpose,
            "level": self.level,
            "permissions": self.permissions or [],
            "validFrom": iso(self.validFrom),
            "validTo": iso(self.validTo),
            "status": self.computed_status,
            "remark": self.remark,
            "applicant": self.applicant,
            "approver": self.approver,
            "history": self.history or [],
            "certExpireAt": iso(self.certExpireAt),
            "remainDays": max(0, (self.validTo - now()).days) if self.validTo else 0,
            "createdAt": iso(self.createdAt),
        }


# ---------------------------------------------------------------------------
# 隐私预算
# ---------------------------------------------------------------------------


class BudgetItem(TimestampMixin, db.Model):
    """项目级隐私预算明细。"""

    __tablename__ = "fs_budget_item"

    id = db.Column(db.Integer, primary_key=True)
    project = db.Column(db.String(64), nullable=False)
    category = db.Column(db.String(64), default="反欺诈模型训练")
    total = db.Column(db.Float, default=10.0)
    used = db.Column(db.Float, default=0.0)
    level = db.Column(db.String(16), default="P2")
    note = db.Column(db.String(255), default="")

    def to_dict(self) -> dict:
        remaining = max(0.0, self.total - self.used)
        return {
            "id": self.id,
            "project": self.project,
            "category": self.category,
            "total": round(self.total, 4),
            "used": round(self.used, 4),
            "remaining": round(remaining, 4),
            "usedRatio": round(self.used / self.total, 4) if self.total else 0.0,
            "level": self.level,
            "note": self.note,
            "updatedAt": iso(self.updatedAt),
        }


class BudgetApplication(TimestampMixin, db.Model):
    """预算申请。"""

    __tablename__ = "fs_budget_application"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    project = db.Column(db.String(64), nullable=False)
    category = db.Column(db.String(64), default="")
    amount = db.Column(db.Float, default=0.0)
    reason = db.Column(db.String(255), default="")
    status = db.Column(db.String(16), default="pending", index=True)  # pending/approved/rejected
    applicant = db.Column(db.String(64), default="")
    approver = db.Column(db.String(64), default="")
    comment = db.Column(db.String(255), default="")
    expectedAt = db.Column(db.Date)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "project": self.project,
            "category": self.category,
            "amount": round(self.amount, 4),
            "reason": self.reason,
            "status": self.status,
            "applicant": self.applicant,
            "approver": self.approver,
            "comment": self.comment,
            "expectedAt": self.expectedAt.strftime("%Y-%m-%d") if self.expectedAt else None,
            "createdAt": iso(self.createdAt),
        }


class BudgetAdjustment(db.Model):
    """预算调整记录（内部转移 / 单项额度调整）。"""

    __tablename__ = "fs_budget_adjustment"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    fromProject = db.Column(db.String(64), default="")
    toProject = db.Column(db.String(64), default="")
    amount = db.Column(db.Float, default=0.0)
    operator = db.Column(db.String(64), default="")
    note = db.Column(db.String(255), default="")
    type = db.Column(db.String(16), default="transfer")  # transfer / adjust
    createdAt = db.Column(db.DateTime, default=now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "fromProject": self.fromProject,
            "toProject": self.toProject,
            "amount": round(self.amount, 4),
            "operator": self.operator,
            "note": self.note,
            "type": self.type,
            "createdAt": iso(self.createdAt),
        }


class BudgetTrend(db.Model):
    """月度预算消耗趋势（用于图表）。"""

    __tablename__ = "fs_budget_trend"

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.String(7), index=True)
    used = db.Column(db.Float, default=0.0)
    remaining = db.Column(db.Float, default=0.0)
    usedRatio = db.Column(db.Float, default=0.0)
    scene = db.Column(db.String(32), default="跨境电商联合风控")


# ---------------------------------------------------------------------------
# 业务数据：制裁清单、商户、交易
# ---------------------------------------------------------------------------


class SanctionEntry(TimestampMixin, db.Model):
    """监管制裁清单条目（OFAC / 联合国 / 欧盟等）。"""

    __tablename__ = "fs_sanction_entry"

    id = db.Column(db.Integer, primary_key=True)
    listName = db.Column(db.String(32), nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    alias = db.Column(db.JSON, default=list)
    taxNo = db.Column(db.String(64), default="")
    country = db.Column(db.String(32), default="")
    program = db.Column(db.String(64), default="")
    entityType = db.Column(db.String(32), default="企业")
    listedAt = db.Column(db.Date)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "list": self.listName,
            "name": self.name,
            "alias": self.alias or [],
            "taxNo": self.taxNo,
            "country": self.country,
            "program": self.program,
            "entityType": self.entityType,
        }


class Merchant(TimestampMixin, db.Model):
    """商户主数据。"""

    __tablename__ = "fs_merchant"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    region = db.Column(db.String(16), default="CN")
    taxNo = db.Column(db.String(64), default="")
    category = db.Column(db.String(32), default="电子产品")
    riskScore = db.Column(db.Float, default=0.2)
    riskLevel = db.Column(db.String(16), default="low")
    annualAmount = db.Column(db.Float, default=0.0)
    txCount = db.Column(db.Integer, default=0)
    tier = db.Column(db.String(16), default="中规模")  # 小规模/中规模/大规模


class Transaction(db.Model):
    """跨境交易明细（用于联合统计与血缘演示）。"""

    __tablename__ = "fs_transaction"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    merchantCode = db.Column(db.String(32), index=True)
    region = db.Column(db.String(16), index=True)
    destRegion = db.Column(db.String(16), default="EU")
    amount = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(8), default="CNY")
    category = db.Column(db.String(32), default="电子产品")
    counterparties = db.Column(db.Integer, default=1)
    level = db.Column(db.String(4), default="P2")
    riskLevel = db.Column(db.String(16), default="low")
    occurredAt = db.Column(db.DateTime, default=now)


# ---------------------------------------------------------------------------
# 数据血缘与审计
# ---------------------------------------------------------------------------


class LineageNode(TimestampMixin, db.Model):
    """数据血缘节点（数据源 / 处理环节 / 应用）。"""

    __tablename__ = "fs_lineage_node"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(48), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    type = db.Column(db.String(32), default="source")  # source/extract/transform/compute/application
    stage = db.Column(db.String(32), default="采集")
    owner = db.Column(db.String(64), default="")
    region = db.Column(db.String(16), default="CN")
    level = db.Column(db.String(4), default="P2")
    dataType = db.Column(db.String(32), default="交易数据")
    tags = db.Column(db.JSON, default=list)
    meta = db.Column(db.JSON, default=dict)
    processedAt = db.Column(db.DateTime, default=now)

    def to_dict(self) -> dict:
        return {
            "id": self.code,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "stage": self.stage,
            "owner": self.owner,
            "region": self.region,
            "level": self.level,
            "dataType": self.dataType,
            "tags": self.tags or [],
            "meta": self.meta or {},
            "processedAt": iso(self.processedAt),
        }


class LineageLink(db.Model):
    """数据血缘连线。"""

    __tablename__ = "fs_lineage_link"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(48), nullable=False, index=True)
    target = db.Column(db.String(48), nullable=False, index=True)
    operation = db.Column(db.String(64), default="流转")
    ts = db.Column(db.DateTime, default=now)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "operation": self.operation,
            "ts": iso(self.ts),
        }


class AuditLog(db.Model):
    """操作审计日志（含风险评分与防篡改签名，满足 ELK 检索式查询）。"""

    __tablename__ = "fs_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=now, index=True)
    actor = db.Column(db.String(64), default="", index=True)
    role = db.Column(db.String(32), default="")
    action = db.Column(db.String(64), default="", index=True)
    target = db.Column(db.String(128), default="")
    dataId = db.Column(db.String(48), default="", index=True)
    dataType = db.Column(db.String(32), default="")
    node = db.Column(db.String(32), default="")
    operation = db.Column(db.String(32), default="查询", index=True)
    result = db.Column(db.String(16), default="success")  # success / denied / failed
    riskScore = db.Column(db.Float, default=0.0)
    signature = db.Column(db.String(64), default="")
    prevHash = db.Column(db.String(64), default="")
    hash = db.Column(db.String(64), default="", index=True)
    chainTxId = db.Column(db.String(64), default="", index=True)
    detail = db.Column(db.String(512), default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": iso(self.ts),
            "actor": self.actor,
            "role": self.role,
            "action": self.action,
            "target": self.target,
            "dataId": self.dataId,
            "dataType": self.dataType,
            "node": self.node,
            "operation": self.operation,
            "result": self.result,
            "riskScore": round(self.riskScore, 3),
            "signature": self.signature,
            "hash": self.hash,
            "chainTxId": self.chainTxId,
            "detail": self.detail,
        }


class ChainBlock(db.Model):
    """联盟链存证区块（Hyperledger Fabric + Raft 共识的本地仿真实现）。"""

    __tablename__ = "fs_chain_block"

    id = db.Column(db.Integer, primary_key=True)
    height = db.Column(db.Integer, unique=True, nullable=False, index=True)
    txId = db.Column(db.String(64), unique=True, nullable=False, index=True)
    ts = db.Column(db.DateTime, default=now)
    node = db.Column(db.String(32), default="fabric-peer-0")
    channel = db.Column(db.String(32), default="fedshield-audit")
    payload = db.Column(db.JSON, default=dict)
    payloadDigest = db.Column(db.String(64), default="")
    prevHash = db.Column(db.String(64), default="")
    hash = db.Column(db.String(64), default="")

    def to_dict(self, with_payload: bool = False) -> dict:
        data = {
            "id": self.id,
            "height": self.height,
            "txId": self.txId,
            "ts": iso(self.ts),
            "node": self.node,
            "channel": self.channel,
            "payloadDigest": self.payloadDigest,
            "prevHash": self.prevHash,
            "hash": self.hash,
        }
        if with_payload:
            data["payload"] = self.payload or {}
        return data


class LineageRecord(db.Model):
    """链路记录（生成的溯源报告，可下载）。"""

    __tablename__ = "fs_lineage_record"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    dataId = db.Column(db.String(48), default="")
    range = db.Column(db.String(64), default="")
    nodes = db.Column(db.JSON, default=list)
    complianceTags = db.Column(db.JSON, default=list)
    generatedBy = db.Column(db.String(64), default="")
    chainTxId = db.Column(db.String(64), default="")
    createdAt = db.Column(db.DateTime, default=now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recordId": self.code,
            "dataId": self.dataId,
            "range": self.range,
            "nodes": self.nodes or [],
            "complianceTags": self.complianceTags or [],
            "generatedBy": self.generatedBy,
            "chainTxId": self.chainTxId,
            "generatedAt": iso(self.createdAt),
        }


class CircuitBreakerEvent(db.Model):
    """异常行为熔断事件（零信任动态授权的兜底机制）。"""

    __tablename__ = "fs_circuit_breaker"

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=now)
    username = db.Column(db.String(64), default="", index=True)
    rule = db.Column(db.String(64), default="")
    severity = db.Column(db.String(16), default="low")  # low / medium / high
    detail = db.Column(db.String(255), default="")
    lockUntil = db.Column(db.DateTime)
    status = db.Column(db.String(16), default="locked")  # locked / released / appealed


def next_code(prefix: str, sequence: int) -> str:
    """生成业务单据编码，例如 TASK-20260518-0007 / RPT-20260518-0003。"""
    return f"{prefix}-{now().strftime('%Y%m%d')}-{sequence:04d}"


__all__ = [
    "User", "LoginSession", "TokenBlacklist", "CollaborationNode", "Dataset", "Partner",
    "ComputeTask", "TaskLog", "ComplianceRule", "ComplianceReport", "ComplianceTrendPoint", "Alert",
    "DataGrant", "BudgetItem", "BudgetApplication", "BudgetAdjustment", "BudgetTrend",
    "SanctionEntry", "Merchant", "Transaction", "LineageNode", "LineageLink", "AuditLog",
    "ChainBlock", "LineageRecord", "CircuitBreakerEvent", "now", "iso", "next_code",
]

# ---------------------------------------------------------------------------
# 便捷时间工具（供业务层复用）
# ---------------------------------------------------------------------------


def days_later(days: int) -> datetime:
    return now() + timedelta(days=days)
