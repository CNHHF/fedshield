# -*- coding: utf-8 -*-
"""Flask 扩展实例（在此集中初始化，避免循环导入）。"""

from __future__ import annotations

from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
cors = CORS()

__all__ = ["db", "cors"]
