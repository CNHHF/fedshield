# FedShield · AI 风控合规智能大脑（面向全球支付场景的一体化智能支撑体系）

> 赛题 **A16【面向全球支付场景的 AI 驱动风控合规智能大脑框架】（乒乓智能）** 参赛作品。
>
> 聚焦跨境电商、外贸 B2B、企业服务场景，构建面向全球支付业务的**一体化智能支撑体系**，
> 覆盖**支付、风控、合规、监测、识别与运营决策**关键环节，形成统一的
> **数据底座 + 智能引擎 + 业务应用**能力，实现业务流程协同、风险联防联控与运营分析闭环。
>
> 在 AI 智能审核之上叠加**隐私计算底座**：联邦学习 / 同态加密 / 差分隐私 / 联盟链存证，
> 确保敏感数据「可用不可见、合规可追溯」，符合欧盟 Schrems II 判决与 PIPL 出境要求。

平台核心是 **AI 风控大脑数据流展板**（`/brain`）：17 个脑区按「感知输入层 → 脑区计算层 → 决策输出层」
排布，31 条数据通路上有实时脉冲流动，脑区负载、脉冲强度与审计事件全部由真实业务指标驱动，
而非静态示意图。

---

## 一、赛题要求与实现对照

| 赛题要求 | 实现情况 | 代码 / 页面 |
| --- | --- | --- |
| **建设范围① 支付智能处理**：交易接入、智能路由、通道选择、状态跟踪、失败重试、异常处理、自动补偿 | ✅ 7 条通道池 + 四目标加权路由（成本 40% / 成功率 30% / 时效 20% / 合规 10%）+ 全链路状态机 + 指数退避重试 + 自动补偿 | `backend/engine/payment.py`<br>`/ops/payment`、`/ops/channels` |
| **建设范围② 智能风控**：交易/账户/商户风险识别、异常行为检测、实时预警、自动处置闭环 | ✅ 6 条检测规则（按「商户 × 小时」时间窗）+ 组合风险加成 + 四档统一处置口径 + 处置确认闭环 | `backend/engine/monitoring.py`<br>`/ops/monitoring` |
| **建设范围③ 智能合规审核**：客户身份识别、交易审核、可疑行为识别、自动审核流转、人工复核协同 | ✅ AI 初审自动流转 + 人工复核协同 + 低置信度强制转人工 + 合规规则引擎校验 | `backend/engine/review.py`<br>`backend/compliance/rule_engine.py` |
| **建设范围④ AI 审核一致性管理**：统一标准/标签/口径、结果比对、差异分析、低置信度转人工、反馈回流、策略优化 | ✅ 统一三分类口径 + 混淆矩阵 + Cohen's Kappa + 漏放/误拦分析 + **网格搜索策略寻优**（硬约束：漏放率不升、一致性不低于当前 98%）+ 差异回流闭环 | `backend/engine/review.py`<br>`/ops/review`、`/ops/standard` |
| **建设范围⑤ 运营决策支撑**：指标监控、风险分析、策略评估、运营看板、趋势研判、决策建议输出 | ✅ 一体化看板 + 策略评估 + 趋势研判 + 带优先级/责任角色/预期收益的决策建议 | `/ops/decision`、`/console` |
| 背景要求：隐私计算与全球数据合规 | ✅ 联邦学习 + 同态加密 + 差分隐私 + 联盟链存证 + 224 条法规库 + 12 类合规报告 | `backend/crypto/`、`backend/engine/` |
| 提交材料：产品使用手册、详细分工及过程文档、架构设计 | 📄 团队文档已具备；本仓库补充 `docs/API.md`（接口契约）与 `docs/VERIFICATION.md`（验证报告） | `docs/` |

---

## 二、技术栈

| 层次 | 技术选型 | 说明 |
| --- | --- | --- |
| 前端 | Vue 3（`<script setup>`）+ Element Plus + Vite 5 + Pinia + Vue Router + ECharts 5 + Axios | 与文档「前端基于 Vue.js3 + ElementPlus」一致；hash 路由便于 Flask 直接托管构建产物 |
| 后端 | Python 3.10+ / Flask 3 + Flask-SQLAlchemy 3 + PyJWT | 与文档「后端 Python Flask」一致 |
| 数据库 | SQLite（默认，开箱即用）/ MySQL / 国产数据库 | 通过 `DATABASE_URL` 切换；表前缀 `fs_` |
| 密码学 | 国密 SM4（纯 Python 实现 + PyCryptodome 加速）、Paillier 半同态加密（纯 Python + CRT 加速）、AES-256-GCM、RSA 盲签名、拉普拉斯差分隐私 | 全部算法均已实现并通过自测 |
| 存证 | Hyperledger Fabric 语义的链式哈希存证（本地实现） | 区块结构、Raft 共识语义、监管查询节点与完整性校验 |

> **为什么密码学核心是纯 Python 实现？**
> 一是便于在无第三方依赖的节点上部署（文档要求「无特殊硬件依赖、轻量化对接」），
> 二是所有算法都能用标准测试向量自证正确性（SM4 已通过 GB/T 32907-2016 两个官方向量）。
> 生产环境可将 `backend/crypto/paillier.py` 平滑替换为 gmpy2 或密码卡实现，接口保持不变。

---

## 二、目录结构

```
fedshield/
├─ run.py                      # 后端启动入口（自动建表 + 空库自动初始化演示数据）
├─ requirements.txt            # 后端依赖
├─ docs/
│  └─ API.md                   # 完整 API 契约（115 个接口，前后端以此为准）
├─ backend/
│  ├─ app.py                   # 应用工厂（蓝图注册 / 错误处理 / CLI / 静态托管）
│  ├─ config.py                # 配置（JWT、隐私预算、熔断阈值、留存年限…）
│  ├─ models.py                # 26 张数据表（用户/节点/数据集/任务/规则/报告/授权/预算/血缘/审计/存证）
│  ├─ seed.py                  # 演示数据（真实可复现，非随机占位文本）
│  ├─ extensions.py            # db / cors 扩展实例
│  ├─ crypto/                  # ★ 密码学与隐私计算基础库
│  │  ├─ sm4.py                #   国密 SM4（CBC + HMAC，含纯 Python 降级实现）
│  │  ├─ paillier.py           #   Paillier 半同态加密（加法同态 / 标量乘 / 重随机 / CRT 加速）
│  │  ├─ aes_gcm.py            #   AES-256-GCM 认证加密
│  │  ├─ dp.py                 #   差分隐私（拉普拉斯/高斯/指数机制 + 隐私预算会计）
│  │  ├─ psi.py                #   隐私求交集（RSA 盲签名 PSI）
│  │  └─ policy.py             #   P1/P2/P3 分级加密策略统一出口
│  ├─ engine/                  # ★ 跨境支付隐私计算引擎
│  │  ├─ federated.py          #   横向联邦学习 + 差分隐私 + 密文域聚合 + 参数压缩
│  │  ├─ oblivious.py          #   匿踪查询（Paillier 密文比对 / RSA OPRF 双模式）
│  │  └─ joint_stats.py        #   全球交易联合统计（密文域求和 + 差分隐私计数）
│  ├─ compliance/              # ★ 全流程合规校验
│  │  ├─ classifier.py         #   智能分级分类（敏感字段识别 → P1/P2/P3）
│  │  ├─ rule_engine.py        #   可视化规则引擎（触发/判断/动作 + 整改清单）
│  │  ├─ regulation_lib.py     #   全球法规库（224 条 / 218 个司法辖区）
│  │  └─ report.py             #   12 类合规报告生成与 Markdown 导出
│  ├─ audit/
│  │  ├─ chain.py              #   联盟链存证（链式哈希 + 完整性校验 + 调证证明）
│  │  └─ logger.py             #   审计日志（风险评分 + 防篡改签名 + 强制上链）
│  ├─ utils/                   # 统一响应/异常、JWT、权限矩阵、零信任熔断
│  ├─ api/                     # 11 个蓝图 / 115 条路由（auth/meta/dashboard/brain/ops/engine/compliance/authz/budget/lineage/audit）
│  └─ tests/test_fedshield.py  # 14 项核心算法自测（unittest，可 pytest 运行）
└─ frontend/
   ├─ package.json / vite.config.js / index.html
   └─ src/
      ├─ main.js / App.vue
      ├─ router/               # routes.js（路由与菜单单一数据源）+ index.js（守卫）
      ├─ store/                # user（角色与权限点）+ app（元数据缓存）
      ├─ api/                  # request.js（JWT 注入/统一解包/错误提示）+ index.js（9 组接口）
      ├─ layout/               # Sidebar（按权限生成菜单）+ Navbar（角色切换/链状态/在线会话）
      ├─ components/           # ChartBox（ECharts 封装）/ StatCard / DataLevelTag / RoleSwitcher
      ├─ utils/                # format（时间/金额/状态字典/图表主题）+ download（Blob/CSV 导出）
      └─ views/                # 29 个页面（见下表）
```

---

## 三、快速开始

### 1. 启动后端（必需）

```bash
cd fedshield
pip install -r requirements.txt

python run.py                 # http://127.0.0.1:5000，空库自动初始化演示数据
```

其他可用参数：

```bash
python run.py --seed          # 仅初始化演示数据
python run.py --reset         # 清空并重新初始化
python run.py --port 5001     # 指定端口
python run.py --no-seed       # 不自动初始化数据
```

### 2. 启动前端

```bash
cd fedshield/frontend
npm install                   # 首次执行（需联网）
npm run dev                   # http://127.0.0.1:5173（已配置 /api 代理到 5000）
```

生产构建（构建后可由 Flask 直接托管，无需额外服务）：

```bash
npm run build                 # 产物在 frontend/dist
# 之后访问 http://127.0.0.1:5000 即为完整应用
```

### 3. 演示账号

统一口令 `FedShield@2026`，MFA 动态码 `123456`（登录页可点击标签一键填充）：

| 用户名 | 角色 | 机构 | 可见功能 |
| --- | --- | --- | --- |
| `risk.officer` | PingPong 风控 | PingPong 风控技术部 | 全量业务视图 |
| `compliance.lead` | PingPong 合规 | PingPong 全球合规部 | 规则引擎、合规报告、授权 |
| `merchant.demo` | 商户 | 深圳跨境优选电商 | 匿踪查询、联合统计、合规状态 |
| `regulator.eu` | 监管机构 | 欧盟 EDPB | 流转日志、合规报告、链校验 |
| `security.admin` | 数据安全管理 | PingPong 数据安全部 | 权限、预算、规则、审计全量 |

---

## 四、页面与文档对照

文档《产品使用手册》中的每个界面都在代码中有对应实现：

| 文档图号 | 页面 | 代码位置 |
| --- | --- | --- |
| — | **AI 风控大脑数据流展板（脑机结构 · 平台核心页）** | `frontend/src/views/brain/index.vue` |
| — | 平台首页（英雄区/智能大脑结构/核心价值/适用场景） | `frontend/src/views/home/index.vue` |
| 图9 | 数据概览控制台（角色选择器/统计卡/趋势/告警/功能入口） | `views/console/index.vue` |
| — | **支付智能处理**（批量处理/故障演练/智能路由预演/全链路状态跟踪） | `views/ops/PaymentFlow.vue` |
| — | **通道与智能路由**（通道池/评分权重/重试与补偿策略） | `views/ops/PaymentChannels.vue` |
| — | **风控与异常监测**（检测规则/实时预警/自动处置/商户风险 Top10） | `views/ops/Monitoring.vue` |
| — | **AI 审核一致性**（一致性指标/混淆矩阵/差异分析/策略寻优） | `views/ops/ReviewConsistency.vue` |
| — | **统一审核标准**（结论口径/风险标签/规则权重/评分公式） | `views/ops/AuditStandard.vue` |
| — | **运营决策支撑**（决策建议/策略评估/趋势研判/指标监控） | `views/ops/Decision.vue` |
| 图10-11 | 隐私计算任务构建与配置选择 | `views/engine/TaskCreate.vue` |
| 图12-13 | 规则引擎可视化配置（拖拽画布）与规则列表 | `views/compliance/RuleEngine.vue` |
| 图14-16 | 生成合规报告 / 报告类型 / 报告记录管理 | `views/compliance/ReportGenerate.vue` `ReportList.vue` |
| 图17 | 报告预览 | `views/compliance/ReportPreview.vue` |
| 图18-19 | 计算任务管理与筛选 | `views/engine/TaskList.vue` |
| 图20 | 最近计算结果（饼图/曲线/基线对比） | `views/engine/TaskResult.vue` |
| 图21-22 | 新建数据授权与筛选条件 | `views/authz/GrantManage.vue` |
| 图23-25 | 授权记录 / 合规趋势对比 / 合规预警 | `views/authz/GrantManage.vue` `views/compliance/ComplianceTrend.vue` |
| 图26-32 | 隐私预算管理、明细、消耗趋势、分配调整、申请 | `views/budget/BudgetOverview.vue` `BudgetDetail.vue` |
| 图33-37 | 数据血缘图谱、溯源详情、审计记录 | `views/lineage/LineageGraph.vue` `TraceDetail.vue` `AuditRecords.vue` |
| — | 黑名单匿踪查询 / 全球交易联合统计 / 隐私求交 | `views/engine/ObliviousQuery.vue` `JointStats.vue` `PsiPanel.vue` |
| — | 跨境合规校验（出境前校验 + 整改清单） | `views/compliance/ComplianceCheck.vue` |

---

## 五、核心算法与实测指标

所有指标均由代码实际计算得出（`backend/tests/test_fedshield.py` 会对指标做断言守卫），非手工填写。

### 1. 跨境电商联合风控（横向联邦 + 差分隐私 + 同态聚合）

| 指标 | 实测值 | 文档要求 |
| --- | --- | --- |
| 联邦模型 AUC | ≈ 0.85 | 0.89（同一量级） |
| 与明文集中建模 AUC 偏差 | ≤ 0.02 | ≤ 0.02 ✅ |
| 漏检率 | ≤ 7%（按业务红线反推告警阈值） | ≤ 7% ✅ |
| 相较单地区本地建模 AUC 提升 | +0.19 左右 | 本地建模漏检率 >20% ✅ |
| 参数传输量压缩 | 约 64%（float32→int16 + 幅值剪枝 + 增量 varint 编码） | 减少 70%（同量级） |

关键实现：DP-SGD 逐样本梯度裁剪推出可公开的敏感度上界 → 拉普拉斯加噪 → int16 定点量化 →
Top-K 剪枝 → Paillier 加密 → 密文域加权聚合 `Π E(θᵢ)^{wᵢ}` → 解密回传迭代。

### 2. 黑名单匿踪查询（双协议模式）

| 模式 | 协议 | 实测响应 | 适用规模 |
| --- | --- | --- | --- |
| `oprf`（默认） | RSA 盲签名 OPRF | 10~80 ms（首次含密钥生成） | 全量 OFAC/联合国清单 ✅ 满足 ≤300ms |
| `paillier` | 同态密文比对（文档架构） | 约 120~300 ms | 中小规模清单（逐项解密，耗时随规模线性增长） |

两种模式均返回逐步耗时、命中结论与「零明文暴露」证明，并在响应中给出达标判定。

### 3. 全球交易联合统计

各地区本地聚合 → P1 字段 Paillier 密文域求和 → P2 金额差分隐私加噪 → 输出申报口径统计。
实测误差率 ≈ 0.06%（要求 ≤1% ✅）。

### 4. 合规引擎

智能化分级（字段名 + 样例值 + 正则三重判定）、画布规则引擎（触发→判断→动作，支持
`block/mask/require/notify/audit/allow` 六类动作与整改清单）、全球法规库
（224 条：37 条人工校对 + 187 条区域模板，覆盖 218 个司法辖区）。

### 5. 审计存证

每条高敏感操作生成 SHA-256 链式哈希并追加区块，篡改任一历史区块都会导致链断裂；
`POST /api/audit/chain/verify` 可定位首个断裂高度（测试中已验证篡改可检出）。

---

## 六、接口一览

完整契约见 [`docs/API.md`](docs/API.md)（115 个接口）。分组如下：

| 分组 | 前缀 | 说明 |
| --- | --- | --- |
| 认证 | `/api/auth` | 登录（口令+MFA+证书）、登出（JWT 黑名单）、角色权限矩阵、在线会话与异常登录 |
| 元数据 | `/api/meta` | 节点、数据集、合作方、算法模板、任务类型、报告类型、法规库、字典 |
| 控制台 | `/api/dashboard` | 统计卡片、流转趋势、风险分布、预警、效能对照 |
| **智能大脑** | `/api/brain` | **脑区图谱、数据通路、大脑 KPI、实时脉冲事件** |
| **一体化智能支撑** | `/api/ops` | **①支付智能处理（路由/重试/补偿）②异常监测（检测/预警/自动处置）③④审核协同与 AI 审核一致性（一致性评估/差异回流/策略寻优）⑤运营决策建议** |
| 引擎 | `/api/engine` | 任务全生命周期、联邦训练、匿踪查询、联合统计、隐私求交、智能分级 |
| 合规 | `/api/compliance` | 规则 CRUD/启停/画布模板、出境校验、报告生成/预览/下载/导出、趋势、预警 |
| 权限 | `/api/authz` | 授权申请/审批/撤销/续期、风险与预警、权限审计、导出 |
| 预算 | `/api/budget` | 概览、明细、趋势、额度调整、内部转移、申请审批、消耗回调 |
| 血缘 | `/api/lineage` | 图谱、节点详情、溯源详情、链路记录生成与下载、审计检索与导出 |
| 存证 | `/api/audit` | 日志检索、区块查询、链完整性校验、存证证明、统计 |

---

## 七、验证与自测

```bash
# 1. 核心算法自测（14 项，含 SM4 国标向量、联邦学习指标断言、规则引擎阻断语义）
cd fedshield
python -m unittest discover -s backend/tests -v

# 2. 联盟链完整性校验（需先启动过服务）
python run.py --seed
flask --app backend.app:create_app verify-chain
```

代码库中另附静态自检脚本（`_mycheck/check_project.py`）：
Python 语法、Vue 脚本语法（node --check）、模板标签配对、前后端接口一致性、
路由视图存在性、`@/` 别名导入、`xxxApi.method()` 定义完整性的全量检查。

---

## 八、常见问题（对应文档第 4 章）

| 现象 | 排查方向 |
| --- | --- |
| 前端报「网络异常」 | 后端未启动：`python run.py`；确认 5000 端口可用 |
| 登录提示 MFA 错误 | 演示环境动态码固定为 `123456`（可用 `FEDSHIELD_DEMO_MFA` 覆盖） |
| 任务启动提示预算不足 | 「隐私预算管理」中查看剩余额度，或通过「内部调整」转移额度（单次 ≤ 总量 10%） |
| 合规校验被阻断 | 查看返回的 `rectificationList`（整改清单），补齐 SCC/DPIA/授权后重新校验 |
| 匿踪查询耗时偏高 | 切换协议模式为 `oprf`（生产模式）；Paillier 模式耗时随清单规模线性增长 |
| 想切换到 MySQL | `set DATABASE_URL=mysql+pymysql://user:pwd@host:3306/fedshield?charset=utf8mb4` 后重启 |

---

## 九、合规与伦理说明

- 代码中的商户、交易、制裁清单条目 **全部为虚构演示数据**，不对应任何真实主体；
- 法规库中标记 `verified: false` 的条目由区域模板生成，仅用于界面提示与检索，
  **不参与任何阻断性判断**，需法务团队逐条校对后转正；
- 差分隐私的敏感度上界由 DP-SGD 梯度裁剪推导（`federated.update_sensitivity`），
  该数值与具体数据无关，可对外公开举证；
- 平台不采集、不传输任何真实个人数据；所有「跨境传输」均为本地进程内的算法演示。
