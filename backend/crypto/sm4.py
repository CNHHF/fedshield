# -*- coding: utf-8 -*-
"""国密 SM4 分组密码（GB/T 32907-2016）实现。

设计说明
--------
- 优先使用 PyCryptodome 的硬件/优化实现（`Crypto.Cipher.SM4`）；
- 若运行环境未安装 PyCryptodome，则自动降级为内置的纯 Python 实现，
  保证「国产密码算法」能力在任何环境下可用（本项目所有节点均可自检）；
- 工作模式：CBC + PKCS#7 填充；完整性：Encrypt-then-MAC（HMAC-SHA256），
  与《信息安全技术 密码应用基本要求》中「先加密后认证」的要求一致。

纯 Python 分支已通过 GB/T 32907-2016 标准测试向量校验（见 tests/test_crypto.py）。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from typing import Tuple

try:  # pragma: no cover - 取决于运行环境
    from Crypto.Cipher import SM4 as _PYCRYPTODOME_SM4  # type: ignore

    HAS_PYCRYPTODOME_SM4 = True
except Exception:  # pragma: no cover
    _PYCRYPTODOME_SM4 = None
    HAS_PYCRYPTODOME_SM4 = False


# --------------------------------------------------------------------------
# 纯 Python SM4 实现
# --------------------------------------------------------------------------

SBOX = bytes.fromhex(
    "d690e9fecce13db716b614c228fb2c05"
    "2b679a762abe04c3aa44132649860699"
    "9c4250f491ef987a33540b43edcfac62"
    "e4b31ca9c908e89580df94fa758f3fa6"
    "4707a7fcf37317ba83593c19e6854fa8"
    "686b81b27164da8bf8eb0f4b70569d35"
    "1e240e5e6358d1a225227c3b01217887"
    "d40046579fd327524c3602e7a0c4c89e"
    "eabf8ad240c738b5a3f7f2cef96115a1"
    "e0ae5da49b341a55ad933230f58cb1e3"
    "1df6e22e8266ca60c02923ab0d534e6f"
    "d5db3745defd8e2f03ff6a726d6c5b51"
    "8d1baf92bbddbc7f11d95c411f105ad8"
    "0ac13188a5cd7bbd2d74d012b8e5b4b0"
    "8969974a0c96777e65b9f109c56ec684"
    "18f07dec3adc4d2079ee5f3ed7cb3948"
)

FK = (0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC)


def _build_ck() -> Tuple[int, ...]:
    """固定参数 CK_i = ck_{i,0}‖ck_{i,1}‖ck_{i,2}‖ck_{i,3}，其中 ck_{i,j} = (4i+j)·7 mod 256。"""
    words = []
    for i in range(32):
        word = 0
        for j in range(4):
            word |= ((4 * i + j) * 7 % 256) << (24 - 8 * j)
        words.append(word)
    return tuple(words)


_CK: Tuple[int, ...] = _build_ck()


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _tau(a: int) -> int:
    return (
        (SBOX[(a >> 24) & 0xFF] << 24)
        | (SBOX[(a >> 16) & 0xFF] << 16)
        | (SBOX[(a >> 8) & 0xFF] << 8)
        | SBOX[a & 0xFF]
    )


def _l(b: int) -> int:
    return b ^ _rotl(b, 2) ^ _rotl(b, 10) ^ _rotl(b, 18) ^ _rotl(b, 24)


def _l_key(b: int) -> int:
    return b ^ _rotl(b, 13) ^ _rotl(b, 23)


def _round_keys(key: bytes) -> Tuple[int, ...]:
    if len(key) != 16:
        raise ValueError("SM4 密钥长度必须为 16 字节")
    mk = struct.unpack(">4I", key)
    k = [mk[i] ^ FK[i] for i in range(4)]
    rk = []
    for i in range(32):
        t = k[i + 1] ^ k[i + 2] ^ k[i + 3] ^ _CK[i]
        k.append(k[i] ^ _l_key(_tau(t)))
        rk.append(k[i + 4])
    return tuple(rk)


def _crypt_block(block: bytes, rk: Tuple[int, ...]) -> bytes:
    x = list(struct.unpack(">4I", block))
    for i in range(32):
        t = x[i + 1] ^ x[i + 2] ^ x[i + 3] ^ rk[i]
        x.append(x[i] ^ _l(_tau(t)))
    return struct.pack(">4I", x[35], x[34], x[33], x[32])


def _pure_encrypt_block(key: bytes, block: bytes) -> bytes:
    return _crypt_block(block, _round_keys(key))


def _pure_decrypt_block(key: bytes, block: bytes) -> bytes:
    return _crypt_block(block, tuple(reversed(_round_keys(key))))


# --------------------------------------------------------------------------
# 对外接口：CBC + PKCS#7 + HMAC-SHA256
# --------------------------------------------------------------------------

BLOCK_SIZE = 16


def _pkcs7_pad(data: bytes) -> bytes:
    pad = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data or len(data) % BLOCK_SIZE:
        raise ValueError("SM4 密文长度非法")
    pad = data[-1]
    if pad < 1 or pad > BLOCK_SIZE or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("SM4 填充校验失败")
    return data[:-pad]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _cbc_encrypt_pure(key: bytes, iv: bytes, data: bytes) -> bytes:
    out = bytearray()
    prev = iv
    for i in range(0, len(data), BLOCK_SIZE):
        block = _xor(data[i : i + BLOCK_SIZE], prev)
        prev = _pure_encrypt_block(key, block)
        out += prev
    return bytes(out)


def _cbc_decrypt_pure(key: bytes, iv: bytes, data: bytes) -> bytes:
    out = bytearray()
    prev = iv
    for i in range(0, len(data), BLOCK_SIZE):
        block = data[i : i + BLOCK_SIZE]
        out += _xor(_pure_decrypt_block(key, block), prev)
        prev = block
    return bytes(out)


def _cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if HAS_PYCRYPTODOME_SM4:
        from Crypto.Util.Padding import pad

        cipher = _PYCRYPTODOME_SM4.new(key, _PYCRYPTODOME_SM4.MODE_CBC, iv)
        return cipher.encrypt(pad(data, BLOCK_SIZE))
    return _cbc_encrypt_pure(key, iv, _pkcs7_pad(data))


def _cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    if HAS_PYCRYPTODOME_SM4:
        from Crypto.Util.Padding import unpad

        cipher = _PYCRYPTODOME_SM4.new(key, _PYCRYPTODOME_SM4.MODE_CBC, iv)
        return unpad(cipher.decrypt(data), BLOCK_SIZE)
    return _pkcs7_unpad(_cbc_decrypt_pure(key, iv, data))


def derive_key(passphrase: str, salt: bytes | None = None, length: int = 16) -> Tuple[bytes, bytes]:
    """由口令派生 SM4 密钥（PBKDF2-HMAC-SHA256，100000 轮）。"""
    salt = salt or os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 100_000, dklen=length)
    return key, salt


def _mac(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    mac_key = hashlib.sha256(b"sm4-mac" + key).digest()
    return hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()


def encrypt(key: bytes, plaintext: bytes | str) -> str:
    """SM4-CBC 加密，返回 `iv||ciphertext||hmac` 的十六进制字符串。"""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    iv = os.urandom(BLOCK_SIZE)
    ciphertext = _cbc_encrypt(key, iv, plaintext)
    return (iv + ciphertext + _mac(key, iv, ciphertext)).hex()


def decrypt(key: bytes, token: str) -> bytes:
    """SM4-CBC 解密并校验 HMAC（Encrypt-then-MAC）。"""
    raw = bytes.fromhex(token)
    if len(raw) < BLOCK_SIZE * 2 + 32:
        raise ValueError("SM4 密文长度非法")
    iv, ciphertext, tag = raw[:BLOCK_SIZE], raw[BLOCK_SIZE:-32], raw[-32:]
    if not hmac.compare_digest(_mac(key, iv, ciphertext), tag):
        raise ValueError("SM4 完整性校验失败：密文可能被篡改")
    return _cbc_decrypt(key, iv, ciphertext)


def decrypt_text(key: bytes, token: str) -> str:
    return decrypt(key, token).decode("utf-8")


def encrypt_block_vector(key: bytes, block: bytes) -> bytes:
    """单分组 ECB 加密，仅用于标准测试向量验证。"""
    return _pure_encrypt_block(key, block)


def decrypt_block_vector(key: bytes, block: bytes) -> bytes:
    """单分组 ECB 解密，仅用于标准测试向量验证。"""
    return _pure_decrypt_block(key, block)
