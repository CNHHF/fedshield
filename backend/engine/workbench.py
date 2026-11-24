"""Field protection and screening dispatch.

Production UCI orders use a real-data Isolation Forest. The legacy labelled
synthetic model remains only for isolated test fixtures and historical context.
"""
from functools import lru_cache
import copy
import hashlib
import math
import time

import numpy as np

from .federated import auc_score
from ..crypto import policy, vault

STAGES = [
    ("classify", "字段分级"), ("protect", "加密与加噪"),
    ("compliance", "跨境合规"), ("risk", "智能初筛"), ("audit", "结果存证"),
]
FIELDS = {
    "datasetId": ("数据集标识", "P3"), "invoiceNo": ("原始发票号", "P3"),
    "customerId": ("原始匿名客户号", "P1"), "customerCountry": ("客户国家", "P3"),
    "lineCount": ("明细数", "P2"), "quantity": ("商品件数", "P2"),
    "merchantCode": ("商户标识", "P1"), "account": ("结算账户", "P1"),
    "amount": ("交易金额", "P2"), "counterparties": ("交易对手数", "P2"),
    "code": ("交易编号", "P3"), "currency": ("币种", "P3"),
    "region": ("来源地区", "P3"), "destRegion": ("目的地区", "P3"),
    "category": ("商品类别", "P3"), "occurredAt": ("交易时间", "P3"),
}


def encrypt_record(level, fields):
    if level == "P1":
        return policy.encrypt_payload(level, fields)
    token, length = vault.encrypt(fields)
    return {"level": level, "cipher": "AES-256-GCM", "ciphertext": token,
        "keyEnvelope": {"algorithm": "local-vault", "keyId": "workbench-v1"},
        "digest": hashlib.sha256(token.encode("ascii")).hexdigest()[:32], "length": length}


def decrypt_record(envelope):
    if envelope.get("keyEnvelope", {}).get("keyId") == "workbench-v1":
        return vault.decrypt(envelope["ciphertext"])
    return policy.decrypt_payload(envelope)


def features(row):
    hour = int(str(row.get("occurredAt", "2026-01-01 12:00:00"))[11:13] or 12)
    return [math.log1p(float(row["amount"])) / 14,
            min(float(row.get("counterparties", 1)), 50) / 50,
            float(row.get("destRegion") in ("ME", "AF")), float(hour < 6)]


@lru_cache(maxsize=1)
def model():
    rng = np.random.default_rng(20261105)
    x = rng.uniform(0, 1, (2400, 4))
    x[:, 2:] = (x[:, 2:] > .7).astype(float)
    probability = 1 / (1 + np.exp(-(x @ np.array([5., 2., 2.2, 1.1]) - 5.7)))
    y = (rng.random(len(x)) < probability).astype(float)
    train, test = x[:1800], x[1800:]
    w, b = np.zeros(4), 0.
    for _ in range(650):
        p = 1 / (1 + np.exp(-(train @ w + b)))
        w -= .25 * (train.T @ (p-y[:1800]) / len(train) + .002*w)
        b -= .25 * float(np.mean(p-y[:1800]))
    pred = 1 / (1 + np.exp(-(test @ w + b)))
    return w, b, {"name": "交易风险逻辑回归 v1", "trainingRows": 1800, "validationRows": 600,
        "validationAuc": round(float(auc_score(y[1800:], pred)), 4),
        "features": ["交易金额（对数）", "交易对手数", "目的地分组", "凌晨交易"],
        "scope": "固定种子的仿真样本训练与留出验证；非真实业务准确率"}


def score(row, compliance_passed):
    if row.get('datasetId')=='uci-online-retail-352':
        from .public_risk import score as real_score
        return real_score(row,compliance_passed)
    from flask import has_app_context,current_app
    if has_app_context() and not current_app.testing:
        return {'code':row['code'],'riskScore':None,'confidence':None,'scoreKind':'unavailable',
            'decision':'manual' if compliance_passed else 'blocked','reason':'该导入来源尚未配置模型，需人工核查；未使用合成标签模型','factors':[]}
    w, b, meta = model()
    x = np.array(features(row))
    p = float(1 / (1 + np.exp(-(x @ w + b))))
    confidence = max(p, 1-p)
    if not compliance_passed:
        decision, reason = "blocked", "合规要件未满足，阻断后续流转"
    elif confidence < .8:
        decision, reason = "manual", "模型置信度低于 80%，进入人工复核"
    else:
        decision = "reject" if p >= .5 else "approve"
        reason = "风险概率达到自动拒绝阈值" if decision == "reject" else "风险概率低于自动通过阈值"
    contributions = x * w
    order = np.argsort(contributions)[::-1][:3]
    return {"code": row["code"], "riskScore": round(p, 5), "confidence": round(confidence, 5),
        "decision": decision, "reason": reason,
        "factors": [{"name": meta["features"][i], "contribution": round(float(contributions[i]), 3)} for i in order]}


def tamper_experiment(envelope):
    """Flip an authenticated ciphertext byte on a copy; never change the vault."""
    import base64
    original = decrypt_record(envelope)
    damaged = copy.deepcopy(envelope)
    token = damaged["ciphertext"]
    prefix = "v1:" if token.startswith("v1:") else ""
    raw = bytearray(base64.b64decode(token[len(prefix):]))
    raw[-1] ^= 1
    damaged["ciphertext"] = prefix + base64.b64encode(raw).decode("ascii")
    started = time.perf_counter()
    detected = False
    try:
        decrypt_record(damaged)
    except ValueError:
        detected = True
    return {"kind": "tamper", "title": "传输密文篡改", "detected": detected,
        "elapsedMs": round((time.perf_counter()-started)*1000, 3),
        "originalIntact": decrypt_record(envelope) == original,
        "beforeHash": hashlib.sha256(token.encode()).hexdigest(),
        "afterHash": hashlib.sha256(damaged["ciphertext"].encode()).hexdigest(),
        "checks": [{"name": "无认证的明文传输", "outcome": "被修改后无认证标签可校验", "safe": False},
                   {"name": envelope["cipher"], "outcome": "拒绝解密" if detected else "未检出", "safe": detected}],
        "scope": "单次本地认证加密篡改试验，不代表抵御全部网络攻击"}


def poisoning_experiment():
    """Fixed synthetic federated updates: compare mean and coordinate median.

    This isolates aggregation robustness, not differential privacy; DP/encryption
    alone do not prevent a malicious node from sending a poisoned update.
    """
    rng = np.random.default_rng(16)
    clean = rng.normal(0, .15, (5, 12))
    poisoned = clean.copy()
    poisoned[0] += 8
    target = clean.mean(axis=0)
    normal = poisoned.mean(axis=0)
    robust = np.median(poisoned, axis=0)
    mean_error = float(np.linalg.norm(normal-target))
    median_error = float(np.linalg.norm(robust-target))
    return {"kind": "poisoning", "title": "单节点模型更新投毒", "nodes": 5, "maliciousNodes": 1,
        "meanDeviation": round(mean_error, 5), "medianDeviation": round(median_error, 5),
        "improvement": round(1-median_error/mean_error, 5),
        "updates": [{"node": f"NODE-{i+1}", "norm": round(float(np.linalg.norm(v)), 4), "malicious": i == 0}
                    for i, v in enumerate(poisoned)],
        "scope": "独立的固定合成更新对照，不是生产联邦训练防投毒能力；加密与差分隐私本身不防投毒"}
