# -*- coding: utf-8 -*-
"""FedShield 后端配置。

通过环境变量覆盖默认值，便于在测试/生产环境切换（遵循 12-Factor 约定）。
数据库默认使用 SQLite（开箱即用），可通过 DATABASE_URL 指向 MySQL / 国产数据库：
    DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/fedshield?charset=utf8mb4
"""

from __future__ import annotations

import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
INSTANCE_DIR = os.path.join(PROJECT_DIR, "instance")


class Config:
    """基础配置。"""

    # ---------------- 基础 ----------------
    SECRET_KEY = os.getenv("FEDSHIELD_SECRET_KEY", "fedshield-dev-secret-key-change-me")
    JSON_AS_ASCII = False
    # 关闭异常穿透：让全局错误处理器把真实错误信息以统一 JSON 返回，
    # 便于前端直接展示、也便于定位问题（若为 True，Flask 会返回 HTML 错误页，前端只能看到 "status code 500"）
    PROPAGATE_EXCEPTIONS = False

    # ---------------- 数据库 ----------------
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + os.path.join(INSTANCE_DIR, "fedshield.db").replace("\\", "/")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # ---------------- 认证 ----------------
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    JWT_ISSUER = "fedshield"
    # 演示环境的 MFA 动态码（生产环境应对接短信/OTP 服务）
    DEMO_MFA_CODE = os.getenv("FEDSHIELD_DEMO_MFA", "123456")
    DEFAULT_PASSWORD = os.getenv("FEDSHIELD_DEMO_PASSWORD", "FedShield@2026")

    # ---------------- 密码学与隐私计算 ----------------
    PAILLIER_KEY_BITS = int(os.getenv("PAILLIER_KEY_BITS", "1024"))
    PSI_RSA_BITS = int(os.getenv("PSI_RSA_BITS", "1024"))
    DEFAULT_EPSILON = float(os.getenv("DEFAULT_EPSILON", "2.0"))
    # 风控合规红线：漏检率不超过 7%
    MAX_MISS_RATE = float(os.getenv("MAX_MISS_RATE", "0.07"))
    # 黑名单查询响应红线（毫秒）
    QUERY_RESPONSE_TARGET_MS = float(os.getenv("QUERY_RESPONSE_TARGET_MS", "300"))
    # 匿名查询默认协议模式：oprf（生产）/ paillier（文档同态比对）
    OBLIVIOUS_DEFAULT_MODE = os.getenv("OBLIVIOUS_MODE", "oprf")

    # ---------------- 合规与审计 ----------------
    DATA_RETENTION_YEARS = {"GDPR": 7, "PIPL": 5, "PDPA": 3, "CCPA": 2}
    PERMISSION_MAX_DAYS = 30  # 权限与任务周期绑定，最长 30 天
    GRANT_MAX_DAYS = 365  # 数据授权有效期最长 1 年
    BUDGET_TRANSFER_LIMIT = 0.10  # 预算内部调整不超过总量的 10%

    # ---------------- 熔断阈值 ----------------
    CIRCUIT_BREAKER = {
        "cross_region_login_minutes": 60,   # 同一账号跨地区同时登录
        "p1_access_window_minutes": 10,     # 10 分钟内访问 P1 级数据次数
        "p1_access_limit": 5,
        "decrypt_daily_limit": 20,          # 每日解密次数阈值
        "lock_hours": {"low": 1, "medium": 4, "high": 24},
    }

    # ---------------- 文件与分页 ----------------
    MAX_PAGE_SIZE = 200
    DEFAULT_PAGE_SIZE = 10


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    PAILLIER_KEY_BITS = 512
    PSI_RSA_BITS = 512


class ProductionConfig(Config):
    DEBUG = False
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    env = (name or os.getenv("FEDSHIELD_ENV", "development")).lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
