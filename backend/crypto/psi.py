# -*- coding: utf-8 -*-
"""隐私求交集（Private Set Intersection, PSI）。

采用 RSA 盲签名 PSI 协议（Meadows 协议），双方仅交换盲化/签名后的哈希值，
不暴露各自集合的原始元素与交集以外的信息。

协议流程（A = 查询方/客户端，B = 清单方/服务端）
-----------------------------------------------
1. B 生成 RSA 密钥 (n, e, d)，公开 (n, e)；
2. A 对集合 X 逐元素计算 h = H(x) mod n，并用随机数 r 盲化：b = h·rᵉ mod n，发送给 B；
3. B 对收到的盲化值签名：s = b^d mod n = h^d·r mod n（B 无法获知 x）；
4. B 同时对自身集合 Y 计算 H(y)^d mod n 并返回给 A；
5. A 去盲：h^d = s·r⁻¹ mod n，与 B 返回的集合求交，得到 X ∩ Y（以哈希形式比较）。

安全边界：B 无法得到 A 的元素，A 只能得到交集大小与交集元素本身（若需仅返回大小，
可在上层只暴露 `intersection_size`，本平台黑名单场景即采用该策略）。
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from math import gcd
from typing import Dict, Iterable, List, Sequence, Tuple

from .paillier import generate_prime, is_probable_prime


def _hash_to_int(value: str, n: int, salt: bytes = b"fedshield-psi") -> int:
    """将元素映射到 Z*ₙ 上的整数（SHA-256 抗碰撞哈希）。"""
    digest = hashlib.sha256(salt + value.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % n


def hash_to_int(value: str, n: int, salt: bytes = b"fedshield-psi") -> int:
    """公开别名：供匿踪查询等模块统一使用同一哈希口径。"""
    return _hash_to_int(value, n, salt)


def _modinv(value: int, modulus: int) -> int:
    return pow(value, -1, modulus)


@dataclass
class RSAPsiKey:
    """RSA 盲签名密钥。"""

    n: int
    e: int
    d: int
    bits: int = 1024

    def to_public_dict(self) -> dict:
        return {"n": str(self.n), "e": str(self.e), "bits": self.bits}


def generate_rsa_key(bits: int = 1024, e: int = 65537) -> RSAPsiKey:
    """生成 RSA 密钥（模数长度 = bits，e 固定为 65537）。"""
    half = bits // 2
    while True:
        p = generate_prime(half)
        q = generate_prime(half)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if gcd(e, phi) != 1:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        d = _modinv(e, phi)
        return RSAPsiKey(n=n, e=e, d=d, bits=bits)


class PSIClient:
    """求交参与方（数据查询侧）：负责盲化与去盲。"""

    def __init__(self, key: RSAPsiKey, salt: bytes = b"fedshield-psi"):
        self.key = key
        self.salt = salt
        self._pending: List[Tuple[int, int, int]] = []  # [(盲化值 b, 随机数 r, 哈希 h)]

    def blind(self, items: Sequence[str]) -> List[int]:
        """对本地集合盲化，返回待签名值列表（内部保留 r 以便去盲）。"""
        blinded: List[int] = []
        self._pending = []
        for item in items:
            h = _hash_to_int(item, self.key.n, self.salt)
            while True:
                r = secrets.randbelow(self.key.n - 2) + 2
                if gcd(r, self.key.n) == 1:
                    break
            b = (h * pow(r, self.key.e, self.key.n)) % self.key.n
            self._pending.append((b, r, h))
            blinded.append(b)
        return blinded

    def unblind(self, signed: Iterable[int]) -> List[int]:
        """校验服务端签名并去盲，得到 H(x)^d mod n（顺序与入参 items 一致）。"""
        signed = list(signed)
        if len(signed) != len(self._pending):
            raise ValueError("签名结果数量与请求不一致，可能存在中间人篡改")
        results = []
        for s, (b, r, _h) in zip(signed, self._pending):
            # 验证 s^e ≡ b (mod n)，确保服务端确实持有私钥且未替换结果
            if pow(s % self.key.n, self.key.e, self.key.n) != b % self.key.n:
                raise ValueError("盲签名校验失败：服务端返回结果不可信")
            results.append((s * _modinv(r, self.key.n)) % self.key.n)
        return results


class PSIServer:
    """求交参与方（监管清单侧）：负责签名与自身集合变换。"""

    def __init__(self, key: RSAPsiKey, salt: bytes = b"fedshield-psi"):
        self.key = key
        self.salt = salt

    def sign(self, blinded_values: Iterable[int]) -> List[int]:
        return [pow(b % self.key.n, self.key.d, self.key.n) for b in blinded_values]

    def transform(self, items: Sequence[str]) -> List[int]:
        return [
            pow(_hash_to_int(item, self.key.n, self.salt), self.key.d, self.key.n)
            for item in items
        ]


def run_psi(left: Sequence[str], right: Sequence[str], key: RSAPsiKey | None = None) -> dict:
    """执行一次完整的隐私求交集，返回交集结果与性能指标。"""
    started = time.perf_counter()
    key = key or generate_rsa_key(768)
    client, server = PSIClient(key), PSIServer(key)

    t0 = time.perf_counter()
    blinded = client.blind(left)
    blind_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    signed = server.sign(blinded)
    sign_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    # 客户端去盲后得到 H(x)^d，与服务端 H(y)^d 集合比对（签名与 items 顺序一一对应）
    client_transformed = client.unblind(signed)
    right_transformed = set(server.transform(right))
    intersection = [
        item
        for item, transformed in zip(left, client_transformed)
        if transformed in right_transformed
    ]
    match_ms = (time.perf_counter() - t0) * 1000

    return {
        "intersection": intersection,
        "intersectionSize": len(intersection),
        "leftSize": len(left),
        "rightSize": len(right),
        "elapsedMs": round((time.perf_counter() - started) * 1000, 2),
        "metrics": {
            "blindMs": round(blind_ms, 2),
            "signMs": round(sign_ms, 2),
            "matchMs": round(match_ms, 2),
            "rsaBits": key.bits,
            "exposedPlaintext": 0,
        },
    }


def hash_psi(left: Sequence[str], right: Sequence[str], salt: str | None = None) -> dict:
    """HMAC 哈希求交（快速模式）：适用于双方已约定同一盐值的场景。

    注意：该模式安全性弱于 RSA 盲签名模式（存在字典攻击面），
    仅用于内网可信节点间的大批量快速比对，平台默认使用 `run_psi`。
    """
    started = time.perf_counter()
    salt_bytes = (salt or "fedshield-psi-fast").encode("utf-8")
    left_map = {hashlib.sha256(salt_bytes + x.encode()).hexdigest(): x for x in left}
    right_set = {hashlib.sha256(salt_bytes + y.encode()).hexdigest() for y in right}
    intersection = [left_map[h] for h in left_map.keys() & right_set]
    return {
        "intersection": intersection,
        "intersectionSize": len(intersection),
        "leftSize": len(left),
        "rightSize": len(right),
        "elapsedMs": round((time.perf_counter() - started) * 1000, 2),
        "mode": "hash",
    }
