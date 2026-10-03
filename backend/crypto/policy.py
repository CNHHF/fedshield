# -*- coding: utf-8 -*-
"""分级加密策略（数据接入层 / 安全传输层的统一出口）。

严格对应文档中的差异化加密策略：

| 级别 | 数据示例 | 加密策略 |
| --- | --- | --- |
| P1 | 身份证号、银行卡号、收付款方实名信息 | 国密 SM4-CBC+HMAC 加密数据本体，密钥再经 Paillier 同态加密保护（双重加密） |
| P2 | 交易金额、商户税号 | 差分隐私（Laplace）加噪 + AES-256-GCM |
| P3 | 商品类别、币种、地区编码 | AES-256-GCM |

对外提供三件事：
1. `encrypt_payload(level, payload)`：把业务字典封装为可跨节点传输的密文信封；
2. `decrypt_payload(envelope)`：仅授权节点可解密（P1 需持有 Paillier 私钥）；
3. `protect_vector(level, values)`：数值向量的分级保护，供联邦学习/联合统计复用。
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, Iterable, List, Sequence

from . import aes_gcm, dp, sm4
from .paillier import PaillierCipher, default_cipher

LEVEL_P1, LEVEL_P2, LEVEL_P3 = "P1", "P2", "P3"

LEVEL_META: Dict[str, dict] = {
    LEVEL_P1: {
        "level": "P1",
        "name": "高敏感数据",
        "algorithm": "国密SM4 + Paillier同态加密",
        "cipher": "SM4-CBC+HMAC-SHA256 / Paillier-1024",
        "keyManagement": "数据密钥由 Paillier 公钥加密后随密文传输，私钥不出地区节点",
        "examples": ["身份证号", "银行卡号", "收付款方实名信息", "生物特征"],
        "transport": "TLS1.3 双向认证专用通道",
    },
    LEVEL_P2: {
        "level": "P2",
        "name": "中敏感数据",
        "algorithm": "差分隐私 + AES-256-GCM",
        "cipher": "Laplace(Δf/ε) / AES-256-GCM",
        "keyManagement": "主密钥由机构 KMS 托管，按任务周期轮换",
        "examples": ["交易金额", "商户税号", "经营地址", "结算账号后四位"],
        "transport": "TLS1.3 专用通道",
    },
    LEVEL_P3: {
        "level": "P3",
        "name": "低敏感数据",
        "algorithm": "AES-256-GCM",
        "cipher": "AES-256-GCM",
        "keyManagement": "主密钥由机构 KMS 托管",
        "examples": ["商品类别", "币种", "地区编码", "交易时间戳"],
        "transport": "TLS1.3 专用通道",
    },
}

_MASTER_KEY: bytes | None = None


def master_key() -> bytes:
    """平台主密钥（由环境变量 FEDSHIELD_MASTER_KEY 派生，未配置时使用开发默认值）。"""
    global _MASTER_KEY
    if _MASTER_KEY is None:
        seed = os.getenv("FEDSHIELD_MASTER_KEY", "fedshield-dev-master-key")
        _MASTER_KEY = hashlib.pbkdf2_hmac(
            "sha256", seed.encode("utf-8"), b"fedshield-kms-v1", 120_000, dklen=32
        )
    return _MASTER_KEY


def describe(level: str) -> dict:
    """返回某级别的加密策略说明（前端「加密级别」下拉展示）。"""
    return LEVEL_META.get(level.upper(), LEVEL_META[LEVEL_P3])


def describe_all() -> List[dict]:
    return list(LEVEL_META.values())


def _key_envelope(cipher: PaillierCipher, data_key: bytes) -> dict:
    """用 Paillier 公钥加密 SM4 数据密钥（密钥封装）。"""
    key_int = int.from_bytes(data_key, "big")
    return {
        "algorithm": "Paillier",
        "keyBits": cipher.public_key.bits,
        "n": str(cipher.public_key.n),
        "encryptedKey": cipher.serialize(cipher.encrypt(key_int)),
    }


def _open_key_envelope(cipher: PaillierCipher, envelope: dict) -> bytes:
    key_int = cipher.decrypt(cipher.deserialize(envelope["encryptedKey"]))
    length = max(16, (key_int.bit_length() + 7) // 8)
    return key_int.to_bytes(length, "big")[-16:]


def encrypt_payload(level: str, payload: dict, epsilon: float = 1.0,
                    sensitivity: float = 1.0, noisy_fields: Sequence[str] | None = None) -> dict:
    """按数据级别加密业务负载，返回跨节点可传输的密文信封。

    参数
    ----
    level: P1 / P2 / P3
    payload: 业务字典
    epsilon: P2 级别的差分隐私预算
    sensitivity: P2 级别数值字段的全局敏感度
    noisy_fields: 需要加噪的数值字段名（为空则对所有数值字段加噪）
    """
    level = level.upper()
    body = dict(payload)
    noise_meta: List[dict] = []

    if level == LEVEL_P2:
        for key, value in list(body.items()):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if noisy_fields and key not in noisy_fields:
                continue
            noisy = dp.laplace_mechanism(float(value), sensitivity, epsilon)
            noise_meta.append({"field": key, "epsilon": epsilon, "noise": round(noisy - float(value), 6)})
            body[key] = round(noisy, 6)

    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    if level == LEVEL_P1:
        data_key = os.urandom(16)
        token = sm4.encrypt(data_key, plaintext)
        cipher = default_cipher()
        return {
            "level": level,
            "algorithm": LEVEL_META[level]["algorithm"],
            "cipher": "SM4-CBC+HMAC",
            "ciphertext": token,
            "keyEnvelope": _key_envelope(cipher, data_key),
            "digest": hashlib.sha256(token.encode("ascii")).hexdigest()[:32],
            "length": len(plaintext),
            "noise": noise_meta,
            "createdAt": _now(),
        }

    token = aes_gcm.encrypt(master_key(), plaintext)
    return {
        "level": level,
        "algorithm": LEVEL_META[level]["algorithm"],
        "cipher": "AES-256-GCM",
        "ciphertext": token,
        "keyEnvelope": {"algorithm": "KMS", "keyId": "fedshield-master-v1"},
        "digest": hashlib.sha256(token.encode("ascii")).hexdigest()[:32],
        "length": len(plaintext),
        "noise": noise_meta,
        "createdAt": _now(),
    }


def decrypt_payload(envelope: dict) -> dict:
    """解密密文信封（P1 需要 Paillier 私钥）。"""
    level = str(envelope.get("level", LEVEL_P3)).upper()
    if level == LEVEL_P1:
        cipher = default_cipher()
        data_key = _open_key_envelope(cipher, envelope["keyEnvelope"])
        plaintext = sm4.decrypt(data_key, envelope["ciphertext"])
    else:
        plaintext = aes_gcm.decrypt(master_key(), envelope["ciphertext"])
    return json.loads(plaintext.decode("utf-8"))


def protect_vector(level: str, values: Iterable[float], epsilon: float = 1.0,
                   sensitivity: float = 1.0, scale: int = 10 ** 6) -> dict:
    """数值向量分级保护：P1 走 Paillier 密文域计算，P2 走差分隐私，P3 走对称加密。"""
    level = level.upper()
    values = [float(v) for v in values]
    if level == LEVEL_P1:
        cipher = default_cipher()
        ciphertexts = [cipher.serialize(c) for c in cipher.encrypt_vector(values, scale)]
        return {
            "level": level,
            "mode": "paillier",
            "ciphertexts": ciphertexts,
            "scale": scale,
            "count": len(values),
        }
    if level == LEVEL_P2:
        noisy = dp.perturb_vector(values, sensitivity, epsilon)
        return {
            "level": level,
            "mode": "dp+aes",
            "ciphertext": aes_gcm.encrypt(master_key(), json.dumps(noisy)),
            "count": len(noisy),
            "epsilon": epsilon,
        }
    return {
        "level": level,
        "mode": "aes",
        "ciphertext": aes_gcm.encrypt(master_key(), json.dumps(values)),
        "count": len(values),
    }


def open_vector(protected: dict) -> List[float]:
    """还原 `protect_vector` 的结果（P1 需要 Paillier 私钥）。"""
    mode = protected.get("mode")
    if mode == "paillier":
        cipher = default_cipher()
        ciphertexts = [cipher.deserialize(token) for token in protected["ciphertexts"]]
        return cipher.decrypt_vector(ciphertexts, protected.get("scale", 10 ** 6))
    if mode in ("dp+aes", "aes"):
        return json.loads(aes_gcm.decrypt(master_key(), protected["ciphertext"]).decode("utf-8"))
    raise ValueError(f"未知的保护模式：{mode}")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
