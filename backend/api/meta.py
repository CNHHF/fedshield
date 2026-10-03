# -*- coding: utf-8 -*-
"""元数据接口（/api/meta）：节点、数据集、合作方、算法模板、法规库等下拉字典。"""

from __future__ import annotations

from flask import Blueprint

from ..compliance import regulation_lib, rule_engine
from ..extensions import db
from ..models import CollaborationNode, Dataset, Partner
from ..utils.deps import auth_required
from ..utils.response import ok

bp = Blueprint("meta", __name__, url_prefix="/api/meta")

# 算法模板（对应文档「自动匹配 XGBoost、逻辑回归等预设算法模板」）
ALGORITHMS = [
    {
        "code": "fedavg",
        "name": "FedAvg 联邦平均",
        "desc": "横向联邦学习默认算法：各节点本地训练后按样本量加权聚合全局模型",
        "engine": "federated",
        "hyperParams": [
            {"key": "rounds", "label": "聚合轮次", "type": "number", "default": 10, "min": 1, "max": 50},
            {"key": "localEpochs", "label": "本地训练轮数", "type": "number", "default": 10, "min": 1, "max": 50},
            {"key": "lr", "label": "学习率", "type": "number", "default": 0.08, "min": 0.001, "max": 1},
        ],
    },
    {
        "code": "fedprox",
        "name": "FedProx 近端正则",
        "desc": "在 FedAvg 基础上加入近端项，缓解 Non-IID 跨境数据导致的模型漂移，迭代速度提升约 30%",
        "engine": "federated",
        "hyperParams": [
            {"key": "rounds", "label": "聚合轮次", "type": "number", "default": 10, "min": 1, "max": 50},
            {"key": "mu", "label": "近端项系数", "type": "number", "default": 0.01, "min": 0, "max": 1},
        ],
    },
    {
        "code": "logistic",
        "name": "逻辑回归（联合风控）",
        "desc": "可解释性强的风控基线模型，支持密文域聚合与差分隐私保护",
        "engine": "federated",
        "hyperParams": [
            {"key": "l2", "label": "L2 正则系数", "type": "number", "default": 0.001, "min": 0, "max": 1},
        ],
    },
    {
        "code": "xgboost",
        "name": "XGBoost 梯度提升树",
        "desc": "直方图分箱 + 联邦梯度聚合，适配高维稀疏跨境交易特征（实测 AUC 约 0.89）",
        "engine": "federated",
        "hyperParams": [
            {"key": "maxDepth", "label": "树深度", "type": "number", "default": 6, "min": 1, "max": 12},
            {"key": "nEstimators", "label": "树数量", "type": "number", "default": 120, "min": 10, "max": 500},
            {"key": "learningRate", "label": "学习率", "type": "number", "default": 0.1, "min": 0.01, "max": 1},
        ],
    },
    {
        "code": "paillier",
        "name": "Paillier 同态加密",
        "desc": "半同态加密：支持密文加法与明文标量乘，用于密文域比对与密文域聚合",
        "engine": "homomorphic",
        "hyperParams": [
            {"key": "keyBits", "label": "密钥长度", "type": "select", "default": 1024, "options": [512, 1024, 2048]},
        ],
    },
    {
        "code": "sm4",
        "name": "国密 SM4 + HMAC",
        "desc": "GB/T 32907-2016 分组密码，CBC 模式 + Encrypt-then-MAC 完整性保护",
        "engine": "homomorphic",
        "hyperParams": [],
    },
    {
        "code": "oprf",
        "name": "RSA 盲签名 OPRF",
        "desc": "匿踪查询生产模式：清单方仅做一次变换，查询方盲化后比对，响应稳定在毫秒级",
        "engine": "oblivious",
        "hyperParams": [],
    },
    {
        "code": "psi-rsa",
        "name": "RSA 盲签名隐私求交",
        "desc": "双方仅交换盲化/签名后的哈希值，不暴露各自集合与交集以外信息",
        "engine": "psi",
        "hyperParams": [],
    },
]

TASK_TYPES = [
    {"code": "federated", "name": "联邦学习建模", "tech": "联邦学习 + 差分隐私 + 同态聚合",
     "desc": "跨境联合风控建模，原始数据不出域", "engine": "engine/federated.py"},
    {"code": "homomorphic", "name": "同态加密计算", "tech": "Paillier 半同态加密",
     "desc": "密文域求和、密文域比对与风险评估", "engine": "crypto/paillier.py"},
    {"code": "oblivious", "name": "隐匿查询", "tech": "Paillier 密文比对 / RSA OPRF",
     "desc": "制裁清单匿踪查询，查询方与清单方互不泄露", "engine": "engine/oblivious.py"},
    {"code": "statistics", "name": "联合统计", "tech": "同态求和 + 差分隐私",
     "desc": "全球交易联合统计与监管申报口径输出", "engine": "engine/joint_stats.py"},
    {"code": "psi", "name": "隐私求交集", "tech": "RSA 盲签名 PSI",
     "desc": "跨境商户信息核验与白名单比对", "engine": "crypto/psi.py"},
]

REPORT_TYPES = [
    {"code": "GDPR", "name": "GDPR 合规评估报告", "regulation": "欧盟《通用数据保护条例》",
     "desc": "面向欧盟监管机构，覆盖数据主体权利、跨境传输机制与 DPIA"},
    {"code": "PIPL", "name": "个人信息保护法（PIPL）合规报告", "regulation": "中国《个人信息保护法》",
     "desc": "面向网信部门，覆盖单独同意、出境评估与境内存储"},
    {"code": "CCPA", "name": "加州消费者隐私法（CCPA）报告", "regulation": "美国加州 CCPA/CPRA",
     "desc": "覆盖知情权、删除权、退出出售权"},
    {"code": "FATF", "name": "FATF 反洗钱合规报告", "regulation": "FATF 四十项建议",
     "desc": "覆盖客户身份识别、制裁筛查与可疑交易监测"},
    {"code": "SCHREMS_II", "name": "欧盟 Schrems II 判决合规报告", "regulation": "CJEU Schrems II",
     "desc": "覆盖传输影响评估与补充技术措施"},
    {"code": "PDPA", "name": "新加坡 PDPA 合规报告", "regulation": "新加坡《个人数据保护法》",
     "desc": "覆盖同意机制、数据保护协议与泄露通知"},
    {"code": "DSL", "name": "数据安全法合规报告", "regulation": "中国《数据安全法》",
     "desc": "覆盖分类分级、重要数据目录与风险评估"},
    {"code": "FATF_TRAVEL", "name": "旅行规则执行报告", "regulation": "FATF R.16",
     "desc": "覆盖跨境转账随附信息完整率"},
    {"code": "DPIA", "name": "数据保护影响评估（DPIA）报告", "regulation": "GDPR 第 35 条",
     "desc": "高风险处理活动的影响评估与缓解措施"},
    {"code": "SCC", "name": "SCC 条款执行情况报告", "regulation": "GDPR 第 46 条",
     "desc": "覆盖标准合同条款签订与履行"},
    {"code": "PCI", "name": "PCI-DSS 数据安全合规报告", "regulation": "PCI-DSS v4.0",
     "desc": "覆盖 PAN 加密存储与访问控制"},
    {"code": "CROSS_BORDER_STATS", "name": "全球交易统计申报报告", "regulation": "海关总署 / 欧盟税务部门",
     "desc": "跨境电商零售进口清单申报与 VAT 申报统计"},
]

BUDGET_CATEGORIES = [
    {"code": "anti_fraud", "name": "反欺诈模型训练", "desc": "跨境电商联合风控建模场景"},
    {"code": "profile", "name": "用户画像分析", "desc": "商户画像与分层运营场景"},
    {"code": "decision", "name": "风控决策", "desc": "实时风控决策与拦截场景"},
    {"code": "screening", "name": "制裁清单筛查", "desc": "外贸 B2B 黑名单匿踪查询场景"},
    {"code": "statistics", "name": "监管统计申报", "desc": "全球交易联合统计与申报场景"},
    {"code": "credit", "name": "联合信用评分", "desc": "跨机构联合信用评分场景"},
]

DICTS = {
    "taskStatus": [
        {"code": "pending", "name": "待启动"}, {"code": "running", "name": "运行中"},
        {"code": "paused", "name": "已暂停"}, {"code": "finished", "name": "已完成"},
        {"code": "failed", "name": "执行失败"}, {"code": "canceled", "name": "已取消"},
    ],
    "grantStatus": [
        {"code": "pending", "name": "待审核"}, {"code": "active", "name": "生效中"},
        {"code": "expired", "name": "已过期"}, {"code": "revoked", "name": "已撤销"},
    ],
    "reportStatus": [
        {"code": "generating", "name": "生成中"}, {"code": "generated", "name": "已生成"},
        {"code": "failed", "name": "失败"},
    ],
    "riskLevel": [
        {"code": "high", "name": "高风险"}, {"code": "medium", "name": "中风险"}, {"code": "low", "name": "低风险"},
    ],
    "dataLevel": [
        {"code": "P1", "name": "P1 高敏感"}, {"code": "P2", "name": "P2 中敏感"}, {"code": "P3", "name": "P3 低敏感"},
    ],
    # 血缘筛选字典（与前端 views/lineage 的筛选项取值一致）
    "dataType": [
        {"code": "user", "name": "用户数据"}, {"code": "transaction", "name": "交易数据"},
        {"code": "list", "name": "清单数据"},
    ],
    "lineageStage": [
        {"code": "collect", "name": "采集"}, {"code": "extract", "name": "抽取"},
        {"code": "transform", "name": "转换"}, {"code": "compute", "name": "计算"},
        {"code": "apply", "name": "应用"},
    ],
    "operation": [
        {"code": "query", "name": "查询"}, {"code": "update", "name": "修改"},
        {"code": "delete", "name": "删除"}, {"code": "export", "name": "导出"},
    ],
    "alertLevel": [
        {"code": "high", "name": "高危"}, {"code": "medium", "name": "中度"}, {"code": "low", "name": "轻度"},
    ],
}


@bp.get("/nodes")
@auth_required
def nodes():
    """跨境协作节点列表。"""
    return ok([item.to_dict() for item in CollaborationNode.query.order_by(CollaborationNode.id).all()])


@bp.get("/datasets")
@auth_required
def datasets():
    """数据集列表（含 P1/P2/P3 分级）。"""
    return ok([item.to_dict() for item in Dataset.query.order_by(Dataset.level, Dataset.id).all()])


@bp.get("/partners")
@auth_required
def partners():
    """已认证合作方列表（含资质证书有效期）。"""
    return ok([item.to_dict() for item in Partner.query.order_by(Partner.id).all()])


@bp.get("/algorithms")
@auth_required
def algorithms():
    return ok(ALGORITHMS)


@bp.get("/task-types")
@auth_required
def task_types():
    return ok(TASK_TYPES)


@bp.get("/report-types")
@auth_required
def report_types():
    return ok(REPORT_TYPES)


@bp.get("/regulations")
@auth_required
def regulations():
    """全球法规库列表（按契约返回数组；覆盖度统计见 /regulations/coverage）。"""
    return ok(regulation_lib.all_regulations())


@bp.get("/regulations/coverage")
@auth_required
def regulation_coverage():
    """法规库覆盖度统计（明确区分已人工校对条目与区域模板条目）。"""
    return ok(regulation_lib.coverage_stats())


@bp.get("/budget-categories")
@auth_required
def budget_categories():
    return ok(BUDGET_CATEGORIES)


@bp.get("/dicts")
@auth_required
def dicts():
    """前端下拉字典汇总。"""
    return ok(DICTS)


@bp.get("/rule-templates")
@auth_required
def rule_templates():
    """规则画布节点模板（与 /api/compliance/rule-templates 等价，便于元数据统一入口）。"""
    return ok(rule_engine.rule_templates())


@bp.get("/health")
def health():
    """健康检查（探活用，无需鉴权）。"""
    return ok(
        {
            "status": "up",
            "nodes": db.session.query(CollaborationNode).count(),
            "datasets": db.session.query(Dataset).count(),
        }
    )
