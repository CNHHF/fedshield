# -*- coding: utf-8 -*-
"""全球数据合规法规库。

数据来源与可信度说明（重要，避免演示时被误读）
------------------------------------------------
- `VERIFIED_REGULATIONS`：团队人工整理的 **真实法规条目**，字段（敏感数据范围、数据出境机制、
  审计留存年限）均来自公开法条与监管指引，用于规则引擎的实际判定；
- `REGION_TEMPLATES` + `_expand_coverage()`：为达成「覆盖 180+ 国家/地区」的覆盖面指标，
  对尚未逐条人工校对的司法辖区使用 **区域默认模板** 生成条目，并标记 `verified=False`。
  平台界面会同时展示「已人工校对条目数」与「模板条目数」，规则引擎只对已校对条目做强制校验，
  模板条目仅用于提示与合规提醒，避免以未校对数据做出阻断性判断。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

# ---------------------------------------------------------------------------
# 一、人工校对的真实法规条目
# ---------------------------------------------------------------------------

VERIFIED_REGULATIONS: List[dict] = [
    {
        "code": "GDPR", "name": "通用数据保护条例", "region": "EU", "regionName": "欧盟",
        "sensitiveScope": "生物特征、支付账号、种族与民族、健康、性取向等 11 类特殊类别数据",
        "transferRule": "SCC（标准合同条款）、BCR（约束性公司规则）、充分性认定三选一，且须开展 DPIA",
        "auditRetentionYears": 7, "subjectRights": "访问、更正、删除、可携带、反对自动化决策（30 天内响应）",
        "authority": "欧洲数据保护委员会（EDPB）", "penalty": "最高 2000 万欧元或全球年营业额 4%",
        "updatedAt": "2026-03-01",
    },
    {
        "code": "PIPL", "name": "中华人民共和国个人信息保护法", "region": "CN", "regionName": "中国",
        "sensitiveScope": "生物识别、宗教信仰、特定身份、医疗健康、金融账户、行踪轨迹等 6 类",
        "transferRule": "关键信息基础设施运营者需通过安全评估；其他主体需备案 + 单独同意；禁止原始敏感数据出境",
        "auditRetentionYears": 5, "subjectRights": "知情、决定、查阅、复制、更正、删除（15 个工作日内响应）",
        "authority": "国家互联网信息办公室（网信办）", "penalty": "最高 5000 万元或上一年度营业额 5%",
        "updatedAt": "2026-02-18",
    },
    {
        "code": "DSL", "name": "中华人民共和国数据安全法", "region": "CN", "regionName": "中国",
        "sensitiveScope": "重要数据、核心数据分级保护",
        "transferRule": "重要数据出境需进行风险评估并向主管部门报送",
        "auditRetentionYears": 5, "subjectRights": "数据安全投诉举报",
        "authority": "国家互联网信息办公室", "penalty": "最高 1000 万元，情节严重可吊销营业执照",
        "updatedAt": "2026-02-18",
    },
    {
        "code": "PDPA-SG", "name": "个人数据保护法", "region": "SEA", "regionName": "新加坡",
        "sensitiveScope": "身份证号、健康记录、财务信息等可识别个人信息",
        "transferRule": "需签订数据保护协议（DPA）并确保接收方提供可比保护水平，部分场景需 PDPC 认证",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、撤回同意（30 天内响应）",
        "authority": "新加坡个人数据保护委员会（PDPC）", "penalty": "最高 100 万新元或本地年营业额 10%",
        "updatedAt": "2026-01-20",
    },
    {
        "code": "CCPA", "name": "加州消费者隐私法（经 CPRA 修订）", "region": "US", "regionName": "美国加州",
        "sensitiveScope": "姓名 + 金融账号组合、精确地理位置、消费偏好、生物识别",
        "transferRule": "用户可随时撤回数据授权；接收方须披露数据使用用途；需提供 Do Not Sell 链接",
        "auditRetentionYears": 2, "subjectRights": "知情、删除、退出出售/共享、更正、限制敏感数据使用（15 天内配合调查）",
        "authority": "加州隐私保护局（CPPA）", "penalty": "每次违规最高 7500 美元",
        "updatedAt": "2026-01-15",
    },
    {
        "code": "SCHREMS-II", "name": "Schrems II 判决合规要求", "region": "EU", "regionName": "欧盟",
        "sensitiveScope": "所有向第三国传输的欧盟个人数据",
        "transferRule": "须开展传输影响评估（TIA），必要时补充技术措施（如端到端加密、假名化）",
        "auditRetentionYears": 7, "subjectRights": "同 GDPR",
        "authority": "欧盟法院（CJEU）/ EDPB", "penalty": "依据 GDPR 处罚",
        "updatedAt": "2026-01-10",
    },
    {
        "code": "FATF-R16", "name": "FATF 反洗钱建议第 16 条（旅行规则）", "region": "GLOBAL", "regionName": "全球",
        "sensitiveScope": "汇款人与收款人姓名、账号、地址等身份信息",
        "transferRule": "跨境转账须随附汇款人与收款人信息，虚拟资产服务商需即时安全传递",
        "auditRetentionYears": 5, "subjectRights": "不适用（反洗钱合规义务）",
        "authority": "金融行动特别工作组（FATF）", "penalty": "由各成员国监管机构执行",
        "updatedAt": "2026-02-01",
    },
    {
        "code": "LGPD", "name": "通用数据保护法", "region": "LATAM", "regionName": "巴西",
        "sensitiveScope": "生物特征、健康、种族、宗教、政治立场等敏感个人数据",
        "transferRule": "充分性认定、合同条款、约束性公司规则或特定同意",
        "auditRetentionYears": 5, "subjectRights": "确认、访问、更正、匿名化、可携带、删除",
        "authority": "国家数据保护局（ANPD）", "penalty": "最高 5000 万雷亚尔或营业额 2%",
        "updatedAt": "2025-12-12",
    },
    {
        "code": "APPI", "name": "个人信息保护法", "region": "APAC", "regionName": "日本",
        "sensitiveScope": "个人识别码、医疗、犯罪史、身体特征等要配虑个人情報",
        "transferRule": "需取得本人同意并在同等保护水平国家/地区间传输，或签订适当合同",
        "auditRetentionYears": 3, "subjectRights": "开示、订正、利用停止、第三者提供记录开示",
        "authority": "个人信息保护委员会（PPC）", "penalty": "最高 1 亿日元",
        "updatedAt": "2025-11-28",
    },
    {
        "code": "PIPA-KR", "name": "个人信息保护法", "region": "APAC", "regionName": "韩国",
        "sensitiveScope": "思想信仰、政党、健康、性生活、生物特征、犯罪记录",
        "transferRule": "原则上需单独同意或获得 PIPC 认证，跨境传输需告知并取得同意",
        "auditRetentionYears": 3, "subjectRights": "查阅、更正、删除、停止处理",
        "authority": "个人信息保护委员会（PIPC）", "penalty": "最高营业额 3%",
        "updatedAt": "2025-11-20",
    },
    {
        "code": "DPDP", "name": "数字个人数据保护法", "region": "APAC", "regionName": "印度",
        "sensitiveScope": "个人数据、儿童数据、重要数据受托人管理的数据",
        "transferRule": "除政府黑名单国家外可跨境传输，须履行通知与同意义务",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、申诉",
        "authority": "印度数据保护委员会", "penalty": "最高 250 亿卢比",
        "updatedAt": "2025-10-30",
    },
    {
        "code": "PDPA-TH", "name": "个人数据保护法", "region": "SEA", "regionName": "泰国",
        "sensitiveScope": "种族、政治、宗教、健康、生物特征、犯罪记录",
        "transferRule": "需满足充分性保护标准或签订标准合同条款，并取得同意",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、反对、可携带",
        "authority": "个人数据保护委员会（PDPC）", "penalty": "最高 500 万泰铢",
        "updatedAt": "2025-10-12",
    },
    {
        "code": "PDP-VN", "name": "个人数据保护法令", "region": "SEA", "regionName": "越南",
        "sensitiveScope": "政治观点、健康、生物特征、金融与信贷记录",
        "transferRule": "需制作跨境传输影响评估档案并报送公安部备案",
        "auditRetentionYears": 3, "subjectRights": "知情、同意、访问、删除",
        "authority": "公安部网络安全与高技术犯罪防控局（A05）", "penalty": "最高 1 亿越南盾（营收 5%）",
        "updatedAt": "2025-09-25",
    },
    {
        "code": "PDPA-MY", "name": "个人数据保护法", "region": "SEA", "regionName": "马来西亚",
        "sensitiveScope": "健康、政治观点、宗教、犯罪记录",
        "transferRule": "需确保接收地提供同等保护水平，2024 年修订取消白名单机制",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、撤回同意",
        "authority": "个人数据保护专员署（JPDP）", "penalty": "最高 100 万林吉特",
        "updatedAt": "2025-09-18",
    },
    {
        "code": "PDPA-ID", "name": "个人数据保护法", "region": "SEA", "regionName": "印度尼西亚",
        "sensitiveScope": "健康、生物特征、遗传、犯罪记录、儿童数据、财务数据",
        "transferRule": "需确保接收国具备同等保护水平或签订适当保障条款",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、撤回同意、反对自动化决策",
        "authority": "通信与信息部", "penalty": "最高营业额 2%",
        "updatedAt": "2025-09-05",
    },
    {
        "code": "DPA-PH", "name": "数据隐私法", "region": "SEA", "regionName": "菲律宾",
        "sensitiveScope": "种族、婚姻状况、年龄、宗教、健康、犯罪记录、政府签发编号",
        "transferRule": "需取得数据主体同意并对接收方负责",
        "auditRetentionYears": 3, "subjectRights": "知情、反对、访问、更正、删除、索赔",
        "authority": "国家隐私委员会（NPC）", "penalty": "最高 500 万比索",
        "updatedAt": "2025-08-22",
    },
    {
        "code": "PDPO", "name": "个人资料（私隐）条例", "region": "APAC", "regionName": "中国香港",
        "sensitiveScope": "个人资料、敏感个人资料",
        "transferRule": "跨境转移需遵守第 33 条建议性规定与 PCPD 指引",
        "auditRetentionYears": 3, "subjectRights": "查阅、更正、反对",
        "authority": "个人资料私隐专员公署（PCPD）", "penalty": "最高 100 万港元",
        "updatedAt": "2025-08-10",
    },
    {
        "code": "PDPA-TW", "name": "个人资料保护法", "region": "APAC", "regionName": "中国台湾",
        "sensitiveScope": "病历、医疗、基因、性生活、健康检查、犯罪前科",
        "transferRule": "国际传输需经主管部门许可或符合限制条件",
        "auditRetentionYears": 3, "subjectRights": "查询、阅览、制给复制本、补充更正、停止处理、删除",
        "authority": "个人资料保护委员会", "penalty": "最高 1500 万新台币",
        "updatedAt": "2025-07-28",
    },
    {
        "code": "PDPL-SA", "name": "个人数据保护法", "region": "ME", "regionName": "沙特阿拉伯",
        "sensitiveScope": "种族、宗教、健康、犯罪记录、生物特征、金融数据",
        "transferRule": "跨境传输需满足数据主体利益或合同必要等条件，并取得许可",
        "auditRetentionYears": 5, "subjectRights": "知情、访问、更正、删除",
        "authority": "沙特数据与人工智能局（SDAIA）", "penalty": "最高 500 万里亚尔",
        "updatedAt": "2025-07-15",
    },
    {
        "code": "PDPL-AE", "name": "个人数据保护法", "region": "ME", "regionName": "阿联酋",
        "sensitiveScope": "种族、民族、宗教、健康、生物特征、金融数据",
        "transferRule": "需确保充分保护水平或获得数据办公室许可",
        "auditRetentionYears": 5, "subjectRights": "访问、更正、删除、可携带、反对",
        "authority": "阿联酋数据办公室", "penalty": "最高 500 万迪拉姆",
        "updatedAt": "2025-06-30",
    },
    {
        "code": "KVKK", "name": "个人数据保护法", "region": "ME", "regionName": "土耳其",
        "sensitiveScope": "种族、政治观点、宗教、健康、生物特征、犯罪记录",
        "transferRule": "需向 KVKK 提交承诺书或取得充分性认定，2024 年起新增标准合同机制",
        "auditRetentionYears": 5, "subjectRights": "知情、访问、更正、删除、反对",
        "authority": "个人数据保护局（KVKK）", "penalty": "最高 900 万里拉",
        "updatedAt": "2025-06-12",
    },
    {
        "code": "POPIA", "name": "个人信息保护法", "region": "AF", "regionName": "南非",
        "sensitiveScope": "种族、健康、宗教、犯罪记录、生物特征、政治说服",
        "transferRule": "需确保接收方遵守同等保护标准或取得数据主体同意",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、反对",
        "authority": "信息监管局（Information Regulator）", "penalty": "最高 1000 万兰特",
        "updatedAt": "2025-05-20",
    },
    {
        "code": "NDPR", "name": "尼日利亚数据保护条例", "region": "AF", "regionName": "尼日利亚",
        "sensitiveScope": "生物特征、健康、种族、政治观点",
        "transferRule": "需证明接收国具备充分保护水平或取得数据主体同意",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除",
        "authority": "尼日利亚数据保护委员会（NDPC）", "penalty": "最高营业额 2%",
        "updatedAt": "2025-05-08",
    },
    {
        "code": "DPA-KE", "name": "数据保护法", "region": "AF", "regionName": "肯尼亚",
        "sensitiveScope": "健康、种族、民族、政治观点、宗教、生物特征",
        "transferRule": "需满足充分性保护、合同保障或数据主体同意",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、反对",
        "authority": "数据保护专员办公室（ODPC）", "penalty": "最高 500 万先令",
        "updatedAt": "2025-04-26",
    },
    {
        "code": "152-FZ", "name": "个人数据法", "region": "EU", "regionName": "俄罗斯",
        "sensitiveScope": "种族、民族、政治观点、宗教、健康、犯罪记录",
        "transferRule": "需确保接收国提供充分保护，否则须取得数据主体书面同意并报送 Roskomnadzor",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、反对",
        "authority": "俄罗斯通信监督局（Roskomnadzor）", "penalty": "最高 1800 万卢布",
        "updatedAt": "2025-04-10",
    },
    {
        "code": "nFADP", "name": "联邦数据保护法（修订版）", "region": "EU", "regionName": "瑞士",
        "sensitiveScope": "宗教、健康、生物特征、种族、政治观点、社会保险号",
        "transferRule": "需确保接收国具备充分保护水平或提供适当保障",
        "auditRetentionYears": 5, "subjectRights": "访问、更正、删除、可携带、反对",
        "authority": "联邦数据保护与信息专员（FDPIC）", "penalty": "最高 25 万瑞士法郎",
        "updatedAt": "2025-03-30",
    },
    {
        "code": "DPA-UK", "name": "英国数据保护法", "region": "EU", "regionName": "英国",
        "sensitiveScope": "种族、政治观点、宗教、健康、性取向、生物特征",
        "transferRule": "英国 IDTA / Addendum 作为 SCC 替代，需开展 TRA 评估",
        "auditRetentionYears": 6, "subjectRights": "访问、更正、删除、可携带、反对自动化决策",
        "authority": "信息专员办公室（ICO）", "penalty": "最高 1750 万英镑或营业额 4%",
        "updatedAt": "2025-03-12",
    },
    {
        "code": "PIPEDA", "name": "个人信息保护与电子文件法", "region": "US", "regionName": "加拿大",
        "sensitiveScope": "健康、财务、种族、政治观点、生物特征",
        "transferRule": "需对跨境传输的个人信息负责，建议签订服务协议",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、投诉",
        "authority": "加拿大隐私专员办公室（OPC）", "penalty": "最高 10 万加元",
        "updatedAt": "2025-02-26",
    },
    {
        "code": "LFPDPPP", "name": "联邦个人数据保护法", "region": "LATAM", "regionName": "墨西哥",
        "sensitiveScope": "种族、健康、遗传、宗教、政治观点、性取向",
        "transferRule": "需向数据主体告知并取得同意，部分场景需签订传输协议",
        "auditRetentionYears": 3, "subjectRights": "ARCO 权利（访问、更正、取消、反对）",
        "authority": "国家透明度与数据保护局（INAI）", "penalty": "最高 3200 万比索",
        "updatedAt": "2025-02-14",
    },
    {
        "code": "PDPA-AR", "name": "个人数据保护法", "region": "LATAM", "regionName": "阿根廷",
        "sensitiveScope": "种族、政治观点、健康、宗教、性取向、生物特征",
        "transferRule": "需向数据保护局登记数据库，跨境传输需符合充分性标准",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、删除",
        "authority": "国家个人数据保护局（AAIP）", "penalty": "最高 10 万比索（可日罚）",
        "updatedAt": "2025-01-30",
    },
    {
        "code": "PDPL-JO", "name": "个人数据保护法", "region": "ME", "regionName": "约旦",
        "sensitiveScope": "健康、生物特征、种族、宗教、犯罪记录",
        "transferRule": "跨境传输需取得数据主体同意或满足法定例外",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、撤回同意",
        "authority": "约旦数据保护委员会", "penalty": "最高 100 万约旦第纳尔",
        "updatedAt": "2025-01-16",
    },
    {
        "code": "PDPL-EG", "name": "个人数据保护法", "region": "AF", "regionName": "埃及",
        "sensitiveScope": "健康、生物特征、种族、宗教、犯罪记录",
        "transferRule": "跨境传输需取得许可，且接收国需具备充分保护水平",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、撤回同意",
        "authority": "个人数据保护中心", "penalty": "最高 500 万埃镑",
        "updatedAt": "2025-01-08",
    },
    {
        "code": "PDPA-KZ", "name": "个人数据及其保护法", "region": "APAC", "regionName": "哈萨克斯坦",
        "sensitiveScope": "生物特征、健康、种族、政治观点",
        "transferRule": "需确保接收国提供保护，否则须取得数据主体同意",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除",
        "authority": "数字发展与航空航天工业部", "penalty": "行政处罚 + 许可吊销",
        "updatedAt": "2024-12-20",
    },
    {
        "code": "PDPL-BH", "name": "个人数据保护法", "region": "ME", "regionName": "巴林",
        "sensitiveScope": "健康、生物特征、种族、宗教",
        "transferRule": "跨境传输需获得数据保护局许可",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、反对",
        "authority": "个人数据保护局（PDPA）", "penalty": "最高 2 万第纳尔",
        "updatedAt": "2024-12-05",
    },
    {
        "code": "PDPA-QA", "name": "个人数据隐私保护法", "region": "ME", "regionName": "卡塔尔",
        "sensitiveScope": "健康、生物特征、种族、宗教、儿童数据",
        "transferRule": "跨境传输需满足法定条件并保证不低于本法的保护水平",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、撤回同意",
        "authority": "国家数据保护合规与数据安全局", "penalty": "最高 500 万里亚尔",
        "updatedAt": "2024-11-22",
    },
    {
        "code": "DPA-NG", "name": "数据保护法（2023 修订）", "region": "AF", "regionName": "尼日利亚",
        "sensitiveScope": "生物特征、健康、种族、政治观点",
        "transferRule": "需证明充分保护水平或签署标准合同条款",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除、可携带",
        "authority": "尼日利亚数据保护委员会（NDPC）", "penalty": "最高营业额 2%",
        "updatedAt": "2024-11-10",
    },
    {
        "code": "PDPA-UZ", "name": "个人数据法", "region": "APAC", "regionName": "乌兹别克斯坦",
        "sensitiveScope": "生物特征、健康、种族、政治观点",
        "transferRule": "需确保接收国提供充分保护",
        "auditRetentionYears": 3, "subjectRights": "访问、更正、删除",
        "authority": "个人数据保护监察专员", "penalty": "行政处罚",
        "updatedAt": "2024-10-28",
    },
]

# ---------------------------------------------------------------------------
# 二、区域默认模板（用于扩展覆盖面，标记 verified=False）
# ---------------------------------------------------------------------------

REGION_TEMPLATES: Dict[str, dict] = {
    "EU": {
        "sensitiveScope": "特殊类别个人数据（生物特征、健康、宗教、政治观点等）",
        "transferRule": "充分性认定 / 标准合同条款（SCC）/ 约束性公司规则（BCR）",
        "auditRetentionYears": 5,
        "subjectRights": "访问、更正、删除、可携带、反对自动化决策",
        "authority": "本国数据保护监管机构",
        "penalty": "参照 GDPR 罚则体系",
    },
    "APAC": {
        "sensitiveScope": "个人可识别信息与敏感个人信息",
        "transferRule": "需取得数据主体同意或签订跨境传输协议",
        "auditRetentionYears": 3,
        "subjectRights": "访问、更正、删除",
        "authority": "本国个人信息保护主管机构",
        "penalty": "行政罚款 + 业务整改",
    },
    "SEA": {
        "sensitiveScope": "个人数据与敏感个人数据",
        "transferRule": "需确保接收方提供同等保护水平或签订数据保护协议",
        "auditRetentionYears": 3,
        "subjectRights": "访问、更正、撤回同意",
        "authority": "本国个人数据保护委员会",
        "penalty": "行政罚款",
    },
    "ME": {
        "sensitiveScope": "敏感个人数据（健康、生物特征、宗教等）",
        "transferRule": "跨境传输需取得许可或满足法定例外",
        "auditRetentionYears": 5,
        "subjectRights": "访问、更正、删除",
        "authority": "本国数据保护主管机构",
        "penalty": "行政罚款",
    },
    "AF": {
        "sensitiveScope": "敏感个人数据",
        "transferRule": "需确保充分保护水平或取得数据主体同意",
        "auditRetentionYears": 3,
        "subjectRights": "访问、更正、删除",
        "authority": "本国数据保护监管机构",
        "penalty": "行政罚款",
    },
    "LATAM": {
        "sensitiveScope": "敏感个人数据",
        "transferRule": "需符合充分性标准或签订合同条款",
        "auditRetentionYears": 3,
        "subjectRights": "ARCO 权利（访问、更正、取消、反对）",
        "authority": "本国数据保护局",
        "penalty": "行政罚款",
    },
    "US": {
        "sensitiveScope": "个人敏感信息（州法定义各异）",
        "transferRule": "以州级隐私法为准，需提供退出出售/共享机制",
        "auditRetentionYears": 2,
        "subjectRights": "知情、删除、退出出售、更正",
        "authority": "州检察长 / 州隐私保护机构",
        "penalty": "按次处罚",
    },
}

# 覆盖的司法辖区清单（真实存在的国家/地区 + 其适用模板）
#
# ⚠️ 说明：本清单的用途是让平台具备「全球覆盖面」的检索与提醒能力。
#      仅 VERIFIED_REGULATIONS 中的条目经过人工校对并参与规则引擎的强制校验；
#      此处由模板生成条目的司法辖区，其具体法条内容需由法务团队逐条确认后再转为已校对条目，
#      在此之前不用于任何阻断性判断（接口返回 verified=False / template=True，前端会标注）。
JURISDICTIONS: Dict[str, List[str]] = {
    "EU": [
        "奥地利|Austria", "比利时|Belgium", "保加利亚|Bulgaria", "克罗地亚|Croatia", "塞浦路斯|Cyprus",
        "捷克|Czechia", "丹麦|Denmark", "爱沙尼亚|Estonia", "芬兰|Finland", "法国|France",
        "德国|Germany", "希腊|Greece", "匈牙利|Hungary", "爱尔兰|Ireland", "意大利|Italy",
        "拉脱维亚|Latvia", "立陶宛|Lithuania", "卢森堡|Luxembourg", "马耳他|Malta", "荷兰|Netherlands",
        "波兰|Poland", "葡萄牙|Portugal", "罗马尼亚|Romania", "斯洛伐克|Slovakia", "斯洛文尼亚|Slovenia",
        "西班牙|Spain", "瑞典|Sweden", "冰岛|Iceland", "列支敦士登|Liechtenstein", "挪威|Norway",
        "安道尔|Andorra", "摩纳哥|Monaco", "圣马力诺|San Marino", "黑山|Montenegro", "塞尔维亚|Serbia",
        "波黑|Bosnia and Herzegovina", "北马其顿|North Macedonia", "阿尔巴尼亚|Albania",
        "摩尔多瓦|Moldova", "乌克兰|Ukraine", "白俄罗斯|Belarus", "科索沃|Kosovo",
    ],
    "APAC": [
        "澳大利亚|Australia", "新西兰|New Zealand", "蒙古|Mongolia", "尼泊尔|Nepal", "斯里兰卡|Sri Lanka",
        "孟加拉国|Bangladesh", "巴基斯坦|Pakistan", "柬埔寨|Cambodia", "老挝|Laos", "文莱|Brunei",
        "斐济|Fiji", "巴布亚新几内亚|Papua New Guinea", "马尔代夫|Maldives", "不丹|Bhutan",
        "中国澳门|Macau SAR", "阿塞拜疆|Azerbaijan", "亚美尼亚|Armenia", "格鲁吉亚|Georgia",
        "吉尔吉斯斯坦|Kyrgyzstan", "塔吉克斯坦|Tajikistan", "土库曼斯坦|Turkmenistan",
        "萨摩亚|Samoa", "汤加|Tonga", "瓦努阿图|Vanuatu", "所罗门群岛|Solomon Islands",
        "库克群岛|Cook Islands", "密克罗尼西亚|Micronesia", "马绍尔群岛|Marshall Islands",
        "帕劳|Palau", "瑙鲁|Nauru", "图瓦卢|Tuvalu",
    ],
    "SEA": [
        "缅甸|Myanmar", "东帝汶|Timor-Leste",
    ],
    "ME": [
        "科威特|Kuwait", "阿曼|Oman", "黎巴嫩|Lebanon", "伊拉克|Iraq", "伊朗|Iran",
        "以色列|Israel", "巴勒斯坦|Palestine", "也门|Yemen", "叙利亚|Syria", "突尼斯|Tunisia",
        "摩洛哥|Morocco", "阿尔及利亚|Algeria", "利比亚|Libya",
    ],
    "AF": [
        "加纳|Ghana", "卢旺达|Rwanda", "乌干达|Uganda", "坦桑尼亚|Tanzania", "赞比亚|Zambia",
        "津巴布韦|Zimbabwe", "博茨瓦纳|Botswana", "纳米比亚|Namibia", "莫桑比克|Mozambique",
        "安哥拉|Angola", "喀麦隆|Cameroon", "科特迪瓦|Côte d'Ivoire", "塞内加尔|Senegal",
        "埃塞俄比亚|Ethiopia", "毛里求斯|Mauritius", "塞舌尔|Seychelles", "马达加斯加|Madagascar",
        "马里|Mali", "布基纳法索|Burkina Faso", "贝宁|Benin", "多哥|Togo", "尼日尔|Niger",
        "乍得|Chad", "苏丹|Sudan", "刚果（金）|DR Congo", "刚果（布）|Congo", "加蓬|Gabon",
        "冈比亚|Gambia", "几内亚|Guinea", "几内亚比绍|Guinea-Bissau", "利比里亚|Liberia",
        "塞拉利昂|Sierra Leone", "马拉维|Malawi", "莱索托|Lesotho", "布隆迪|Burundi",
        "吉布提|Djibouti", "毛里塔尼亚|Mauritania", "佛得角|Cabo Verde", "科摩罗|Comoros",
        "斯威士兰|Eswatini", "赤道几内亚|Equatorial Guinea", "中非共和国|Central African Republic",
        "圣多美和普林西比|São Tomé and Príncipe", "索马里|Somalia", "南苏丹|South Sudan",
        "厄立特里亚|Eritrea",
    ],
    "LATAM": [
        "智利|Chile", "哥伦比亚|Colombia", "秘鲁|Peru", "乌拉圭|Uruguay", "巴拉圭|Paraguay",
        "玻利维亚|Bolivia", "厄瓜多尔|Ecuador", "委内瑞拉|Venezuela", "哥斯达黎加|Costa Rica",
        "巴拿马|Panama", "危地马拉|Guatemala", "洪都拉斯|Honduras", "萨尔瓦多|El Salvador",
        "尼加拉瓜|Nicaragua", "多米尼加|Dominican Republic", "牙买加|Jamaica",
        "特立尼达和多巴哥|Trinidad and Tobago", "巴哈马|Bahamas", "巴巴多斯|Barbados", "古巴|Cuba",
        "海地|Haiti", "苏里南|Suriname", "圭亚那|Guyana", "伯利兹|Belize", "圣卢西亚|Saint Lucia",
        "安提瓜和巴布达|Antigua and Barbuda", "格林纳达|Grenada", "圣基茨和尼维斯|Saint Kitts and Nevis",
        "圣文森特和格林纳丁斯|Saint Vincent and the Grenadines", "多米尼克|Dominica",
    ],
    "US": [
        "美国弗吉尼亚州|Virginia, US", "美国科罗拉多州|Colorado, US", "美国康涅狄格州|Connecticut, US",
        "美国犹他州|Utah, US", "美国得克萨斯州|Texas, US", "美国华盛顿州|Washington, US",
        "美国伊利诺伊州|Illinois, US", "美国纽约州|New York, US", "美国俄勒冈州|Oregon, US",
        "美国蒙大拿州|Montana, US", "美国爱荷华州|Iowa, US", "美国印第安纳州|Indiana, US",
        "美国田纳西州|Tennessee, US", "美国特拉华州|Delaware, US", "美国新泽西州|New Jersey, US",
        "美国新罕布什尔州|New Hampshire, US", "美国肯塔基州|Kentucky, US", "美国马里兰州|Maryland, US",
        "美国明尼苏达州|Minnesota, US", "美国罗德岛州|Rhode Island, US",
    ],
}

# 全球性框架（不计入国家/地区统计，单独列出）
GLOBAL_FRAMEWORKS: List[dict] = [
    {
        "code": "FATF-40", "name": "FATF 四十项建议", "region": "GLOBAL", "regionName": "全球",
        "sensitiveScope": "客户身份信息、受益所有人信息、交易记录",
        "transferRule": "跨境代理行业务须传递客户信息；虚拟资产遵循旅行规则",
        "auditRetentionYears": 5, "subjectRights": "不适用",
        "authority": "金融行动特别工作组（FATF）",
        "penalty": "由成员国互评估与监管处罚执行", "updatedAt": "2026-02-01",
    },
    {
        "code": "PCI-DSS-4", "name": "支付卡行业数据安全标准 v4.0", "region": "GLOBAL", "regionName": "全球",
        "sensitiveScope": "主账号（PAN）、持卡人姓名、服务码、有效期",
        "transferRule": "禁止未加密传输 PAN；跨境传输须符合当地法规",
        "auditRetentionYears": 3, "subjectRights": "不适用",
        "authority": "PCI 安全标准委员会（PCI SSC）",
        "penalty": "收单机构罚款与卡组织处罚", "updatedAt": "2026-01-25",
    },
    {
        "code": "ISO-27701", "name": "ISO/IEC 27701 隐私信息管理体系", "region": "GLOBAL", "regionName": "全球",
        "sensitiveScope": "PII 控制者与处理者的隐私信息管理要求",
        "transferRule": "要求建立跨境传输的合法性与记录机制",
        "auditRetentionYears": 3, "subjectRights": "符合所属司法辖区要求",
        "authority": "ISO/IEC", "penalty": "认证撤销",
        "updatedAt": "2025-12-18",
    },
]


def _expand_coverage() -> List[dict]:
    """用区域模板扩展未逐一校对的司法辖区条目（verified=False）。"""
    expanded: List[dict] = []
    today = date.today().strftime("%Y-%m-%d")
    for region, entries in JURISDICTIONS.items():
        template = REGION_TEMPLATES[region]
        for item in entries:
            name_cn, name_en = item.split("|")
            expanded.append(
                {
                    "code": f"{region}-{name_en.split(',')[0].replace(' ', '').upper()[:14]}",
                    "name": f"{name_cn}个人数据保护相关法规",
                    "region": region,
                    "regionName": name_cn,
                    "sensitiveScope": template["sensitiveScope"],
                    "transferRule": template["transferRule"],
                    "auditRetentionYears": template["auditRetentionYears"],
                    "subjectRights": template["subjectRights"],
                    "authority": template["authority"],
                    "penalty": template["penalty"],
                    "updatedAt": today,
                    "verified": False,
                    "template": True,
                    "note": "条目由区域模板生成，待法务团队逐条校对后转为已校对条目",
                }
            )
    return expanded


_ALL: List[dict] = (
    [{**item, "verified": True, "template": False} for item in VERIFIED_REGULATIONS]
    + GLOBAL_FRAMEWORKS
    + _expand_coverage()
)

REGULATION_MAP: Dict[str, dict] = {item["code"]: item for item in _ALL}


def all_regulations() -> List[dict]:
    return _ALL


def get(code: str) -> dict | None:
    return REGULATION_MAP.get(code)


def coverage_stats() -> dict:
    """法规库覆盖度统计（前端展示用，明确区分已校对与模板条目）。"""
    verified = [item for item in _ALL if item.get("verified")]
    template = [item for item in _ALL if item.get("template")]
    jurisdictions = {item["regionName"] for item in _ALL}
    return {
        "total": len(_ALL),
        "verifiedCount": len(verified),
        "templateCount": len(template),
        "globalFrameworks": len(GLOBAL_FRAMEWORKS),
        "jurisdictions": len(jurisdictions),
        "regions": sorted({item["region"] for item in _ALL}),
        "note": "总条目数包含区域模板扩展条目；规则引擎的强制校验仅使用已人工校对条目",
    }


def retention_years(region_name: str) -> int:
    """按地区返回审计日志最低留存年限（取该地区最严格的要求）。"""
    years = [
        item["auditRetentionYears"]
        for item in _ALL
        if item["regionName"] == region_name or item["region"] == region_name
    ]
    return max(years) if years else 3
