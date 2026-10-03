# FedShield 平台 API 契约（v1.1）

> 后端基址：`http://127.0.0.1:5000`，所有业务接口统一前缀 `/api`。
> 前端开发服务器（Vite，5173）通过 `vite.config.js` 的 proxy 转发 `/api` 到 5000 端口。

## 0. 通用约定

### 0.1 统一响应体

```json
{ "code": 0, "message": "ok", "data": {}, "requestId": "req-8f2c1a" }
```

| 字段 | 说明 |
| --- | --- |
| `code` | 0 成功；400x 参数/权限问题；500x 服务端异常 |
| `message` | 提示信息，前端直接用于 `ElMessage` |
| `data` | 业务数据，见各接口 |
| `requestId` | 链路追踪 ID，写入审计日志 |

### 0.2 认证

除 `/api/auth/login`、`/api/health` 外，所有接口需要请求头：

```
Authorization: Bearer <JWT>
```

JWT 载荷：`{ sub: username, role: <role>, org: <org>, exp, iat, jti }`；角色与权限矩阵见 §9。

### 0.3 角色（role）

| 取值 | 含义 | 前端视图 |
| --- | --- | --- |
| `pingpong` | PingPong 平台运营/风控（内部） | 全量业务视图 |
| `merchant` | 跨境电商 / 外贸 B2B 商户 | 交易统计、黑名单查询、合规状态 |
| `regulator` | 全球监管机构 | 数据流转日志、合规报告、审计 |
| `admin` | 数据安全管理员 | 权限、预算、规则、审计全量 |

### 0.4 分页

请求：`?page=1&size=10`；响应：

```json
{ "list": [], "total": 36, "page": 1, "size": 10 }
```

### 0.5 数据分级（P1/P2/P3）

| 级别 | 定义 | 加密策略 |
| --- | --- | --- |
| P1 | 高敏感：身份证号、银行卡号、生物特征、收付款方实名信息 | 国密 SM4 + Paillier 同态加密（双重） |
| P2 | 中敏感：交易金额、商户税号、地址 | 差分隐私（Laplace）+ AES-256-GCM |
| P3 | 低敏感：商品类别、币种、地区编码 | AES-256-GCM |

---

## 1. 认证与用户 `/api/auth`

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| POST | `/api/auth/login` | 登录（密码 + MFA 动态码 + 数字证书校验） | `{username, password, role, mfaCode, certNo?}` | `{token, expiresIn, user:{username,displayName,role,org,certExpireAt}}` |
| POST | `/api/auth/logout` | 登出（JWT 加入黑名单） | — | `{success:true}` |
| GET | `/api/auth/profile` | 当前用户信息 + 权限点 | — | `{user:{...}, permissions:["engine:task:create", ...]}` |
| GET | `/api/auth/roles` | 角色与权限矩阵 | — | `[{role,label,description,permissions:[]}]` |
| GET | `/api/auth/sessions` | 在线会话（含异常登录检测） | — | `[{username,role,region,loginAt,ip,risk}]` |

**演示账号**（`seed.py` 写入，密码统一为 `FedShield@2026`，MFA 动态码 `123456`）：

| 用户名 | 角色 | 机构 |
| --- | --- | --- |
| `risk.officer` | pingpong | PingPong 风控技术部 |
| `compliance.lead` | pingpong | PingPong 全球合规部 |
| `merchant.demo` | merchant | 深圳跨境优选电商 |
| `regulator.eu` | regulator | 欧盟 EDPB |
| `security.admin` | admin | PingPong 数据安全部 |

---

## 2. 元数据 `/api/meta`

| 方法 | 路径 | 说明 | 响应 data |
| --- | --- | --- | --- |
| GET | `/api/meta/nodes` | 跨境协作节点 | `[{code,name,region,status,latencyMs,certExpireAt}]` |
| GET | `/api/meta/datasets` | 数据集（含分级） | `[{code,name,level,owner,region,rows,fields:[]}]` |
| GET | `/api/meta/partners` | 已认证合作方 | `[{code,name,region,orgType,certNo,certExpireAt,verified}]` |
| GET | `/api/meta/algorithms` | 算法模板 | `[{code,name,desc,hyperParams:[{key,label,type,default,min,max}]}]` |
| GET | `/api/meta/task-types` | 任务类型 | `[{code,name,tech,desc,engine}]` |
| GET | `/api/meta/report-types` | 合规报告类型 | `[{code,name,regulation,desc}]` |
| GET | `/api/meta/regulations` | 法规库（180+ 国家/地区） | `[{code,name,region,sensitiveScope,transferRule,auditRetentionYears,updatedAt}]` |
| GET | `/api/meta/budget-categories` | 预算项目类别 | `[{code,name,desc}]` |
| GET | `/api/meta/dicts` | 前端下拉字典（汇总） | `{taskStatus:[],grantStatus:[],reportStatus:[],riskLevel:[],dataLevel:[]}` |

---

## 3. 数据概览控制台 `/api/dashboard`

| 方法 | 路径 | 说明 | 响应 data |
| --- | --- | --- | --- |
| GET | `/api/dashboard/overview?role=` | 统计卡片 + 节点状态 + 功能入口 | `{stats:[{key,label,value,unit,delta,trend}], nodes:[], modules:[]}` |
| GET | `/api/dashboard/flow-trend?days=30` | 数据流转趋势（折线） | `{dates:[], series:[{name,data:[]}]}` |
| GET | `/api/dashboard/alerts?limit=5` | 合规/风险告警 | `[{code,level,title,content,requirement,createdAt,status,source}]` |
| GET | `/api/dashboard/risk-distribution` | 风险分布（饼图） | `[{name:"高风险",value:12},...]` |
| GET | `/api/dashboard/performance` | 效能指标（明文对照） | `{items:[{name,plain,secure,ratio,standard,pass}]}` |

---

## 3.5 AI 风控合规智能大脑 `/api/brain`

对应赛题「面向全球支付场景的 AI 驱动风控合规智能大脑框架」，把平台模块映射为**脑区图谱**
（感知输入层 → 脑区计算层 → 决策输出层），并以真实业务指标驱动数据流动画。

| 方法 | 路径 | 说明 | 响应 data |
| --- | --- | --- | --- |
| GET | `/api/brain/overview` | 大脑总览：脑区 + 数据通路 + KPI + 实时脉冲 | 见下 |
| GET | `/api/brain/atlas` | 脑区图谱静态定义（坐标、分组、通路） | `{canvas, regions, flows, groups}` |

`/api/brain/overview` 响应结构：

```json
{
  "canvas": { "width": 1000, "height": 620 },
  "title": "AI 风控合规智能大脑",
  "groups": [{ "code": "sensory", "name": "感知输入层" }],
  "regions": [
    {
      "id": "core_risk", "name": "联合风控决策核", "group": "cortex", "groupLabel": "脑区计算层",
      "x": 372, "y": 158, "desc": "横向联邦学习联合建模，输出风险评分与标签",
      "load": 0.42, "status": "active", "symbolSize": 36.9,
      "metrics": [{ "label": "建模任务", "value": "3/4", "unit": "完成/总" }]
    }
  ],
  "flows": [
    { "source": "core_crypto", "target": "core_risk", "label": "密文聚合",
      "value": 0.63, "throughput": 193 }
  ],
  "kpis": [{ "key": "regions", "label": "在线脑区", "value": 13, "unit": "个", "sub": "感知 4 · 计算 6 · 输出 3" }],
  "events": [{ "ts": "15:20:31", "actor": "risk.officer", "action": "task.finish",
               "target": "TASK-20261003-0001", "result": "success", "chainTxId": "tx-..." }],
  "performance": [{ "label": "密文聚合耗时", "value": 1032.95, "unit": "ms" }],
  "updatedAt": "2026-10-03 15:20:31"
}
```

**脑区划分**（13 个）：感知输入层 4 个（全球交易流、监管制裁清单、商户主数据、全球法规更新）；
脑区计算层 6 个（联合风控决策核、合规判断核、密文计算核、隐私预算调度核、数据血缘记忆核、联盟链存证核）；
决策输出层 3 个（风险评分与标签、拦截与告警指令、监管合规报告）。
`load`（0~1）由真实指标折算，前端据此调整节点尺寸与颜色，`flows.value` 决定脉冲强度。

---

## 3.6 全球支付一体化智能支撑 `/api/ops`

对应赛题 A16 五大建设范围，是「AI 驱动风控合规智能大脑」的核心业务接口。

### ① 支付智能处理能力 `/api/ops/payment`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ops/payment/channels` | 通道池（费率/成功率/时延/限额/健康状态）、受限目的地、重试策略、路由权重 |
| POST | `/api/ops/payment/route-preview` | 智能路由预演：`{amount,currency,destRegion,riskLevel}` → 候选通道打分与排除原因 |
| POST | `/api/ops/payment/process` | 批量处理：`{count:1~50, injectFailureRate:0~0.6}` → 全链路订单与链路指标 |
| GET | `/api/ops/payment/orders` | 订单列表，支持 `status/channel/riskLevel/keyword/page/size` |
| GET | `/api/ops/payment/orders/<code>` | 订单详情（含 `events` 全链路事件：接入→风控→路由→处理→重试→补偿） |
| GET | `/api/ops/payment/summary` | 链路指标：成功率、直通率、重试率、补偿率、风控拦截率、平均/P95 耗时、通道路由分布 |

订单状态机：`received → risk_checked → routed → processing → success / failed → retrying → compensated`，
风控前置命中时进入 `blocked`（自动拦截）或 `manual`（转人工）。
`injectFailureRate` 为**通道故障演练**开关，用于演示失败重试与自动补偿能力。

### ② 智能风控与异常监测 `/api/ops/monitoring`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ops/monitoring/rules` | 异常检测规则（6 条）与统一处置口径（放行/二次验证/转人工/拦截） |
| POST | `/api/ops/monitoring/detect` | `{limit:20~2000}` 执行异常检测 → `{summary, alerts, scanned}` |
| GET | `/api/ops/monitoring/alerts` | 实时预警列表，支持 `riskLevel/action/status/page/size` |
| POST | `/api/ops/monitoring/alerts/<id>/handle` | 人工确认处置结果（自动处置 + 人工确认闭环） |
| GET | `/api/ops/monitoring/summary` | 预警汇总、处置分布、自动化处置率、账户/商户风险 Top10 |

检测规则：短时高频（按「商户 × 小时」窗口）、金额突增、高风险地区/高风险交易、
夜间集中交易、收款人分散度异常、新商户大额；同一商户命中多条规则时叠加**组合风险加成**。

### ③④ 智能合规审核与 AI 审核一致性管理 `/api/ops/review`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/ops/review/batch` | 执行审核批次：AI 初审 → 人工复核 → 差异标记，`{count:4~60}` |
| GET | `/api/ops/review/records` | 审核记录，支持 `batchCode/agreed/diffType/riskLevel/page/size` |
| GET | `/api/ops/review/batches` | 批次列表 |
| GET | `/api/ops/review/consistency` | **一致性评估**（见下） |
| GET | `/api/ops/review/policy` | 当前审核策略与统一标准（结论口径 + 风险标签体系） |
| POST | `/api/ops/review/optimize` | **差异回流**：网格搜索最优策略并给出优化前后对比 |
| POST | `/api/ops/review/apply` | 应用优化策略（形成持续优化闭环） |
| GET | `/api/ops/review/optimizations` | 策略优化记录（证据链） |

一致性评估口径（关键）：

| 指标 | 含义 |
| --- | --- |
| `agreementRate` | **核心一致性**：仅统计 AI 自主决策（approve/reject）样本中与人工结论一致的比例 |
| `overallAlignmentRate` | 总体协同率：转人工样本计入「已协同处理」，不视为分歧 |
| `automationRate` / `manualTransferRate` | AI 可独立决策比例 / 转人工比例（低置信度强制转人工） |
| `kappa` / `kappaLevel` | Cohen's Kappa（排除随机一致后的真实一致性水平） |
| `confusionMatrix` | AI 结论 × 人工结论 三分类混淆矩阵 |
| `falseNegativeCount` / `falsePositiveCount` | 漏放（AI 通过但人工拒绝）/ 误拦（AI 拒绝但人工通过） |
| `byRiskLevel` / `byConfidence` | 按风险等级、按置信度区间的一致性 |
| `efficiency` | AI 初审与人工复核的平均耗时与提速倍数 |

策略寻优采用**候选阈值网格复盘**：对每组候选策略用同一批真实样本复盘，
硬约束为「漏放率不得上升 且 一致性不得低于当前的 98%」，
综合得分 `= 0.6×一致性 + 0.25×自动化率 − 1.0×漏放率`；若无更优解则明确返回"维持现状"。

### ⑤ 运营决策支撑 `/api/ops`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ops/decisions` | 决策建议（优先级/依据/动作/责任角色/预期收益）+ 三组指标 |
| GET | `/api/ops/overview` | 五大能力总览（支付 / 一致性 / 监测 / 建议条数） |

---

## 4. 隐私计算引擎 `/api/engine`

### 4.1 任务管理

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| POST | `/api/engine/tasks` | 创建任务 | `{name,type,algorithm,partners:[code],datasets:[code],epsilon,rounds,description,hyper:{}}` | `{id,code,status}` |
| GET | `/api/engine/tasks?status=&type=&keyword=&page=&size=` | 任务列表 | — | 分页：`[{id,code,name,type,typeName,algorithm,partners:[],status,progress,epsilon,createdAt,durationMs}]` |
| GET | `/api/engine/tasks/<id>` | 任务详情（含参数、资源消耗、结果摘要） | — | `{...task, params:{cipher,iterations,quantization,batch}, resource:{cpuSec,memMb,netMb}, result:{}}` |
| POST | `/api/engine/tasks/<id>/start` | 启动 | — | `{status,progress}` |
| POST | `/api/engine/tasks/<id>/pause` | 暂停 | — | `{status}` |
| POST | `/api/engine/tasks/<id>/cancel` | 取消 | — | `{status}` |
| POST | `/api/engine/tasks/<id>/rerun` | 重新计算 | — | `{id:newId,status}` |
| GET | `/api/engine/tasks/<id>/logs` | 加密算法调用日志 | — | `[{ts,stage,message,cipher,digest}]` |
| GET | `/api/engine/tasks/<id>/result` | 计算结果 | — | 见 4.2 |
| GET | `/api/engine/tasks/<id>/export` | 导出加密审计日志（CSV 文件流） | — | `text/csv` 附件 |
| GET | `/api/engine/tasks/<id>/preview` | 中间结果脱敏预览 | — | `{columns:[],rows:[],maskedFields:[]}` |

### 4.2 三大业务场景计算

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| POST | `/api/engine/federated-training` | 跨境电商联合风控建模（横向联邦 + 差分隐私 + 同态聚合） | `{taskId? ,nodes:[code], rounds:10, epsilon:2.0, algorithm:"fedavg"\|"fedprox", timeDecay:0.15, quantize:true}` | `{auc,accuracy,recall,missRate,precision,rounds:[{round,loss,auc,epsilonUsed,aggMs,trafficKb}], trafficSavedPercent, plainBaseline:{auc,missRate}, chainTxId}` |
| POST | `/api/engine/oblivious-query` | 外贸 B2B 黑名单匿踪查询（Paillier 密文比对） | `{merchantName,taxNo,lists:["OFAC","UN"]}` | `{hit,matchedList,matchedEntity,elapsedMs,steps:[{name,ms,cipher}],queryDigest,chainTxId}` |
| POST | `/api/engine/joint-stats` | 全球交易联合统计（同态求和 + 差分隐私计数） | `{dimension:"region"\|"category"\|"month", startDate?, endDate?, epsilon:1.5}` | `{totalAmount,currency,txCount,byRegion:[{name,amount,count}],byCategory:[{name,amount,share}],errorRate,epsilonUsed,chainTxId}` |
| POST | `/api/engine/psi` | 隐私求交集（RSA 盲签名 PSI） | `{left:[], right:[], salt?}` | `{intersection:[], leftSize,rightSize,intersectionSize,elapsedMs,chainTxId}` |
| POST | `/api/engine/classify` | 智能分级（敏感字段识别） | `{fields:[{name,sample}]}` | `{results:[{name,level,confidence,category,rule}], summary:{P1:0,P2:0,P3:0}}` |

---

## 5. 合规校验与报告 `/api/compliance`

### 5.1 规则引擎

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| GET | `/api/compliance/rules?scene=&enabled=` | 规则列表 | — | `[{id,code,name,description,scene,priority,enabled,updatedAt,updatedBy,version,nodes:[],edges:[]}]` |
| POST | `/api/compliance/rules` | 新建规则（画布节点+连线） | `{name,description,scene,priority,enabled,nodes:[],edges:[]}` | `{id,code}` |
| PUT | `/api/compliance/rules/<id>` | 保存规则 | 同上 | `{id,version}` |
| DELETE | `/api/compliance/rules/<id>` | 删除规则 | — | `{success:true}` |
| POST | `/api/compliance/rules/<id>/toggle` | 启用/禁用 | `{enabled:true}` | `{id,enabled}` |
| POST | `/api/compliance/rules/validate` | 合规校验（数据出境前） | `{dataLevel,sourceRegion,targetRegion,fields:[],purpose,hasScc,hasDpia,authorized}` | `{passed,checkedRules:[{code,name,result,detail}],issues:[{rule,level,message,rectification}],rectificationList:[]}` |
| GET | `/api/compliance/rule-templates` | 画布节点模板（触发条件/判断/执行动作） | — | `{triggers:[],conditions:[],actions:[]}` |

`nodes` / `edges` 结构（前端拖拽画布 ↔ 后端规则引擎）：

```json
{
  "nodes": [
    { "id": "n1", "type": "trigger", "name": "数据跨境传输", "x": 80, "y": 120,
      "config": { "event": "data.transfer" } },
    { "id": "n2", "type": "condition", "name": "数据敏感度为 P1", "x": 320, "y": 120,
      "config": { "field": "dataLevel", "op": "eq", "value": "P1" } },
    { "id": "n3", "type": "action", "name": "阻断并生成整改清单", "x": 560, "y": 120,
      "config": { "action": "block", "notify": ["security.admin"], "message": "P1 数据禁止未授权出境" } }
  ],
  "edges": [ { "source": "n1", "target": "n2" }, { "source": "n2", "target": "n3" } ]
}
```

支持的 `op`：`eq` `ne` `gt` `gte` `lt` `lte` `in` `contains` `exists` `regex`。
支持的动作 `action`：`block`（阻断）`mask`（脱敏）`require`（补充要件）`notify`（告警）`audit`（存证）`allow`（放行）。

### 5.2 合规报告

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| POST | `/api/compliance/reports` | 生成报告 | `{type,periodStart,periodEnd,regions:[],advanced:{includeDpia,includeScc,includeSubjectRights}}` | `{id,code,status}` |
| GET | `/api/compliance/reports?status=&type=&page=&size=` | 报告记录 | — | 分页 `[{id,code,type,typeName,periodStart,periodEnd,status,createdAt,createdBy,sizeKb}]` |
| GET | `/api/compliance/reports/<id>` | 报告预览（结构化内容） | — | `{id,code,type,typeName,period,createdAt,basicInfo:{},dataActivities:[],subjectRights:[],conclusion:{overall,issues:[],suggestions:[]},chainTxId}` |
| POST | `/api/compliance/reports/<id>/regenerate` | 重新生成 | — | `{id,status}` |
| GET | `/api/compliance/reports/<id>/download` | 下载（Markdown/CSV 附件流） | — | `text/markdown` 附件 |
| GET | `/api/compliance/reports/export` | 导出报告列表 CSV | — | `text/csv` |
| GET | `/api/compliance/trend?months=6&regions=EU,US,SEA` | 跨境合规趋势 | — | `{months:[], series:[{region,name,data:[]}]}` |
| GET | `/api/compliance/alerts?limit=20` | 合规预警 | — | `[{code,level,title,content,requirement,source,createdAt,status}]` |
| GET | `/api/compliance/taxonomy` | 分级分类字典与统计 | — | `{levels:[{code,name,desc,count}], total}` |

---

## 6. 多方协同权限管控 `/api/authz`

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| GET | `/api/authz/grants?status=&keyword=&page=&size=` | 授权记录 | — | 分页 `[{id,code,partner,partnerRegion,datasetScope:[],purpose,level,validFrom,validTo,status,permissions:[],certExpireAt}]` |
| POST | `/api/authz/grants` | 新建授权申请 | `{partner,datasetScope:[],purpose,level,validFrom,validTo,permissions:[],remark}` | `{id,code,status}` |
| GET | `/api/authz/grants/<id>` | 授权详情（含权限变更日志） | — | `{...grant, history:[]}` |
| POST | `/api/authz/grants/<id>/approve` | 审批通过 | `{approved:true,comment}` | `{id,status}` |
| POST | `/api/authz/grants/<id>/revoke` | 撤销 | `{reason}` | `{id,status}` |
| POST | `/api/authz/grants/<id>/renew` | 续期 | `{validTo}` | `{id,validTo,status}` |
| GET | `/api/authz/export` | 导出授权记录 CSV | — | `text/csv` |
| GET | `/api/authz/filters` | 筛选项（授权对象/数据范围/使用目的） | — | `{partners:[], scopes:[], purposes:[]}` |
| GET | `/api/authz/risks` | 异常访问/即将过期授权（监管视图） | — | `{abnormalAccess:[], expiringSoon:[], mfaFailures:[]}` |
| GET | `/api/authz/audit?page=&size=` | 权限变更与计算请求审计 | — | 分页 `[{ts,actor,action,target,result,riskScore}]` |

---

## 7. 隐私预算动态管理 `/api/budget`

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| GET | `/api/budget/overview` | 预算概览 | — | `{total,used,remaining,usedRatio,remainingRatio,monthUsed,alerts:[],composition:[{name,value}]}` |
| GET | `/api/budget/items` | 项目预算明细 | — | `[{id,project,category,total,used,remaining,usedRatio,level,updatedAt}]` |
| GET | `/api/budget/trend?months=6` | 消耗趋势（堆叠柱 + 折线） | — | `{months:[], used:[], remaining:[], usedRatio:[]}` |
| POST | `/api/budget/items/<id>/adjust` | 调整单项额度 | `{total,reason}` | `{id,total,used,remaining}` |
| POST | `/api/budget/transfer` | 项目间内部调整（≤总量 10%） | `{fromProject,toProject,amount,note}` | `{from:{},to:{},record:{}}` |
| POST | `/api/budget/applications` | 新增预算申请 | `{project,category,amount,reason,expectedAt}` | `{id,code,status}` |
| GET | `/api/budget/applications?status=&page=&size=` | 申请列表 | — | 分页 `[{id,code,project,category,amount,status,applicant,createdAt}]` |
| POST | `/api/budget/applications/<id>/approve` | 审批 | `{approved:true,comment}` | `{id,status}` |
| GET | `/api/budget/adjustments` | 调整记录报告 | — | `[{id,code,fromProject,toProject,amount,operator,createdAt,note}]` |
| POST | `/api/budget/consume` | 计算消耗预算（引擎回调，演示用） | `{project,epsilon,scene}` | `{project,used,remaining,warning}` |

---

## 8. 数据血缘与溯源 `/api/lineage`

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| GET | `/api/lineage/graph?dataType=&stage=&start=&end=&keyword=` | 血缘图谱 | — | `{nodes:[{id,name,type,stage,owner,region,level,tags:[],processedAt}], links:[{source,target,operation,ts}]}` |
| GET | `/api/lineage/nodes/<id>` | 节点详情（元数据 + 双向追溯） | — | `{node, upstream:[], downstream:[], rules:[], complianceTags:[]}` |
| GET | `/api/lineage/trace/<dataId>` | 数据溯源详情 | — | `{basic:{dataId,name,type,level,createdAt,updatedAt,owner}, timeline:[{ts,node,action,operator,detail}], compliance:[{label,passed,standard}]}` |
| POST | `/api/lineage/records` | 生成链路记录（含合规标签，落链存证） | `{dataId,range?}` | `{recordId,chainTxId,nodes:0,generatedAt}` |
| GET | `/api/lineage/records/<recordId>/download` | 导出 PDF/Markdown 溯源报告 | — | `text/markdown` 附件 |
| GET | `/api/lineage/audit?dataId=&operation=&dataType=&start=&end=&page=&size=` | 溯源审计记录 | — | 分页 `[{id,ts,operator,role,operation,dataId,dataType,node,result,riskScore,signature}]` |
| GET | `/api/lineage/audit/export` | 导出审计记录 CSV/Excel | — | `text/csv` 附件 |

---

## 9. 审计存证（联盟链） `/api/audit`

| 方法 | 路径 | 说明 | 请求 | 响应 data |
| --- | --- | --- | --- | --- |
| GET | `/api/audit/logs?actor=&action=&start=&end=&page=&size=` | 审计日志检索（ELK 风格） | — | 分页 `[{id,ts,actor,role,action,target,result,riskScore,signature,chainTxId}]` |
| GET | `/api/audit/chain?page=&size=` | 区块列表 | — | 分页 `[{height,txId,ts,payloadDigest,prevHash,hash,node}]` |
| POST | `/api/audit/chain/verify` | 链完整性校验 | — | `{valid:true,blocks:128,brokenAt:null,checkedAt}` |
| GET | `/api/audit/chain/<txId>` | 按交易 ID 查询存证 | — | `{txId,block,payload,proof}` |
| GET | `/api/audit/stats` | 存证统计 | — | `{txTotal,blockHeight,tps,retentionYears,regulatorNodes:[]}` |

---

## 10. 权限点（permission）与角色的对应

| 权限点 | pingpong | merchant | regulator | admin |
| --- | --- | --- | --- | --- |
| `engine:task:*` | ✅ | ❌ | ❌ | ✅ |
| `engine:query:oblivious` | ✅ | ✅ | ❌ | ✅ |
| `engine:stats:joint` | ✅ | ✅（仅本商户） | ✅（只读汇总） | ✅ |
| `compliance:rule:*` | ✅（合规负责人） | ❌ | ❌ | ✅ |
| `compliance:report:create` | ✅ | ✅ | ❌ | ✅ |
| `compliance:report:view` | ✅ | ✅（本商户） | ✅（全量） | ✅ |
| `authz:grant:*` | ✅ | ❌ | ❌ | ✅ |
| `authz:grant:view` | ✅ | ✅ | ✅ | ✅ |
| `budget:*` | ✅ | ❌ | ❌ | ✅ |
| `lineage:view` | ✅ | ✅（本商户数据） | ✅ | ✅ |
| `audit:chain:verify` | ❌ | ❌ | ✅ | ✅ |

后端在蓝图里通过 `@require_permission("engine:task:create")` 装饰器校验；前端在 `src/router/index.js` 的 `meta.permission` 与 `src/store/user.js` 的 `hasPermission()` 中同步控制。

---

## 11. 错误码

| code | 含义 |
| --- | --- |
| 0 | 成功 |
| 400 | 参数校验失败 |
| 401 | 未认证 / Token 过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 状态冲突（如任务已启动） |
| 429 | 触发熔断/限流 |
| 500 | 服务端异常 |
| 5001 | 隐私预算不足 |
| 5002 | 合规校验未通过（附整改清单） |
| 5003 | 加密/解密失败 |
| 5004 | 节点未授权或证书过期 |
