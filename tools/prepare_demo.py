# -*- coding: utf-8 -*-
"""准备演示数据：重置 → 联邦建模 → 异常检测 → 支付处理 → 审核批次（不应用优化，留作演示）。

用法（在仓库根目录执行）：
    python tools/prepare_demo.py

适用场景：演示或录制视频前，一次性生成大脑展板、支付链路、异常预警与审核批次等演示数据。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app, _warm_up_caches
from backend.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
    from backend.seed import reset_all, seed_all

    reset_all()
    print("① 演示数据重置：", seed_all())
    _warm_up_caches(app)

client = app.test_client()
token = client.post(
    "/api/auth/login",
    json={"username": "risk.officer", "password": "FedShield@2026", "mfaCode": "123456"},
).get_json()["data"]["token"]
headers = {"Authorization": f"Bearer {token}"}

# ② 联邦建模任务（大脑「联合风控决策核」显示真实 AUC）
task = client.post("/api/engine/tasks", headers=headers, json={
    "name": "欧洲-中国跨境电商联合风控建模", "type": "federated", "algorithm": "fedavg",
    "partners": ["EU-FRA", "CN-HGH", "SG-SIN"], "datasets": ["DS-TX-CN", "DS-TX-EU", "DS-MERCHANT"],
    "epsilon": 2.0, "rounds": 10, "description": "演示库预置任务",
}).get_json()["data"]
result = client.post(f"/api/engine/tasks/{task['id']}/start", headers=headers).get_json()["data"]
metrics = (result.get("result") or {}).get("metrics", {})
print(f"② 联邦建模完成：{task['code']} AUC={metrics.get('auc')} 漏检率={metrics.get('missRate')}")

# ③ 异常行为检测（智能风控预警 + 自动处置）
detected = client.post("/api/ops/monitoring/detect", headers=headers, json={"limit": 1500}).get_json()["data"]
s = detected["summary"]
print(f"③ 异常检测：扫描 {detected['scanned']} 笔 → 预警 {s['total']} 条"
      f"（高 {s.get('high')} / 中 {s.get('medium')} / 低 {s.get('low')}），涉险 {s['amountAtRisk']/1e4:.1f} 万元")

# ④ 支付智能处理（含故障演练，演示重试与自动补偿）
paid = client.post("/api/ops/payment/process", headers=headers,
                   json={"count": 30, "injectFailureRate": 0.2}).get_json()["data"]
p = paid["summary"]
print(f"④ 支付处理：{p['total']} 笔 | 成功率 {p['successRate']*100:.1f}% | 直通率 {p['straightThroughRate']*100:.1f}%"
      f" | 重试率 {p['retryRate']*100:.1f}% | 补偿率 {p['compensationRate']*100:.1f}% | 风控拦截 {p['blockedCount']} 笔")

# ⑤ 审核批次（AI 初审 + 人工复核 + 一致性评估）
batch = client.post("/api/ops/review/batch", headers=headers, json={"count": 40}).get_json()["data"]
m = batch["metrics"]
print(f"⑤ 审核批次 {batch['batchCode']}：样本 {m['total']} | 核心一致性 {m['agreementRate']*100:.1f}%"
      f" | Kappa {m['kappa']}（{m['kappaLevel']}） | 自动化率 {m['automationRate']*100:.1f}%"
      f" | 漏放 {m['falseNegativeCount']} 误拦 {m['falsePositiveCount']}")

# ⑥ 匿踪查询 + 合规报告（丰富审计脉冲与报告数据）
oq = client.post("/api/engine/oblivious-query", headers=headers,
                 json={"merchantName": "Tehran Petro Trading Co", "taxNo": "IR-88213",
                       "lists": ["OFAC", "UN"], "mode": "oprf"}).get_json()["data"]
print(f"⑥ 匿踪查询：命中 {oq['hit']} {oq['matchedList']} {oq['elapsedMs']}ms")
for report_type in ("GDPR", "FATF"):
    r = client.post("/api/compliance/reports", headers=headers, json={"type": report_type}).get_json()["data"]
    print(f"   合规报告：{r['code']}（{report_type}）")

brain = client.get("/api/brain/overview", headers=headers).get_json()["data"]
print(f"\n大脑展板：{len(brain['regions'])} 个脑区 / {len(brain['flows'])} 条数据通路")
print("  " + " | ".join(f"{k['label']}={k['value']}{k['unit']}" for k in brain["kpis"][:5]))
for item in brain["regions"]:
    if item["id"] in ("core_payment", "core_monitor", "core_review", "core_decision"):
        print("  %-14s 负载 %.0f%%  %s" % (item["name"], item["load"] * 100,
                                          " / ".join(f"{m['label']} {m['value']}{m['unit']}" for m in item["metrics"])))
