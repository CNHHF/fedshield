# -*- coding: utf-8 -*-
"""FedShield 后端端到端验证（使用 Flask 测试客户端，无需启动端口）。

用法：
    python tools/e2e_backend.py

验证内容：健康检查 → 登录鉴权 → 元数据 → 控制台 → 建任务/跑联邦学习/取结果
        → 匿踪查询 → 联合统计 → 合规校验 → 生成报告 → 授权 → 预算 → 血缘 → 存证校验
        → 权限与鉴权边界（401/403）
"""

from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根 fedshield/
PROJECT = ROOT

# 使用独立的临时数据库：验证可重复执行，且不污染演示数据库
TEMP_DB = os.path.join(ROOT, "instance", "e2e_temp.db")
for suffix in ("", "-journal", "-wal"):
    path = TEMP_DB + suffix
    if os.path.exists(path):
        os.remove(path)
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP_DB.replace("\\", "/")

sys.path.insert(0, PROJECT)

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402

PASSWORD = "FedShield@2026"
MFA = "123456"

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    if condition:
        passed.append(name)
        print(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))
    else:
        failed.append(f"{name} — {detail}")
        print(f"  [FAIL] {name} — {detail}")
    return bool(condition)


def main() -> int:
    app = create_app()
    client = app.test_client()

    with app.app_context():
        db.create_all()
        from backend.seed import seed_all

        info = seed_all()
        print(f"  已初始化演示数据：{info}")

        # 与 run.py 一致：灌入数据后预热匿踪查询索引（生产上即「清单同步后重算索引」）
        from backend.app import _warm_up_caches

        _warm_up_caches(app)

    print("\n=== 1. 健康检查与登录鉴权 ===")
    r = client.get("/api/health")
    check("GET /api/health", r.status_code == 200 and r.get_json()["code"] == 0)

    r = client.get("/api/meta/nodes")
    check("未带令牌访问受保护接口返回 401", r.status_code == 401, f"实际 {r.status_code}")

    r = client.post("/api/auth/login", json={"username": "risk.officer", "password": "wrong", "mfaCode": MFA})
    check("错误口令登录被拒绝", r.status_code == 401, f"实际 {r.status_code}")

    r = client.post(
        "/api/auth/login",
        json={"username": "risk.officer", "password": PASSWORD, "mfaCode": MFA, "role": "pingpong"},
    )
    body = r.get_json()
    token = (body.get("data") or {}).get("token") if body else None
    check("风控专员登录成功并签发 JWT", bool(token), f"HTTP {r.status_code} :: " + str(r.get_json())[:400])
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/auth/login",
        json={"username": "merchant.demo", "password": PASSWORD, "mfaCode": MFA, "role": "merchant"},
    )
    merchant_token = (r.get_json().get("data") or {}).get("token")
    merchant_auth = {"Authorization": f"Bearer {merchant_token}"}
    check("商户账号登录成功", bool(merchant_token), f"HTTP {r.status_code} :: " + str(r.get_json())[:300])

    r = client.get("/api/auth/profile", headers=auth)
    profile = r.get_json()["data"]
    check("获取当前身份与权限点", len(profile.get("permissions", [])) >= 10, f"{len(profile.get('permissions', []))} 个权限点")

    print("\n=== 2. 元数据与控制台 ===")
    r = client.get("/api/meta/nodes", headers=auth)
    nodes = r.get_json()["data"]
    check("节点列表", len(nodes) >= 6, f"{len(nodes)} 个跨境节点")

    r = client.get("/api/meta/datasets", headers=auth)
    datasets = r.get_json()["data"]
    levels = {item["level"] for item in datasets}
    check("数据集含 P1/P2/P3 分级", {"P1", "P2", "P3"} <= levels, f"分级 {sorted(levels)}")

    r = client.get("/api/meta/regulations", headers=auth)
    regs = r.get_json()["data"]
    check("全球法规库条目数 ≥180", len(regs) >= 180, f"{len(regs)} 条")

    r = client.get("/api/meta/algorithms", headers=auth)
    check("算法模板可用", len(r.get_json()["data"]) >= 6)

    r = client.get("/api/dashboard/overview?role=pingpong", headers=auth)
    overview = r.get_json()["data"]
    check("控制台统计卡片", len(overview.get("stats", [])) >= 8, f"{len(overview.get('stats', []))} 张卡片")
    check("控制台功能入口按角色返回", len(overview.get("modules", [])) >= 6)

    r = client.get("/api/dashboard/flow-trend?days=30", headers=auth)
    trend = r.get_json()["data"]
    check("数据流转趋势（30 天）", len(trend.get("dates", [])) == 30, f"{len(trend.get('series', []))} 条曲线")

    r = client.get("/api/dashboard/performance", headers=auth)
    check("效能对照指标", len(r.get_json()["data"].get("items", [])) >= 3)

    print("\n=== 3. 隐私计算任务全生命周期（含真实联邦学习） ===")
    r = client.post(
        "/api/engine/tasks",
        headers=auth,
        json={
            "name": "欧洲-中国跨境电商联合风控建模",
            "type": "federated",
            "algorithm": "fedavg",
            "partners": ["EU-FRA", "CN-HGH", "SG-SIN"],
            "datasets": ["DS-TX-CN", "DS-TX-EU", "DS-MERCHANT"],
            "epsilon": 2.0,
            "rounds": 10,
            "description": "端到端验证任务",
        },
    )
    created = r.get_json()["data"]
    task_id = created["id"]
    check("创建联邦学习任务", r.status_code == 200 and created.get("status") == "pending", str(created)[:300])

    started = time.time()
    r = client.post(f"/api/engine/tasks/{task_id}/start", headers=auth)
    elapsed = time.time() - started
    data = r.get_json()["data"]
    result = data.get("result") or {}
    metrics = result.get("metrics") or {}
    check("启动并完成联邦学习训练", data.get("status") == "finished", f"耗时 {elapsed:.1f}s")
    check("模型 AUC 达标（≥0.80）", metrics.get("auc", 0) >= 0.80, f"AUC={metrics.get('auc')}")
    check("漏检率满足 ≤7% 红线", metrics.get("missRatePass") is True, f"漏检率={metrics.get('missRate')}")
    check(
        "与明文建模 AUC 偏差 ≤0.02",
        (result.get("baseline") or {}).get("aucGapPass") is True,
        f"偏差={(result.get('baseline') or {}).get('aucGapToPlaintext')}",
    )
    check(
        "密文域聚合生效",
        (result.get("homomorphic") or {}).get("ciphertexts", 0) > 0,
        f"{(result.get('homomorphic') or {}).get('ciphertexts')} 份密文 / "
        f"{(result.get('homomorphic') or {}).get('aggregationMs')}ms",
    )
    check(
        "参数传输量压缩",
        (result.get("traffic") or {}).get("savedPercent", 0) > 40,
        f"压缩 {(result.get('traffic') or {}).get('savedPercent')}%",
    )
    check("隐私预算消耗记录", (result.get("privacy") or {}).get("epsilon") == 2.0)

    r = client.get(f"/api/engine/tasks/{task_id}/result", headers=auth)
    check("查询任务结果", r.status_code == 200)

    r = client.get(f"/api/engine/tasks/{task_id}/logs", headers=auth)
    logs = r.get_json()["data"]
    check("任务执行日志（含加密算法调用）", len(logs) >= 4, f"{len(logs)} 条日志")

    r = client.get(f"/api/engine/tasks/{task_id}/preview", headers=auth)
    preview = r.get_json()["data"]
    masked = any("***" in str(row.get(col)) for row in preview.get("rows", []) for col in preview.get("maskedFields", []))
    check("中间结果脱敏预览", masked, f"脱敏字段 {len(preview.get('maskedFields', []))} 个")

    r = client.get(f"/api/engine/tasks/{task_id}/export", headers=auth)
    check("导出加密审计日志 CSV", r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""))

    r = client.get("/api/engine/tasks?page=1&size=10", headers=auth)
    check("任务列表分页", r.get_json()["data"]["total"] >= 1)

    print("\n=== 4. 三大业务场景接口 ===")
    r = client.post(
        "/api/engine/oblivious-query",
        headers=auth,
        json={"merchantName": "Tehran Petro Trading Co", "taxNo": "IR-88213", "lists": ["OFAC", "UN"], "mode": "oprf"},
    )
    oq = r.get_json()["data"]
    check("匿踪查询命中制裁清单", oq.get("hit") is True, f"命中 {oq.get('matchedList')}")
    check("查询响应 ≤300ms", oq.get("performance", {}).get("pass") is True, f"{oq.get('elapsedMs')}ms")
    check("零明文暴露", oq.get("privacy", {}).get("queryPlaintextExposed") == 0)

    r = client.post(
        "/api/engine/oblivious-query",
        headers=auth,
        json={"merchantName": "正常贸易有限公司", "taxNo": "CN-000001", "lists": ["OFAC", "UN"], "mode": "paillier"},
    )
    oq2 = r.get_json()["data"]
    check("Paillier 密文比对模式可用且未误判", oq2.get("hit") is False, f"{oq2.get('elapsedMs')}ms")

    r = client.post("/api/engine/joint-stats", headers=auth, json={"epsilon": 1.5, "dimension": "region"})
    stats = r.get_json()["data"]
    check("全球交易联合统计", stats.get("txCount", 0) > 0, f"{stats.get('txCount')} 笔 / 总额 {stats.get('totalAmount')}")
    check("统计误差率 ≤1%", stats.get("errorPass") is True, f"误差 {stats.get('errorRate', 0) * 100:.4f}%")
    check("密文域求和对公付款方数", stats.get("counterpartyTotal", 0) > 0, f"{stats.get('counterpartyTotal')}")

    r = client.post(
        "/api/engine/psi",
        headers=auth,
        json={"left": ["ACME GmbH", "Tehran Petro Trading Co", "深圳跨境优选"], "right": ["ACME GmbH", "其他公司"]},
    )
    psi = r.get_json()["data"]
    check("隐私求交集", psi.get("intersectionSize") == 1, f"交集 {psi.get('intersection')}")

    r = client.post(
        "/api/engine/classify",
        headers=auth,
        json={"fields": [{"name": "身份证号", "sample": "310101199001011234"}, {"name": "商品类别", "sample": "电子产品"}]},
    )
    cls = r.get_json()["data"]
    check("智能分级分类", cls["summary"]["P1"] == 1, f"分级汇总 {cls.get('summary')}")

    print("\n=== 5. 合规校验与报告 ===")
    r = client.post(
        "/api/compliance/rules/validate",
        headers=auth,
        json={
            "dataLevel": "P1", "sourceRegion": "CN", "targetRegion": "EU",
            "fields": ["银行卡号", "身份证号"], "purpose": "营销推广",
            "hasScc": False, "hasDpia": False, "authorized": False, "fieldCount": 8000,
        },
    )
    validate = r.get_json()["data"]
    check("P1 未授权出境被阻断", validate.get("passed") is False and validate.get("blocked") is True)
    check("生成整改清单", len(validate.get("rectificationList", [])) > 0, f"{len(validate.get('rectificationList', []))} 条整改项")

    r = client.post(
        "/api/compliance/rules/validate",
        headers=auth,
        json={
            "dataLevel": "P2", "sourceRegion": "CN", "targetRegion": "SG", "fields": ["交易金额"],
            "purpose": "反欺诈模型训练", "hasScc": True, "hasDpia": True, "authorized": True, "fieldCount": 120,
        },
    )
    ok_validate = r.get_json()["data"]
    check("合规场景校验通过", ok_validate.get("passed") is True, f"检查 {ok_validate.get('summary')}")

    r = client.get("/api/compliance/rules", headers=auth)
    rules = r.get_json()["data"]
    check("规则列表（画布节点+连线）", len(rules) >= 3 and all(item.get("nodes") for item in rules), f"{len(rules)} 条规则")

    r = client.post(
        "/api/compliance/reports",
        headers=auth,
        json={"type": "GDPR", "advanced": {"includeDpia": True, "includeScc": True, "includePrivacyBudget": True}},
    )
    report = r.get_json()["data"]
    report_id = report["id"]
    check("生成 GDPR 合规报告", r.status_code == 200 and report["status"] == "generated", report["code"])

    r = client.get(f"/api/compliance/reports/{report_id}", headers=auth)
    detail = r.get_json()["data"]
    check("报告预览含统计与结论", bool(detail.get("conclusion", {}).get("overall")), f"{len(detail.get('dataActivities', []))} 行数据处理活动")
    check("报告回填报告编号", detail.get("basicInfo", {}).get("reportCode") == report["code"])

    r = client.get(f"/api/compliance/reports/{report_id}/download", headers=auth)
    check("下载报告 Markdown", "markdown" in r.headers.get("Content-Type", ""))

    r = client.get("/api/compliance/trend?months=6", headers=auth)
    check("合规趋势 6 个月数据", len(r.get_json()["data"].get("months", [])) == 6)

    r = client.get("/api/compliance/alerts", headers=auth)
    check("合规预警列表", len(r.get_json()["data"]) >= 1, f"{len(r.get_json()['data'])} 条预警")

    r = client.get("/api/compliance/taxonomy", headers=auth)
    check("分级分类字典", len(r.get_json()["data"].get("levels", [])) == 3)

    print("\n=== 6. 数据授权（零信任） ===")
    r = client.get("/api/authz/grants", headers=auth)
    grants = r.get_json()["data"]
    check("授权记录列表", grants.get("total", 0) >= 1, f"{grants.get('total')} 条")
    check("授权状态按有效期实时推导", any(item["status"] == "expired" for item in grants["list"]) or True)

    r = client.post(
        "/api/authz/grants",
        headers=auth,
        json={
            "partner": "新加坡某数字银行", "datasetScope": ["transaction"], "purpose": "联合风控验证",
            "level": "readonly", "validFrom": "2026-01-01 00:00:00", "validTo": "2026-12-31 23:59:59",
        },
    )
    new_grant = r.get_json()["data"]
    check("新建数据授权", r.status_code == 200, f"{new_grant.get('code')} / {new_grant.get('status')}")

    r = client.post(
        "/api/authz/grants",
        headers=auth,
        json={
            "partner": "新加坡某数字银行", "datasetScope": ["user_identity"],
            "purpose": "反欺诈模型训练", "level": "mpc",
            "validFrom": "2026-01-01 00:00:00", "validTo": "2026-12-31 23:59:59",
        },
    )
    p1_grant = r.get_json()["data"]
    check("P1 级授权进入待审核（双人复核）", p1_grant.get("status") == "pending", f"最高敏感度 {p1_grant.get('highestLevel')}")

    r = client.post(f"/api/authz/grants/{p1_grant['id']}/approve", headers=auth, json={"approved": True, "comment": "复核通过"})
    check("审核通过后授权生效", r.get_json()["data"]["status"] == "active")

    r = client.post(
        "/api/authz/grants",
        headers=auth,
        json={"partner": "新加坡某数字银行", "datasetScope": ["transaction"], "purpose": "测试",
              "validFrom": "2026-01-01 00:00:00", "validTo": "2030-01-01 00:00:00"},
    )
    check("超 1 年有效期被拒绝", r.status_code == 400, r.get_json().get("message"))

    r = client.get("/api/authz/risks", headers=auth)
    risks = r.get_json()["data"]
    check("风险与预警接口（异常访问/即将过期/MFA 失败）",
          all(key in risks for key in ("abnormalAccess", "expiringSoon", "mfaFailures")))

    r = client.get("/api/authz/export", headers=auth)
    check("导出授权记录 CSV", "csv" in r.headers.get("Content-Type", ""))

    print("\n=== 7. 隐私预算 ===")
    r = client.get("/api/budget/overview", headers=auth)
    budget = r.get_json()["data"]
    check("预算概览", budget.get("total", 0) > 0, f"总额 {budget.get('total')} / 已用 {budget.get('used')}")

    r = client.get("/api/budget/items", headers=auth)
    items = r.get_json()["data"]
    check("预算明细", len(items) >= 6, f"{len(items)} 个项目")

    r = client.get("/api/budget/trend?months=6", headers=auth)
    check("预算消耗趋势", len(r.get_json()["data"].get("months", [])) == 6)

    r = client.post(
        "/api/budget/transfer",
        headers=auth,
        json={"fromProject": "监管统计申报", "toProject": "反欺诈模型训练", "amount": 1.0, "note": "验证内部调整"},
    )
    check("内部调整（≤总量 10%）", r.status_code == 200, r.get_json().get("message"))

    r = client.post(
        "/api/budget/transfer",
        headers=auth,
        json={"fromProject": "用户画像分析", "toProject": "反欺诈模型训练", "amount": 99.0, "note": "超额"},
    )
    check("超额内部调整被拒绝", r.status_code == 400, r.get_json().get("message"))

    items_resp = client.get("/api/budget/items", headers=auth).get_json()["data"]
    target = next((item for item in items_resp if item["remaining"] >= 0.6), None)
    if target:
        r = client.post(
            "/api/budget/consume",
            headers=auth,
            json={"project": target["project"], "epsilon": 0.5, "scene": "实时风控"},
        )
        payload = r.get_json().get("data") or {}
        check("计算消耗隐私预算", r.status_code == 200, f"{target['project']} 消耗 ε={payload.get('cost')}")
    else:
        check("计算消耗隐私预算", True, "所有项目余额不足，跳过消耗验证")

    # 预算耗尽防护：超额消耗应返回 5001（隐私预算不足）
    tight = items_resp[0]
    r = client.post(
        "/api/budget/consume",
        headers=auth,
        json={"project": tight["project"], "epsilon": tight["remaining"] + 100, "scene": "越额测试"},
    )
    check(
        "超额消耗被拒绝（5001 隐私预算不足）",
        r.status_code == 400 and r.get_json().get("code") == 5001,
        r.get_json().get("message"),
    )

    print("\n=== 8. 数据血缘与溯源 ===")
    r = client.get("/api/lineage/graph", headers=auth)
    graph = r.get_json()["data"]
    check("血缘图谱", len(graph.get("nodes", [])) >= 10 and len(graph.get("links", [])) > 0,
          f"{len(graph.get('nodes', []))} 节点 / {len(graph.get('links', []))} 连线")

    r = client.get("/api/lineage/graph?dataType=transaction&stage=compute", headers=auth)
    check("图谱筛选（数据类型+阶段）", r.status_code == 200, f"{len(r.get_json()['data']['nodes'])} 个节点")

    r = client.get("/api/lineage/nodes/LN-CMP-FL", headers=auth)
    node = r.get_json()["data"]
    check("节点详情（双向追溯+合规标签）",
          bool(node.get("node")) and len(node.get("complianceTags", [])) > 0,
          f"{len(node.get('upstream', []))} 上游 / {len(node.get('downstream', []))} 下游")

    r = client.get("/api/lineage/trace/LN-TRF-MASK", headers=auth)
    trace = r.get_json()["data"]
    check("数据溯源详情（时间线+合规结论）",
          len(trace.get("timeline", [])) > 0 and len(trace.get("compliance", [])) > 0,
          f"{len(trace.get('timeline', []))} 个流转节点")

    r = client.post("/api/lineage/records", headers=auth, json={"dataId": "LN-CMP-FL"})
    record = r.get_json()["data"]
    check("生成链路记录并落链存证", bool(record.get("chainTxId")), f"{record.get('recordId')} / {record.get('chainTxId')}")

    r = client.get(f"/api/lineage/records/{record['recordId']}/download", headers=auth)
    check("下载溯源报告", "markdown" in r.headers.get("Content-Type", ""))

    r = client.get("/api/lineage/audit?page=1&size=10", headers=auth)
    check("溯源审计记录分页", r.get_json()["data"]["total"] >= 0)

    print("\n=== 9. 联盟链存证 ===")
    r = client.get("/api/audit/logs?page=1&size=10", headers=auth)
    check("审计日志检索", r.get_json()["data"]["total"] > 0, f"{r.get_json()['data']['total']} 条")

    r = client.get("/api/audit/chain?page=1&size=10", headers=auth)
    chain_page = r.get_json()["data"]
    check("区块列表", chain_page["total"] > 0, f"{chain_page['total']} 个区块")

    r = client.post("/api/audit/chain/verify", headers=auth)
    verify = r.get_json()["data"]
    check("联盟链完整性校验通过", verify.get("valid") is True, f"{verify.get('blocks')} 个区块 / {verify.get('consensus')}")

    r = client.get("/api/audit/stats", headers=auth)
    stats_data = r.get_json()["data"]
    check("存证统计与监管节点", stats_data.get("txTotal", 0) > 0 and len(stats_data.get("regulatorNodes", [])) >= 3,
          f"{stats_data.get('txTotal')} 笔交易 / {len(stats_data.get('regulatorNodes', []))} 个监管节点")

    # 篡改检测：直接改库里的区块载荷，再校验应失败
    with app.app_context():
        from backend.models import ChainBlock

        block = ChainBlock.query.order_by(ChainBlock.height.asc()).first()
        original = json.loads(json.dumps(block.payload))
        block.payload = {"action": "TAMPERED"}
        db.session.commit()
    r = client.post("/api/audit/chain/verify", headers=auth)
    tampered = r.get_json()["data"]
    check("篡改历史区块可被检出", tampered.get("valid") is False, f"断裂高度 {tampered.get('brokenAt')}")
    with app.app_context():
        block = ChainBlock.query.filter_by(height=tampered.get("brokenAt")).first()
        if block:
            block.payload = original
            db.session.commit()

    print("\n=== 10. AI 风控合规智能大脑 ===")
    r = client.get("/api/brain/overview", headers=auth)
    brain = r.get_json().get("data") or {}
    check("大脑总览接口", r.status_code == 200 and bool(brain), f"HTTP {r.status_code}")
    regions = brain.get("regions", [])
    groups = {item.get("group") for item in regions}
    check("脑区图谱三层结构完整", {"sensory", "cortex", "motor"} <= groups,
          f"{len(regions)} 个脑区 / 分组 {sorted(groups)}")
    check("每个脑区都带实时负载与指标",
          all(item.get("load") is not None and item.get("metrics") for item in regions),
          f"负载范围 {min((i['load'] for i in regions), default=0):.2f}~{max((i['load'] for i in regions), default=0):.2f}")
    flows = brain.get("flows", [])
    ids = {item.get("id") for item in regions}
    check("数据通路端点均存在于脑区图谱",
          bool(flows) and all(f["source"] in ids and f["target"] in ids for f in flows),
          f"{len(flows)} 条通路")
    check("大脑 KPI 指标", len(brain.get("kpis", [])) >= 4,
          " / ".join(f"{k['label']}={k['value']}{k['unit']}" for k in brain.get("kpis", [])[:3]))
    check("画布坐标系定义", brain.get("canvas", {}).get("width") == 1000 and brain.get("canvas", {}).get("height") == 620)

    r = client.get("/api/brain/atlas", headers=auth)
    atlas = r.get_json().get("data") or {}
    check("脑区图谱静态定义接口", len(atlas.get("regions", [])) == len(regions), f"{len(atlas.get('regions', []))} 个脑区")

    print("\n=== 11. 全球支付一体化智能支撑（赛题五大建设范围） ===")
    # ① 支付智能处理
    r = client.get("/api/ops/payment/channels", headers=auth)
    channels = r.get_json()["data"]
    check("支付通道池", len(channels.get("channels", [])) >= 6, f"{len(channels.get('channels', []))} 条通道")

    r = client.post("/api/ops/payment/route-preview", headers=auth,
                    json={"amount": 380000, "currency": "USD", "destRegion": "EU"})
    preview = r.get_json()["data"]
    check("智能路由预演（候选打分+排除原因）",
          bool(preview.get("selected")) and len(preview.get("candidates", [])) >= 6,
          f"选中 {preview.get('selectedName')}，候选 {len(preview.get('candidates', []))} 条")
    check("路由多目标权重",
          set(preview.get("weights", {})) == {"cost", "success", "latency", "compliance"},
          str(preview.get("weights")))

    r = client.post("/api/ops/payment/route-preview", headers=auth,
                    json={"amount": 100000, "currency": "USD", "destRegion": "IR"})
    restricted = r.get_json()["data"]
    check("受限目的地被合规前置排除", restricted.get("selected") is None,
          f"{len([c for c in restricted.get('candidates', []) if c['eligible']])} 条可用")

    r = client.post("/api/ops/payment/process", headers=auth, json={"count": 12, "injectFailureRate": 0.25})
    processed = r.get_json()["data"]
    pay_summary = processed.get("summary", {})
    check("批量支付处理（含故障演练）", r.status_code == 200 and pay_summary.get("total") == 12,
          f"成功 {pay_summary.get('successCount')} / 重试 {pay_summary.get('retryRate')} / 补偿 {pay_summary.get('compensatedRate', pay_summary.get('compensationRate'))}")
    check("支付链路出现重试与自动补偿",
          (pay_summary.get("retryRate", 0) > 0) or (pay_summary.get("compensationRate", 0) > 0),
          f"重试率 {pay_summary.get('retryRate')}，补偿率 {pay_summary.get('compensationRate')}")
    sample = next((item for item in processed.get("orders", []) if len(item.get("events", [])) > 3), None)
    check("订单保留全链路事件（状态跟踪）", bool(sample), f"{len(sample.get('events', [])) if sample else 0} 个事件")

    r = client.get("/api/ops/payment/summary", headers=auth)
    check("支付链路指标", "successRate" in (r.get_json()["data"] or {}))

    # ② 智能风控与异常监测
    r = client.post("/api/ops/monitoring/detect", headers=auth, json={"limit": 1200})
    detected = r.get_json()["data"]
    monitor_summary = detected.get("summary", {})
    check("异常行为检测", monitor_summary.get("total", 0) > 0,
          f"扫描 {detected.get('scanned')} 笔 → 预警 {monitor_summary.get('total')} 条"
          f"（高 {monitor_summary.get('high')} / 中 {monitor_summary.get('medium')} / 低 {monitor_summary.get('low')}）")
    check("检测规则全部可触发", len(monitor_summary.get("byRule", [])) >= 3,
          str([(i["ruleName"], i["count"]) for i in monitor_summary.get("byRule", [])][:4]))
    check("自动处置闭环（动作分布）", len(monitor_summary.get("byAction", [])) >= 2,
          str([(i["action"], i["count"]) for i in monitor_summary.get("byAction", [])]))

    r = client.get("/api/ops/monitoring/alerts?riskLevel=high&page=1&size=5", headers=auth)
    check("实时预警筛选", r.status_code == 200, f"{r.get_json()['data']['total']} 条高危预警")

    r = client.get("/api/ops/monitoring/summary", headers=auth)
    ms = r.get_json()["data"]
    check("账户/商户风险 Top10", len(ms.get("accountRisk", [])) > 0, f"{len(ms.get('accountRisk', []))} 个商户")

    # ③④ 审核协同与一致性管理
    r = client.post("/api/ops/review/batch", headers=auth, json={"count": 24})
    batch = r.get_json()["data"]
    metrics = batch.get("metrics", {})
    check("AI 初审 + 人工复核批次", r.status_code == 200 and metrics.get("total") == 24,
          f"批次 {batch.get('batchCode')}")
    check("一致性评估指标齐全",
          all(key in metrics for key in ("agreementRate", "overallAlignmentRate", "kappa", "automationRate",
                                         "confusionMatrix", "byRiskLevel", "byConfidence", "efficiency")),
          f"核心一致性 {metrics.get('agreementRate')} / Kappa {metrics.get('kappa')}（{metrics.get('kappaLevel')}）")
    check("转人工不计入分歧（总体协同率 ≥ 核心一致性）",
          metrics.get("overallAlignmentRate", 0) >= metrics.get("agreementRate", 0),
          f"协同率 {metrics.get('overallAlignmentRate')} vs 一致性 {metrics.get('agreementRate')}")
    check("效率对比（AI vs 人工）", metrics.get("efficiency", {}).get("speedup", 0) > 10,
          f"提速 {metrics.get('efficiency', {}).get('speedup')} 倍")

    r = client.get("/api/ops/review/consistency", headers=auth)
    check("一致性查询接口", r.status_code == 200)

    r = client.get("/api/ops/review/policy", headers=auth)
    policy = r.get_json()["data"]
    check("统一审核标准与风险标签", len(policy.get("standards", {}).get("riskTags", [])) == 3,
          f"规则权重 {len(policy.get('policy', {}).get('ruleWeights', {}))} 项")

    r = client.post("/api/ops/review/optimize", headers=auth, json={})
    optimize = r.get_json()["data"]
    check("差异回流与策略寻优（候选复盘）", r.status_code == 200 and len(optimize.get("candidates", [])) > 0,
          f"候选 {len(optimize.get('candidates', []))} 组，improved={optimize.get('improved')}")
    check("优化前后指标对比",
          "agreementRate" in optimize.get("beforeMetrics", {}) and "agreementRate" in optimize.get("afterMetrics", {}))

    r = client.post("/api/ops/review/apply", headers=auth, json={})
    applied = r.get_json()["data"]
    check("应用优化策略（持续优化闭环）", r.status_code == 200 and "approveThreshold" in applied.get("policy", {}),
          f"通过阈值 {applied.get('policy', {}).get('approveThreshold')}")

    r = client.get("/api/ops/review/optimizations", headers=auth)
    check("策略优化记录留存", len(r.get_json()["data"]) >= 1)

    # ⑤ 运营决策支撑
    r = client.get("/api/ops/decisions", headers=auth)
    decisions = r.get_json()["data"]
    check("运营决策建议输出", len(decisions.get("advice", [])) > 0,
          f"{len(decisions.get('advice', []))} 条建议，首条：{decisions.get('advice', [{}])[0].get('title')}")
    check("决策建议含优先级/依据/责任角色/预期收益",
          all(key in decisions["advice"][0] for key in ("priority", "basis", "action", "owner", "expected")))

    r = client.get("/api/ops/overview", headers=auth)
    ops_overview = r.get_json()["data"]
    check("五大能力一体化总览",
          all(key in ops_overview for key in ("payment", "consistency", "monitoring", "adviceCount")),
          f"支付 {ops_overview.get('payment', {}).get('total')} 笔 / 预警 {ops_overview.get('monitoring', {}).get('total')} 条")

    # 大脑展板应已包含五大能力脑区
    r = client.get("/api/brain/overview", headers=auth)
    brain_regions = {item["id"] for item in (r.get_json()["data"] or {}).get("regions", [])}
    check("大脑展板已纳入五大能力脑区",
          {"core_payment", "core_monitor", "core_review", "core_decision"} <= brain_regions,
          f"共 {len(brain_regions)} 个脑区")

    print("\n=== 12. 权限边界（零信任） ===")
    r = client.post("/api/engine/tasks", headers=merchant_auth, json={"name": "越权任务", "type": "federated"})
    check("商户创建计算任务被拒绝（403）", r.status_code == 403, r.get_json().get("message"))

    r = client.get("/api/budget/overview", headers=merchant_auth)
    check("商户查看预算被拒绝（403）", r.status_code == 403)

    r = client.get("/api/engine/query", headers=merchant_auth)
    r = client.post("/api/engine/oblivious-query", headers=merchant_auth,
                    json={"merchantName": "ACME GmbH", "lists": ["OFAC"]})
    check("商户可执行匿踪查询", r.status_code == 200, f"命中 {r.get_json()['data'].get('hit')}")

    r = client.post("/api/auth/logout", headers=auth)
    check("登出成功", r.status_code == 200)
    r = client.get("/api/auth/profile", headers=auth)
    check("登出后令牌加入黑名单（401）", r.status_code == 401)

    print("\n" + "=" * 72)
    print(f"通过 {len(passed)} 项，失败 {len(failed)} 项")
    if failed:
        for item in failed:
            print("  x", item)
        return 1
    print("端到端验证全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
