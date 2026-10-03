# -*- coding: utf-8 -*-
"""AES-256-GCM 认证加密（国际算法通道）。

对应文档：
- P2 级数据（交易金额、商户税号等）采用「差分隐私 + 对称加密」；
- P3 级数据（商品类别、币种等）仅采用对称加密；
- 采用 AES-256-GCM 保证机密性与完整性（AEAD），密钥由口令经 PBKDF2 派生。

依赖 PyCryptodome（requirements.txt 已固定版本）。所有密文以
`v1:base64(nonce|tag|ciphertext)` 形式输出，便于跨节点传输与版本演进。
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Tuple

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

VERSION = "v1"
NONCE_SIZE = 12  # GCM 推荐 96 位随机 nonce
KEY_SIZE = 32  # AES-256
TAG_SIZE = 16


def derive_key(passphrase: str, salt: bytes | None = None) -> Tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256 派生 256 位密钥，返回 (key, salt)。"""
    salt = salt or os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 150_000, dklen=KEY_SIZE)
    return key, salt


def generate_key() -> bytes:
    """生成随机 256 位数据密钥（用于节点间会话密钥协商）。"""
    return get_random_bytes(KEY_SIZE)


def encrypt(key: bytes, plaintext: bytes | str, aad: bytes | None = None) -> str:
    """AES-256-GCM 加密，返回带版本前缀的 Base64 字符串。"""
    if len(key) != KEY_SIZE:
        raise ValueError("AES-256 密钥长度必须为 32 字节")
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = get_random_bytes(NONCE_SIZE)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
    if aad:
        cipher.update(aad)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return f"{VERSION}:" + base64.b64encode(nonce + tag + ciphertext).decode("ascii")


def decrypt(key: bytes, token: str, aad: bytes | None = None) -> bytes:
    """AES-256-GCM 解密并校验认证标签，篡改会抛 ValueError。"""
    if token.startswith(VERSION + ":"):
        token = token[len(VERSION) + 1 :]
    raw = base64.b64decode(token)
    if len(raw) < NONCE_SIZE + TAG_SIZE:
        raise ValueError("AES-GCM 密文长度非法")
    nonce, tag, ciphertext = (
        raw[:NONCE_SIZE],
        raw[NONCE_SIZE : NONCE_SIZE + TAG_SIZE],
        raw[NONCE_SIZE + TAG_SIZE :],
    )
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
    if aad:
        cipher.update(aad)
    try:
        return cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as exc:  # pragma: no cover - 取决于输入
        raise ValueError("AES-GCM 完整性校验失败：密文或附加数据被篡改") from exc


def decrypt_text(key: bytes, token: str, aad: bytes | None = None) -> str:
    return decrypt(key, token, aad).decode("utf-8")


def wrap_key(wrapping_key: bytes, data_key: bytes) -> str:
    """密钥封装：用主密钥加密数据密钥（用于分级加密中的密钥保护）。"""
    return encrypt(wrapping_key, data_key)


def unwrap_key(wrapping_key: bytes, token: str) -> bytes:
    return decrypt(wrapping_key, token)
