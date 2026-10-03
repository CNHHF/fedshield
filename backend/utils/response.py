# -*- coding: utf-8 -*-
"""统一响应体、异常与分页工具。"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Sequence

from flask import g, jsonify, request


class ApiError(Exception):
    """业务异常：由全局错误处理器转换为统一响应体。

    常用错误码（与 docs/API.md §11 一致）：
        400 参数校验失败 / 401 未认证 / 403 权限不足 / 404 资源不存在
        409 状态冲突 / 429 熔断限流 / 500 服务端异常
        5001 隐私预算不足 / 5002 合规校验未通过 / 5003 加密解密失败 / 5004 节点未授权
    """

    def __init__(self, message: str, code: int = 400, http_status: int | None = None, data: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status or (code if 400 <= code <= 599 else 400)
        self.data = data


def request_id() -> str:
    """当前请求的链路追踪 ID（写入审计日志与响应体）。"""
    existing = getattr(g, "request_id", None)
    if existing:
        return existing
    value = request.headers.get("X-Request-Id") or f"req-{uuid.uuid4().hex[:12]}"
    g.request_id = value
    return value


def ok(data: Any = None, message: str = "ok"):
    """成功响应。"""
    return jsonify({"code": 0, "message": message, "data": data, "requestId": request_id()})


def fail(message: str, code: int = 400, data: Any = None, http_status: int | None = None):
    """失败响应。"""
    return (
        jsonify({"code": code, "message": message, "data": data, "requestId": request_id()}),
        http_status or (code if 400 <= code <= 599 else 400),
    )


def page_args(default_size: int = 10, max_size: int = 200) -> tuple[int, int]:
    """解析分页参数。"""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.args.get("size", default_size))
    except (TypeError, ValueError):
        size = default_size
    return page, max(1, min(size, max_size))


def paginate(query, page: int, size: int, serializer) -> dict:
    """对 SQLAlchemy 查询做统一分页与序列化。"""
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    return {"list": [serializer(item) for item in items], "total": total, "page": page, "size": size}


def body() -> dict:
    """获取 JSON 请求体（兼容空体）。"""
    return request.get_json(silent=True) or {}


def require_fields(payload: dict, fields: Sequence[str]) -> None:
    """校验必填字段，缺失时抛出 400。"""
    missing = [name for name in fields if payload.get(name) in (None, "", [])]
    if missing:
        raise ApiError(f"缺少必填参数：{'、'.join(missing)}", code=400)


def pick(payload: dict, fields: Iterable[str], default=None) -> dict:
    """按字段清单提取子集（避免把前端多余字段直接写库）。"""
    return {name: payload.get(name, default) for name in fields}
