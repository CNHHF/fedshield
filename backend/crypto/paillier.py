# -*- coding: utf-8 -*-
"""Paillier 半同态加密（加法同态），用于密文域比对与密文域聚合。

数学基础
--------
- 密钥生成：选取大素数 p、q，令 n = p·q，λ = lcm(p-1, q-1)，μ = λ⁻¹ mod n；
  取生成元 g = n + 1（简化形式，此时 L(u) = (u-1)/n）；
- 加密：c = gᵐ · rⁿ mod n²，其中 r ∈ Z*ₙ 为随机数（概率加密，同一明文两次密文不同）；
- 解密：m = L(c^λ mod n²) · μ mod n；
- 同态性质：
    · 密文加法   E(m₁)·E(m₂) = E(m₁ + m₂)
    · 明文标量乘 E(m)^k       = E(k · m)
    · 密文重随机 E(m)·rⁿ      = E(m) 的新鲜密文

工程说明
--------
本文件为纯 Python 实现（仅依赖标准库），保证「国产/离线节点」也能部署；
生产环境可平滑替换为 gmpy2 或 JNI 调用硬件密码卡（接口保持一致）。
密钥默认 1024 位，可用 512 位以便本地快速自测。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from math import gcd
from typing import Iterable, List, Sequence

_SMALL_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149, 151,
    157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233,
    239, 241, 251, 257, 263, 269, 271, 277, 281, 283, 293, 307, 311, 313, 317,
    331, 337, 347, 349, 353, 359, 367, 373, 379, 383, 389, 397, 401, 409, 419,
    421, 431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491, 499, 503,
    509, 521, 523, 541,
]


def is_probable_prime(n: int, rounds: int = 32) -> bool:
    """Miller-Rabin 素性检测（错误概率 < 4⁻³²）。"""
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_prime(bits: int) -> int:
    """生成指定位数的大素数（保证最高位与最低位为 1）。"""
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate):
            return candidate


def _lcm(a: int, b: int) -> int:
    return a // gcd(a, b) * b


@dataclass(frozen=True)
class PaillierPublicKey:
    """公钥 (n, g)，可安全分发至各跨境节点。"""

    n: int
    g: int
    bits: int = 1024

    @property
    def n_square(self) -> int:
        return self.n * self.n

    def to_dict(self) -> dict:
        return {"n": _int_to_b64(self.n), "g": _int_to_b64(self.g), "bits": self.bits}

    @classmethod
    def from_dict(cls, data: dict) -> "PaillierPublicKey":
        return cls(n=_b64_to_int(data["n"]), g=_b64_to_int(data["g"]), bits=data.get("bits", 1024))


@dataclass(frozen=True)
class PaillierPrivateKey:
    """私钥 (λ, μ)，仅留存于数据所属地区节点，不出域。

    额外保存 p、q 以便使用中国剩余定理（CRT）加速解密：
    黑名单匿踪查询需要对整份清单逐项解密比对，CRT 可将解密耗时降低约 3~4 倍，
    是达成「查询响应 ≤300ms」指标的关键优化之一。
    """

    lam: int
    mu: int
    public_key: PaillierPublicKey
    p: int | None = None
    q: int | None = None

    def to_dict(self) -> dict:
        return {
            "lam": _int_to_b64(self.lam),
            "mu": _int_to_b64(self.mu),
            "p": _int_to_b64(self.p) if self.p else None,
            "q": _int_to_b64(self.q) if self.q else None,
            "publicKey": self.public_key.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PaillierPrivateKey":
        return cls(
            lam=_b64_to_int(data["lam"]),
            mu=_b64_to_int(data["mu"]),
            public_key=PaillierPublicKey.from_dict(data["publicKey"]),
            p=_b64_to_int(data["p"]) if data.get("p") else None,
            q=_b64_to_int(data["q"]) if data.get("q") else None,
        )


def generate_keypair(bits: int = 1024) -> tuple[PaillierPublicKey, PaillierPrivateKey]:
    """生成 Paillier 密钥对；bits 为模数 n 的位数。"""
    if bits < 256 or bits % 2:
        raise ValueError("Paillier 模数位数需为不小于 256 的偶数")
    while True:
        p = generate_prime(bits // 2)
        q = generate_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        g = n + 1
        lam = _lcm(p - 1, q - 1)
        if gcd(lam, n) != 1:
            continue
        mu = pow(lam, -1, n)
        public_key = PaillierPublicKey(n=n, g=g, bits=bits)
        return public_key, PaillierPrivateKey(lam=lam, mu=mu, public_key=public_key, p=p, q=q)


class PaillierCipher:
    """面向业务的加解密/同态运算门面，密文统一用 Base64 字符串传输。"""

    def __init__(self, public_key: PaillierPublicKey, private_key: PaillierPrivateKey | None = None):
        self.public_key = public_key
        self.private_key = private_key

    # ---------------- 加解密 ----------------

    def encrypt(self, message: int) -> int:
        """加密整数 m（自动对 n 取模，负数以 n - |m| 表示）。"""
        n, n2 = self.public_key.n, self.public_key.n_square
        m = message % n
        while True:
            r = secrets.randbelow(n - 1) + 1
            if gcd(r, n) == 1:
                break
        return (pow(self.public_key.g, m, n2) * pow(r, n, n2)) % n2

    def decrypt(self, ciphertext: int) -> int:
        """解密；返回 [0, n) 区间内的整数。

        当私钥包含 p、q 时走 CRT 快速路径（约 3~4 倍加速）。
        """
        if self.private_key is None:
            raise ValueError("缺少私钥：仅数据所属节点可解密")
        n, n2 = self.public_key.n, self.public_key.n_square
        if self.private_key.p and self.private_key.q:
            return self._decrypt_crt(ciphertext)
        u = pow(ciphertext % n2, self.private_key.lam, n2)
        return ((u - 1) // n * self.private_key.mu) % n

    def _decrypt_crt(self, ciphertext: int) -> int:
        """基于中国剩余定理的 Paillier 解密。"""
        p, q = self.private_key.p, self.private_key.q
        n, g = self.public_key.n, self.public_key.g
        p2, q2 = p * p, q * q
        c = ciphertext % (n * n)

        cp = pow(c % p2, p - 1, p2)
        mp = ((cp - 1) // p * pow((pow(g % p2, p - 1, p2) - 1) // p, -1, p)) % p

        cq = pow(c % q2, q - 1, q2)
        mq = ((cq - 1) // q * pow((pow(g % q2, q - 1, q2) - 1) // q, -1, q)) % q

        return (mp + p * ((mq - mp) * pow(p, -1, q) % q)) % n

    def decrypt_signed(self, ciphertext: int) -> int:
        """解密并还原为带符号整数（用于差值比对场景）。"""
        n = self.public_key.n
        value = self.decrypt(ciphertext)
        return value - n if value > n // 2 else value

    # ---------------- 同态运算 ----------------

    def add(self, *ciphertexts: int) -> int:
        """密文加法：E(m₁)·E(m₂)·… = E(m₁+m₂+…)"""
        acc = 1
        n2 = self.public_key.n_square
        for c in ciphertexts:
            acc = (acc * c) % n2
        return acc

    def add_plain(self, ciphertext: int, scalar: int) -> int:
        """密文与明文相加：E(m)·gᵏ = E(m + k)"""
        n, n2 = self.public_key.n, self.public_key.n_square
        return (ciphertext * pow(self.public_key.g, scalar % n, n2)) % n2

    def scalar_mul(self, ciphertext: int, scalar: int) -> int:
        """明文标量乘：E(m)^k = E(k·m)"""
        n2 = self.public_key.n_square
        return pow(ciphertext % n2, scalar, n2)

    def randomize(self, ciphertext: int) -> int:
        """密文重随机化，得到同一明文的另一个合法密文。"""
        n, n2 = self.public_key.n, self.public_key.n_square
        while True:
            r = secrets.randbelow(n - 1) + 1
            if gcd(r, n) == 1:
                break
        return (ciphertext * pow(r, n, n2)) % n2

    def reencrypt_zero(self) -> int:
        """生成 E(0) 的新鲜密文。"""
        return self.encrypt(0)

    # ---------------- 向量便捷方法 ----------------

    def encrypt_vector(self, values: Sequence[float], scale: int = 10 ** 6) -> List[int]:
        """浮点向量定点化后逐个加密（scale 为定点精度，默认 1e-6）。"""
        return [self.encrypt(int(round(v * scale))) for v in values]

    def decrypt_vector(self, ciphertexts: Iterable[int], scale: int = 10 ** 6) -> List[float]:
        return [self.decrypt(c) / scale for c in ciphertexts]

    def serialize(self, ciphertext: int) -> str:
        return _int_to_b64(ciphertext)

    def deserialize(self, token: str) -> int:
        return _b64_to_int(token)


# --------------------------------------------------------------------------
# 编码工具
# --------------------------------------------------------------------------


def _int_to_b64(value: int) -> str:
    length = max(1, (value.bit_length() + 7) // 8)
    return base64.b64encode(value.to_bytes(length, "big")).decode("ascii")


def _b64_to_int(token: str) -> int:
    return int.from_bytes(base64.b64decode(token), "big")


def digest_of(ciphertext: int) -> str:
    """密文摘要，用于区块链存证（不暴露密文本身）。"""
    return hashlib.sha256(str(ciphertext).encode("ascii")).hexdigest()[:32]


# --------------------------------------------------------------------------
# 默认密钥对（进程内单例 + 本地文件缓存，避免每次请求重新生成）
# --------------------------------------------------------------------------

_DEFAULT: tuple[PaillierPublicKey, PaillierPrivateKey] | None = None


def get_default_keys(cache_dir: str | None = None, bits: int = 1024) -> tuple[PaillierPublicKey, PaillierPrivateKey]:
    """获取默认密钥对；优先从缓存文件读取，保证服务重启后密文仍可解密。"""
    global _DEFAULT
    if _DEFAULT is not None:
        return _DEFAULT

    path = os.path.join(cache_dir or os.path.join(os.getcwd(), "instance"), "paillier_keys.json")
    if cache_dir is None and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            private_key = PaillierPrivateKey.from_dict(data)
            _DEFAULT = (private_key.public_key, private_key)
            return _DEFAULT
        except Exception:
            pass

    public_key, private_key = generate_keypair(bits)
    _DEFAULT = (public_key, private_key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(private_key.to_dict(), fp)
    except Exception:
        pass
    return _DEFAULT


def default_cipher() -> PaillierCipher:
    public_key, private_key = get_default_keys()
    return PaillierCipher(public_key, private_key)
