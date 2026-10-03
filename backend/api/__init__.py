# -*- coding: utf-8 -*-
"""REST 接口蓝图注册。"""

from __future__ import annotations

from flask import Flask

from . import audit, auth, authz, budget, compliance, dashboard, engine, lineage, meta


def register_blueprints(app: Flask) -> None:
    """注册全部业务蓝图（统一 /api 前缀）。"""
    for module in (auth, meta, dashboard, engine, compliance, authz, budget, lineage, audit):
        app.register_blueprint(module.bp)


__all__ = ["register_blueprints"]
