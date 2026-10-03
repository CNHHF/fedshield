# -*- coding: utf-8 -*-
"""安全工具：口令散列、JWT 签发/校验、日志防篡改签名。"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .response import ApiError


# ---------------------------------------------------------------------------
# 口令
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """PBKDF2-SHA256 口令散列（werkzeug 默认 60 万轮）。"""
    return generate_password_hash(password, method="pbkdf2:sha256")


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_token(user, role: Optional[str] = None, extra: Optional[dict] = None) -> tuple[str, int]:
    """签发 JWT。

    载荷包含：sub（用户）、role（角色）、org（机构）、jti（令牌唯一标识，用于黑名单）。
    返回 (token, expires_in_seconds)。
    """
    expire_minutes = int(current_app.config.get("JWT_EXPIRE_MINUTES", 480))
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.username,
        "role": role or user.role,
        "org": user.org,
        "iss": current_app.config.get("JWT_ISSUER", "fedshield"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expire_minutes)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm=current_app.config["JWT_ALGORITHM"])
    return token, expire_minutes * 60


def decode_token(token: str) -> dict:
    """校验并解析 JWT；失败时抛出 401。"""
    try:
        return jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
            issuer=current_app.config.get("JWT_ISSUER", "fedshield"),
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("访问令牌已过期，请重新登录", code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("访问令牌无效", code=401) from exc


# ---------------------------------------------------------------------------
# 审计日志防篡改签名
# ---------------------------------------------------------------------------


def _secret() -> bytes:
    return str(current_app.config.get("SECRET_KEY", "fedshield")).encode("utf-8")


def sign_payload(payload: dict) -> str:
    """对日志关键字段做 HMAC-SHA256 签名（防止日志被事后篡改）。"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hmac.new(_secret(), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_chain(prev_hash: str, payload: dict) -> str:
    """链式哈希：hash = SHA256(prevHash ‖ payloadDigest)，构成不可篡改的日志链。"""
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return hashlib.sha256((prev_hash + digest).encode("utf-8")).hexdigest()


def mask_sensitive(value: str, keep_head: int = 3, keep_tail: int = 4) -> str:
    """动态脱敏：保留首尾若干位，中间以 * 代替。"""
    if not value:
        return ""
    text = str(value)
    if len(text) <= keep_head + keep_tail:
        return "*" * len(text)
    return f"{text[:keep_head]}{'*' * (len(text) - keep_head - keep_tail)}{text[-keep_tail:]}"
