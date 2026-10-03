# -*- coding: utf-8 -*-
"""初始化演示数据（真实可复现的业务数据，不含随机占位文本）。

执行方式：
    python run.py --seed          # 建表 + 灌入演示数据（幂等：已有数据时跳过）
    flask --app backend.app:create_app seed
"""

from __future__ import annotations

import random
import zlib
from datetime import date, datetime, timedelta

from .compliance import rule_engine
from .crypto import policy
from .extensions import db
from .models import (
    Alert,
    BudgetApplication,
    BudgetItem,
    BudgetTrend,
    CollaborationNode,
    ComplianceReport,
    ComplianceRule,
    ComplianceTrendPoint,
    Dataset,
    DataGrant,
    LineageLink,
    LineageNode,
    Merchant,
    Partner,
    SanctionEntry,
    Transaction,
    User,
    next_code,
    now,
)
from .utils.security import hash_password

RANDOM = random.Random(20260518)

# ---------------------------------------------------------------------------
# 制裁清单（演示数据，非真实受制裁实体；名称均为虚构）
# ---------------------------------------------------------------------------

OFAC_ENTITIES = [
    ("Tehran Petro Trading Co", "IR-88213", "Iran", "SDN", "石油贸易"),
    ("Pyongyang Shipping Lines", "KP-10021", "DPRK", "SDN", "航运"),
    ("Damascus Bank Holding", "SY-40118", "Syria", "SDN", "金融"),
    ("Crimea Port Logistics", "RU-77201", "Russia", "SDN", "物流"),
    ("Havana Sugar Export SA", "CU-33012", "Cuba", "SDN", "农产品"),
    ("Caracas Gold Miners", "VE-21007", "Venezuela", "SDN", "矿产"),
    ("Minsk Arms Brokerage", "BY-55031", "Belarus", "SDN", "军工贸易"),
    ("Kabul Exchange House", "AF-11004", "Afghanistan", "SDN", "货币兑换"),
    ("Sanaa Import Group", "YE-66029", "Yemen", "SDN", "进出口"),
    ("Tripoli Maritime Co", "LY-88015", "Libya", "SDN", "航运"),
    ("Bangui Diamond Traders", "CF-14022", "Central African Republic", "SDN", "矿产"),
    ("Mogadishu Telecom Ltd", "SO-77041", "Somalia", "SDN", "通信"),
    ("Port Sudan Clearing Co", "SD-92008", "Sudan", "SDN", "清算"),
    ("Juba Oil Services", "SS-41036", "South Sudan", "SDN", "石油服务"),
    ("Nicaragua Free Zone SA", "NI-31019", "Nicaragua", "SDN", "自贸区"),
    ("Yangon Gems Exchange", "MM-22061", "Myanmar", "SDN", "珠宝"),
    ("Vientiane Trans Group", "LA-33044", "Laos", "SDN", "跨境运输"),
    ("Phnom Penh Casinos Ltd", "KH-66017", "Cambodia", "SDN", "博彩"),
    ("Naypyidaw Timber Co", "MM-22088", "Myanmar", "SDN", "木材"),
    ("Aleppo Textile Mills", "SY-40155", "Syria", "SDN", "纺织"),
    ("Khartoum Livestock Ltd", "SD-92033", "Sudan", "SDN", "畜牧"),
    ("Asmara Mining Corp", "ER-55012", "Eritrea", "SDN", "采矿"),
    ("Kinshasa Cobalt Traders", "CD-14077", "DR Congo", "SDN", "钴矿"),
    ("Bujumbura Coffee Co", "BI-11091", "Burundi", "SDN", "咖啡"),
    ("Lome Free Port SA", "TG-66028", "Togo", "SDN", "港口"),
    ("Conakry Bauxite Ltd", "GN-77053", "Guinea", "SDN", "铝土矿"),
    ("Bamako Gold Export", "ML-88026", "Mali", "SDN", "黄金"),
    ("Niamey Uranium Co", "NE-92047", "Niger", "SDN", "铀矿"),
    ("N'Djamena Transit Ltd", "TD-41063", "Chad", "SDN", "转运"),
    ("Moscow Technology JSC", "RU-77244", "Russia", "SDN", "电子元件"),
    ("Sevastopol Shipyard", "RU-77289", "Russia", "SDN", "船舶修造"),
    ("Grozny Construction Co", "RU-77301", "Russia", "SDN", "建筑"),
]

UN_ENTITIES = [
    ("Korea Mining Development Corp", "KP-10088", "DPRK", "UNSC", "矿产开发"),
    ("Iran Electronics Industries", "IR-88344", "Iran", "UNSC", "电子工业"),
    ("Syrian Scientific Studies", "SY-40221", "Syria", "UNSC", "科研机构"),
    ("Libyan Investment Authority", "LY-88077", "Libya", "UNSC", "主权基金"),
    ("Somali Charcoal Exporters", "SO-77099", "Somalia", "UNSC", "木炭贸易"),
    ("Eritrean Mining National", "ER-55066", "Eritrea", "UNSC", "国家矿业"),
    ("DPRK Ocean Shipping", "KP-10133", "DPRK", "UNSC", "远洋运输"),
    ("Houthi Financial Network", "YE-66177", "Yemen", "UNSC", "金融网络"),
    ("Al-Shabaab Trading Wing", "SO-77122", "Somalia", "UNSC", "贸易"),
    ("Taliban Exchange Network", "AF-11188", "Afghanistan", "UNSC", "货币兑换"),
    ("ISIL Oil Smuggling Cell", "SY-40311", "Syria", "UNSC", "石油走私"),
    ("Central African Arms Dealer", "CF-14155", "Central African Republic", "UNSC", "军火"),
]

EU_ENTITIES = [
    ("Minsk Industrial Group", "BY-55122", "Belarus", "EU-Sanction", "工业集团"),
    ("Donbas Coal Holding", "UA-33099", "Ukraine", "EU-Sanction", "煤炭"),
    ("Tehran Aviation Parts", "IR-88466", "Iran", "EU-Sanction", "航空配件"),
    ("Myanmar Economic Holdings", "MM-22311", "Myanmar", "EU-Sanction", "控股公司"),
    ("Venezuela State Oil JV", "VE-21288", "Venezuela", "EU-Sanction", "石油合资"),
    ("Crimea Tourism Operator", "RU-77455", "Russia", "EU-Sanction", "旅游运营"),
]

# ---------------------------------------------------------------------------
# 节点与数据集
# ---------------------------------------------------------------------------

NODES = [
    ("EU-FRA", "欧盟法兰克福节点", "EU", "https://fra.fedshield.eu:8443", "online", 46, "aggregator"),
    ("CN-HGH", "中国杭州节点", "CN", "https://hgh.fedshield.cn:8443", "online", 12, "participant"),
    ("SG-SIN", "新加坡节点", "SEA", "https://sin.fedshield.sg:8443", "online", 68, "participant"),
    ("US-VA", "美国弗吉尼亚节点", "US", "https://iad.fedshield.us:8443", "online", 158, "participant"),
    ("AE-DXB", "阿联酋迪拜节点", "ME", "https://dxb.fedshield.ae:8443", "degraded", 210, "participant"),
    ("ZA-JNB", "南非约翰内斯堡节点", "AF", "https://jnb.fedshield.za:8443", "offline", 320, "participant"),
]

DATASETS = [
    ("DS-TX-CN", "中国区跨境交易明细", "P2", "PingPong 中国区", "CN", "交易数据", 1_280_000,
     ["交易金额", "交易笔数", "商品类别", "币种", "结算账号", "收款方名称"]),
    ("DS-TX-EU", "欧盟区跨境交易明细", "P2", "PingPong 欧盟区", "EU", "交易数据", 960_000,
     ["交易金额", "退款率", "拒付率", "结算账号", "收付款方信息"]),
    ("DS-MERCHANT", "商户主数据（含实名信息）", "P1", "PingPong 商户中心", "CN", "用户数据", 420_000,
     ["商户名称", "统一社会信用代码", "税号", "法人身份证号", "结算银行卡号", "经营地址"]),
    ("DS-KYC", "KYC 身份核验数据", "P1", "PingPong 风控部", "EU", "用户数据", 310_000,
     ["证件号码", "护照号", "人脸特征值", "手机号", "注册地址"]),
    ("DS-SANCTION", "监管制裁清单（OFAC/联合国/欧盟）", "P3", "合规数据集市", "GLOBAL", "清单数据", 12_800,
     ["实体名称", "别名", "税号", "国家", "制裁项目"]),
    ("DS-CATEGORY", "商品类别与地区编码", "P3", "PingPong 数据平台", "CN", "交易数据", 2_400_000,
     ["商品类别", "地区编码", "币种", "交易时间戳"]),
    ("DS-RISK", "风控特征与评分结果", "P2", "PingPong 风控部", "CN", "交易数据", 1_050_000,
     ["设备指纹异常分", "夜间交易占比", "目的地风险分", "历史争议笔数"]),
    ("DS-STAT", "全球交易统计汇总", "P2", "PingPong 财务部", "GLOBAL", "交易数据", 86_000,
     ["地区", "金额合计", "笔数", "商品类别占比"]),
]

PARTNERS = [
    ("PT-EU-BANK01", "欧洲某银行（法兰克福）", "EU", "银行", True, "EU-FRA"),
    ("PT-EU-PSP02", "欧盟持牌支付机构（阿姆斯特丹）", "EU", "支付机构", True, "EU-FRA"),
    ("PT-CN-BANK01", "中国某股份制银行（杭州）", "CN", "银行", True, "CN-HGH"),
    ("PT-SG-BANK01", "新加坡某数字银行", "SEA", "银行", True, "SG-SIN"),
    ("PT-US-PSP01", "美国收单机构（弗吉尼亚）", "US", "支付机构", True, "US-VA"),
    ("PT-ME-BANK01", "中东某伊斯兰银行（迪拜）", "ME", "银行", False, "AE-DXB"),
    ("PT-UN-LIST01", "联合国制裁清单服务方", "GLOBAL", "监管清单服务方", True, "SG-SIN"),
    ("PT-OFAC-LIST01", "美国 OFAC 清单服务方", "US", "监管清单服务方", True, "US-VA"),
]

USERS = [
    ("risk.officer", "陈风控", "pingpong", "PingPong 风控技术部", "CN", "13800000001", "risk.officer@pingpong.com"),
    ("compliance.lead", "李合规", "pingpong", "PingPong 全球合规部", "CN", "13800000002", "compliance@pingpong.com"),
    ("ops.manager", "王运营", "pingpong", "PingPong 全球运营中心", "SG", "13800000003", "ops@pingpong.com"),
    ("merchant.demo", "深圳跨境优选", "merchant", "深圳跨境优选电子商务有限公司", "CN", "13900000001", "fin@sz-crossborder.com"),
    ("merchant.eu", "ACME GmbH", "merchant", "ACME GmbH（德国）", "EU", "13900000002", "finance@acme-gmbh.de"),
    ("regulator.eu", "EDPB 监管员", "regulator", "欧盟数据保护委员会（EDPB）", "EU", "13700000001", "audit@edpb.europa.eu"),
    ("regulator.cn", "网信办监管员", "regulator", "国家互联网信息办公室", "CN", "13700000002", "audit@cac.gov.cn"),
    ("security.admin", "赵安全", "admin", "PingPong 数据安全部", "CN", "13600000001", "security@pingpong.com"),
]

CATEGORIES = ["电子产品", "服饰鞋帽", "家居用品", "机械配件", "美妆个护", "汽车配件", "户外运动", "母婴用品"]
REGION_WEIGHTS = {"CN": 0.34, "EU": 0.26, "US": 0.16, "SEA": 0.13, "ME": 0.07, "AF": 0.04}


def _cert_expire(offset_days: int) -> datetime:
    return now() + timedelta(days=offset_days)


def seed_all() -> dict:
    """写入全部演示数据；已存在数据时直接返回（幂等）。"""
    if User.query.count() > 0:
        return {"skipped": True, "reason": "数据已存在，跳过初始化"}

    password = "FedShield@2026"
    password_hash = hash_password(password)

    # ---------------- 用户 ----------------
    for index, (username, display, role, org, region, phone, email) in enumerate(USERS):
        db.session.add(
            User(
                username=username,
                passwordHash=password_hash,
                displayName=display,
                role=role,
                org=org,
                region=region,
                phone=phone,
                email=email,
                certNo=f"FS-CERT-{1000 + index}",
                certExpireAt=_cert_expire(365 - index * 12),
                mfaEnabled=True,
                status="active",
            )
        )

    # ---------------- 节点 ----------------
    for index, (code, name, region, endpoint, status, latency, role) in enumerate(NODES):
        db.session.add(
            CollaborationNode(
                code=code, name=name, region=region, endpoint=endpoint, status=status,
                latencyMs=latency, bandwidthMbps=10, role=role,
                certNo=f"FS-NODE-{2000 + index}", certExpireAt=_cert_expire(300 - index * 20),
                tlsVersion="TLSv1.3",
            )
        )

    # ---------------- 数据集 ----------------
    for code, name, level, owner, region, category, rows, fields in DATASETS:
        meta = policy.describe(level)
        db.session.add(
            Dataset(
                code=code, name=name, level=level, owner=owner, region=region, category=category,
                rows=rows, fields=fields, storage="HDFS",
                description=f"{meta['algorithm']}｜{meta['keyManagement']}",
            )
        )

    # ---------------- 合作方 ----------------
    for index, (code, name, region, org_type, verified, node_code) in enumerate(PARTNERS):
        db.session.add(
            Partner(
                code=code, name=name, region=region, orgType=org_type, verified=verified,
                certNo=f"FS-PT-{3000 + index}", certExpireAt=_cert_expire(200 - index * 25),
                nodeCode=node_code,
            )
        )

    # ---------------- 制裁清单 ----------------
    for list_name, entries in (("OFAC", OFAC_ENTITIES), ("UN", UN_ENTITIES), ("EU", EU_ENTITIES)):
        for offset, (name, tax_no, country, program, entity_type) in enumerate(entries):
            db.session.add(
                SanctionEntry(
                    listName=list_name, name=name, alias=[f"{name} Ltd", f"{name.split()[0]} Group"],
                    taxNo=tax_no, country=country, program=program, entityType=entity_type,
                    listedAt=date.today() - timedelta(days=400 + offset * 11),
                )
            )

    # ---------------- 商户与交易 ----------------
    merchants = []
    index = 0
    for region, weight in REGION_WEIGHTS.items():
        count = max(4, int(60 * weight))
        for _ in range(count):
            index += 1
            tier = RANDOM.choices(["小规模", "中规模", "大规模"], weights=[0.5, 0.35, 0.15])[0]
            amount = {
                "小规模": RANDOM.uniform(80, 900) * 1e4,
                "中规模": RANDOM.uniform(1000, 9000) * 1e4,
                "大规模": RANDOM.uniform(1.1, 6.5) * 1e8,
            }[tier]
            risk_score = round(min(0.99, RANDOM.betavariate(2, 8)), 4)
            risk_level = "high" if risk_score >= 0.7 else ("medium" if risk_score >= 0.4 else "low")
            merchant = Merchant(
                code=f"M{index:05d}",
                name=f"{region}-跨境商户{index:03d}",
                region=region,
                taxNo=f"{region}-{RANDOM.randint(100000, 999999)}",
                category=RANDOM.choice(CATEGORIES),
                riskScore=risk_score,
                riskLevel=risk_level,
                annualAmount=round(amount, 2),
                txCount=int(amount / RANDOM.uniform(800, 6000)),
                tier=tier,
            )
            db.session.add(merchant)
            merchants.append(merchant)

    db.session.flush()

    # 交易明细：近 90 天，按地区与类别分布
    tx_index = 0
    for day_offset in range(89, -1, -1):
        day = now() - timedelta(days=day_offset)
        daily = RANDOM.randint(18, 42)
        for _ in range(daily):
            tx_index += 1
            region = RANDOM.choices(list(REGION_WEIGHTS), weights=list(REGION_WEIGHTS.values()))[0]
            level = RANDOM.choices(["P1", "P2", "P3"], weights=[0.18, 0.52, 0.30])[0]
            risk_level = RANDOM.choices(["low", "medium", "high"], weights=[0.84, 0.12, 0.04])[0]
            db.session.add(
                Transaction(
                    code=f"TX{tx_index:07d}",
                    merchantCode=RANDOM.choice(merchants).code,
                    region=region,
                    destRegion=RANDOM.choice([item for item in REGION_WEIGHTS if item != region]),
                    amount=round(RANDOM.lognormvariate(9.1, 0.85), 2),
                    currency=RANDOM.choice(["CNY", "USD", "EUR", "SGD"]),
                    category=RANDOM.choice(CATEGORIES),
                    counterparties=RANDOM.randint(1, 6),
                    level=level,
                    riskLevel=risk_level,
                    occurredAt=day.replace(hour=RANDOM.randint(0, 23), minute=RANDOM.randint(0, 59)),
                )
            )

    # ---------------- 合规规则（文档中的 3 条默认规则） ----------------
    for item in rule_engine.default_rules():
        db.session.add(
            ComplianceRule(
                code=item["code"], name=item["name"], description=item["description"],
                scene=item["scene"], priority=item["priority"], enabled=item["enabled"],
                nodes=item["nodes"], edges=item["edges"], updatedBy="compliance.lead",
            )
        )

    # ---------------- 隐私预算 ----------------
    budget_projects = [
        ("反欺诈模型训练", "anti_fraud", 12.0, 9.4, "P1"),
        ("用户画像分析", "profile", 8.0, 2.1, "P2"),
        ("风控决策", "decision", 6.0, 5.3, "P2"),
        ("制裁清单筛查", "screening", 10.0, 3.6, "P1"),
        ("监管统计申报", "statistics", 6.0, 1.4, "P2"),
        ("联合信用评分", "credit", 4.0, 0.9, "P2"),
    ]
    for project, category, total, used, level in budget_projects:
        db.session.add(
            BudgetItem(project=project, category=category, total=total, used=used, level=level,
                       note="按场景配置初始预算额度")
        )

    today = date.today()
    for offset in range(5, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=offset * 30)).replace(day=1)
        progress = (6 - offset) / 6
        db.session.add(
            BudgetTrend(
                month=month_date.strftime("%Y-%m"),
                used=round(21.0 * progress, 4),
                remaining=round(46.0 - 21.0 * progress, 4),
                usedRatio=round(21.0 * progress / 46.0, 4),
                scene=RANDOM.choice(["跨境电商联合风控", "国际汇款", "制裁清单筛查"]),
            )
        )

    for offset in range(4):
        db.session.add(
            BudgetApplication(
                code=next_code("BAPP", offset + 1),
                project=RANDOM.choice([item[0] for item in budget_projects]),
                category=RANDOM.choice(["反欺诈模型训练", "风控决策", "监管统计申报"]),
                amount=round(RANDOM.uniform(1.0, 4.0), 2),
                reason="业务规模增长，模型迭代频次提升，申请追加隐私预算",
                status=RANDOM.choice(["pending", "approved", "rejected"]),
                applicant="risk.officer",
                approver="security.admin" if offset else "",
                expectedAt=today + timedelta(days=15 + offset * 5),
            )
        )

    # ---------------- 合规趋势 ----------------
    for offset in range(5, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=offset * 30)).replace(day=1)
        for region, base in (("EU", 0.955), ("US", 0.965), ("SEA", 0.932), ("CN", 0.978)):
            db.session.add(
                ComplianceTrendPoint(
                    month=month_date.strftime("%Y-%m"),
                    region=region,
                    complianceRate=round(min(0.999, base + (5 - offset) * 0.006 + RANDOM.uniform(-0.008, 0.008)), 4),
                    issues=RANDOM.randint(0, 4),
                    reports=RANDOM.randint(1, 4),
                )
            )

    # ---------------- 授权记录 ----------------
    grant_specs = [
        ("欧洲某银行（法兰克福）", "EU", ["user_base", "risk_feature"], "反欺诈模型训练", "mpc", 240, "active"),
        ("欧盟持牌支付机构（阿姆斯特丹）", "EU", ["transaction"], "联合风控验证", "query-limited", 120, "active"),
        ("中国某股份制银行（杭州）", "CN", ["user_base", "transaction"], "联合信用评分", "readonly", 60, "active"),
        ("新加坡某数字银行", "SEA", ["sanction_list", "risk_feature"], "黑名单核验", "mpc", 18, "active"),
        ("美国收单机构（弗吉尼亚）", "US", ["transaction", "category"], "监管申报统计", "query-limited", -15, "expired"),
        ("中东某伊斯兰银行（迪拜）", "ME", ["user_identity"], "反欺诈模型训练", "mpc", 365, "pending"),
    ]
    for index, (partner, region, scope, purpose, level, days, status) in enumerate(grant_specs):
        valid_from = now() - timedelta(days=30 if days > 0 else 200)
        db.session.add(
            DataGrant(
                code=next_code("GRANT", index + 1),
                partner=partner, partnerRegion=region, datasetScope=scope, purpose=purpose,
                level=level, permissions=["authz:mfa-required"] + (["authz:re-authorize"] if level == "mpc" else []),
                validFrom=valid_from, validTo=now() + timedelta(days=days),
                status="active" if status == "active" else status,
                applicant="compliance.lead", approver="security.admin" if status != "pending" else "",
                history=[
                    {"ts": valid_from.strftime("%Y-%m-%d %H:%M:%S"), "action": "create",
                     "operator": "compliance.lead", "detail": "创建授权申请"},
                ],
                certExpireAt=_cert_expire(days + 90),
            )
        )

    # ---------------- 血缘图谱 ----------------
    lineage_nodes = [
        ("LN-SRC-EU-TX", "欧盟区交易库", "source", "采集", "PingPong 欧盟区", "EU", "P2", "交易数据",
         ["符合GDPR跨境规范", "欧盟境内存储"]),
        ("LN-SRC-CN-TX", "中国区交易库", "source", "采集", "PingPong 中国区", "CN", "P2", "交易数据",
         ["符合PIPL要求", "境内存储"]),
        ("LN-SRC-MERCHANT", "商户主数据库", "source", "采集", "PingPong 商户中心", "CN", "P1", "用户数据",
         ["脱敏三级等保", "符合PIPL要求"]),
        ("LN-SRC-SANCTION", "监管制裁清单库", "source", "采集", "合规数据集市", "GLOBAL", "P3", "清单数据",
         ["公开数据源", "每日同步"]),
        ("LN-EXT-TX", "交易数据抽取", "extract", "抽取", "数据平台", "CN", "P2", "交易数据",
         ["最小必要原则", "字段级权限"]),
        ("LN-TRF-MASK", "数据清洗与脱敏", "transform", "转换", "数据安全部", "CN", "P1", "用户数据",
         ["动态脱敏", "脱敏三级等保"]),
        ("LN-TRF-CLASSIFY", "智能分级分类", "transform", "转换", "数据安全部", "CN", "P1", "用户数据",
         ["分级准确率≥95%", "P1/P2/P3 标记"]),
        ("LN-CMP-FL", "联邦学习联合建模", "compute", "计算", "风控技术部", "EU", "P1", "交易数据",
         ["原始数据不出域", "SM4+Paillier 双重加密", "差分隐私保护"]),
        ("LN-CMP-HE", "同态加密密文计算", "compute", "计算", "风控技术部", "SG", "P1", "交易数据",
         ["密文域运算", "密钥不出地区节点"]),
        ("LN-CMP-STAT", "全球交易联合统计", "compute", "计算", "财务部", "SG", "P2", "交易数据",
         ["同态求和", "误差率≤1%"]),
        ("LN-APP-SCORE", "风险评分模型", "application", "应用", "风控技术部", "CN", "P2", "交易数据",
         ["AUC≈0.89", "漏检率≤7%"]),
        ("LN-APP-REPORT", "合规报告与监管申报", "application", "应用", "全球合规部", "EU", "P2", "交易数据",
         ["符合GDPR跨境规范", "联盟链存证"]),
        ("LN-APP-SCREEN", "制裁清单筛查服务", "application", "应用", "合规数据集市", "US", "P3", "清单数据",
         ["查询响应≤300ms", "零明文暴露"]),
    ]
    for code, name, node_type, stage, owner, region, level, data_type, tags in lineage_nodes:
        db.session.add(
            LineageNode(
                code=code, name=name, type=node_type, stage=stage, owner=owner, region=region,
                level=level, dataType=data_type, tags=tags,
                meta={
                    "storage": "HDFS" if node_type == "source" else "中间库",
                    "rows": RANDOM.randint(50_000, 2_000_000),
                    "rules": ["按最小必要原则取数", "字段级访问控制", "操作留痕并上链存证"],
                },
                processedAt=now() - timedelta(hours=RANDOM.randint(1, 240)),
            )
        )

    lineage_links = [
        ("LN-SRC-EU-TX", "LN-EXT-TX", "跨地区安全传输（TLS1.3）"),
        ("LN-SRC-CN-TX", "LN-EXT-TX", "境内抽取"),
        ("LN-SRC-MERCHANT", "LN-TRF-MASK", "脱敏处理"),
        ("LN-EXT-TX", "LN-TRF-CLASSIFY", "分级标记"),
        ("LN-TRF-MASK", "LN-TRF-CLASSIFY", "分级标记"),
        ("LN-TRF-CLASSIFY", "LN-CMP-FL", "加密后参与联邦建模"),
        ("LN-TRF-CLASSIFY", "LN-CMP-HE", "同态加密"),
        ("LN-EXT-TX", "LN-CMP-STAT", "本地聚合后密文上传"),
        ("LN-SRC-SANCTION", "LN-APP-SCREEN", "清单密文化"),
        ("LN-CMP-FL", "LN-APP-SCORE", "输出全局模型"),
        ("LN-CMP-HE", "LN-APP-SCORE", "密文计算结果"),
        ("LN-CMP-STAT", "LN-APP-REPORT", "生成申报口径统计"),
        ("LN-APP-SCORE", "LN-APP-REPORT", "风险指标汇总"),
    ]
    for source, target, operation in lineage_links:
        db.session.add(
            LineageLink(source=source, target=target, operation=operation,
                        ts=now() - timedelta(hours=RANDOM.randint(1, 200)))
        )

    # ---------------- 合规预警 ----------------
    alert_specs = [
        ("high", "GDPR 不合规项：跨境传输缺少 DPIA",
         "检测到 2 笔自中国出境至欧盟的 P1 级数据传输未关联 DPIA 评估报告。",
         "依据 GDPR 第 35 条，须在传输前完成数据保护影响评估并留存记录", "规则引擎"),
        ("medium", "隐私预算超配额预警",
         "「反欺诈模型训练」项目隐私预算已消耗 78.3%，接近预警阈值。",
         "依据隐私预算动态管理策略，超 80% 需提前申请追加额度", "预算管理"),
        ("medium", "合规报告待审核",
         "《GDPR 合规评估报告》已生成但尚未提交监管机构归档。",
         "监管要求报告生成后 5 个工作日内完成提交并留存凭证", "报告管理"),
        ("low", "数据授权即将到期",
         "「新加坡某数字银行」的数据授权将在 18 天后到期。",
         "权限与任务周期绑定，到期将自动回收，请提前续期或确认任务下线", "权限管控"),
        ("high", "异常访问行为：10 分钟内高频访问 P1 级数据",
         "账号 risk.officer 在 10 分钟内访问 P1 级数据集 6 次且未发起建模任务。",
         "触发零信任熔断规则，需数据安全管理员核查后解除", "审计存证"),
    ]
    for index, (level, title, content, requirement, source) in enumerate(alert_specs):
        db.session.add(
            Alert(
                code=next_code("ALT", index + 1), level=level, title=title, content=content,
                requirement=requirement, source=source,
                status="open" if index < 4 else "handling",
            )
        )

    # ---------------- 合规报告（示例） ----------------
    from .compliance import report as report_module

    period_end = date.today()
    period_start = period_end - timedelta(days=30)
    stats = None  # 延迟到 flush 之后统计，保证数据可见
    db.session.flush()
    stats = report_module.collect_stats(period_start, period_end, ["EU", "CN", "SEA"])
    for index, report_type in enumerate(["GDPR", "PIPL", "FATF"]):
        meta = report_module.REPORT_TYPE_MAP[report_type]
        code = next_code("RPT", index + 1)
        content = report_module.build_report(
            report_type, period_start, period_end, ["EU", "CN", "SEA"], {}, stats, created_by="compliance.lead"
        )
        content["basicInfo"]["reportCode"] = code
        record = ComplianceReport(
            code=code, type=report_type, typeName=meta["name"], status="generated",
            periodStart=period_start, periodEnd=period_end, regions=["EU", "CN", "SEA"],
            advanced={}, content=content, createdBy="compliance.lead",
            createdAt=now() - timedelta(days=index * 6),
        )
        record.sizeKb = round(len(report_module.render_markdown(record).encode("utf-8")) / 1024, 2)
        db.session.add(record)

    db.session.commit()
    return {
        "skipped": False,
        "users": len(USERS),
        "nodes": len(NODES),
        "datasets": len(DATASETS),
        "partners": len(PARTNERS),
        "sanctions": len(OFAC_ENTITIES) + len(UN_ENTITIES) + len(EU_ENTITIES),
        "merchants": len(merchants),
        "transactions": tx_index,
        "rules": len(rule_engine.default_rules()),
        "password": password,
    }


def reset_all() -> None:
    """清空所有业务数据（谨慎使用，用于把演示环境恢复到初始状态）。

    注意删除顺序：先删依赖方（任务日志、审计日志），再删被依赖方（任务、用户），
    避免外键约束报错。审计与存证也会一并清空，保证「重置」后链从创世块重新开始。
    """
    from .models import (
        AuditLog,
        BudgetAdjustment,
        ChainBlock,
        CircuitBreakerEvent,
        ComputeTask,
        LineageRecord,
        LoginSession,
        TaskLog,
        TokenBlacklist,
    )

    for model in (
        TaskLog, ComputeTask, LineageRecord, BudgetAdjustment, CircuitBreakerEvent,
        AuditLog, ChainBlock, LoginSession, TokenBlacklist,
        Transaction, Merchant, SanctionEntry, LineageLink, LineageNode, Alert, ComplianceReport,
        ComplianceTrendPoint, DataGrant, BudgetTrend, BudgetApplication, BudgetItem, ComplianceRule,
        Partner, Dataset, CollaborationNode, User,
    ):
        model.query.delete()
    db.session.commit()


__all__ = ["seed_all", "reset_all"]
