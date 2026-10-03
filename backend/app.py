# -*- coding: utf-8 -*-
"""FedShield 后端应用工厂。

启动方式：
    python run.py                 # 开发模式（自动建表 + 首次自动灌入演示数据）
    python run.py --seed          # 强制初始化演示数据
    python run.py --reset         # 清空数据后重新初始化
"""

from __future__ import annotations

import os
import traceback

from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

from .api import register_blueprints
from .config import INSTANCE_DIR, get_config
from .extensions import cors, db
from .utils.response import ApiError, request_id


def create_app(config_name: str | None = None) -> Flask:
    config_class = get_config(config_name)
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_class)
    app.json.ensure_ascii = False  # 中文直出，避免转义

    os.makedirs(INSTANCE_DIR, exist_ok=True)

    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    register_blueprints(app)
    _register_health(app)
    _register_error_handlers(app)
    _register_cli(app)
    _register_frontend(app)

    with app.app_context():
        db.create_all()
        _ensure_schema(app)
        _warm_up_caches(app)

    app.logger.info("FedShield 后端已就绪：%s", app.config["SQLALCHEMY_DATABASE_URI"])
    return app


def _ensure_schema(app: Flask) -> None:
    """轻量结构兼容：为已存在的库补齐「新增的可空字段」。

    演示项目不引入 Alembic，但迭代中会新增字段（例如异常预警的 amount）。
    这里在启动时对比模型与库结构，缺列则自动 ALTER TABLE ADD COLUMN，
    让老库无需删除重建即可继续使用（仅处理新增可空列，不做改类型/删列）。
    """
    from sqlalchemy import inspect, text

    try:
        engine = db.engine
        inspector = inspect(engine)
        existing = set(inspector.get_table_names())
        added: list[str] = []
        for table in db.metadata.sorted_tables:
            if table.name not in existing:
                continue
            current = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in current:
                    continue
                column_type = column.type.compile(engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))
                added.append(f"{table.name}.{column.name} ({column_type})")
        if added:
            app.logger.info("已自动补齐 %d 个新增字段：%s", len(added), "、".join(added))
    except Exception as exc:  # 结构兼容失败不应阻断启动
        app.logger.warning("结构兼容检查失败（不影响启动，如异常请删除 instance/*.db 重建）：%s", exc)


def _warm_up_caches(app: Flask) -> None:
    """启动预热：构建匿踪查询的清单变换索引，避免首次查询承担冷启动开销。

    预热失败不影响服务启动（例如数据库尚未初始化时），仅记录日志。
    """
    try:
        from .engine import oblivious
        from .models import SanctionEntry

        rows = SanctionEntry.query.all()
        if not rows:
            app.logger.info("跳过匿踪查询预热：制裁清单为空（可执行 python run.py --seed 初始化数据）")
            return
        grouped: dict[str, list[dict]] = {}
        for item in rows:
            grouped.setdefault(item.listName, []).append(item.to_dict())
        result = oblivious.warm_up(grouped)
        app.logger.info(
            "匿踪查询索引预热完成：%s 条变换值，耗时 %sms",
            result.get("entries"),
            result.get("totalMs", result.get("keygenMs")),
        )
    except Exception as exc:  # 预热属优化项，任何异常都不应阻断启动
        app.logger.warning("匿踪查询索引预热失败（不影响启动）：%s", exc)


def _register_health(app: Flask) -> None:
    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "code": 0,
                "message": "ok",
                "data": {
                    "status": "up",
                    "service": "fedshield-backend",
                    "env": app.config.get("ENV", "development"),
                    "database": app.config["SQLALCHEMY_DATABASE_URI"].split("://")[0],
                },
                "requestId": request_id(),
            }
        )


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        # 认证失败时附带 WWW-Authenticate，符合 HTTP 语义
        response = jsonify(
            {"code": error.code, "message": error.message, "data": error.data, "requestId": request_id()}
        )
        response.status_code = error.http_status
        if error.http_status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        message = {
            400: "请求参数错误",
            401: "未认证或令牌失效",
            403: "权限不足",
            404: "接口不存在",
            405: "请求方法不被允许",
            429: "请求过于频繁，已触发限流",
        }.get(error.code, error.description)
        return (
            jsonify({"code": error.code, "message": message, "data": None, "requestId": request_id()}),
            error.code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.error("未捕获异常：%s\n%s", error, traceback.format_exc())
        detail = {
            "exception": type(error).__name__,
            "hint": "完整堆栈已打印在后端控制台（运行 python run.py 的窗口）",
        }
        # 开发模式附带堆栈末几行，便于快速定位
        if app.config.get("DEBUG"):
            detail["traceback"] = traceback.format_exc().splitlines()[-6:]
        return (
            jsonify(
                {
                    "code": 500,
                    "message": f"服务端异常：{type(error).__name__}: {error}",
                    "data": detail,
                    "requestId": request_id(),
                }
            ),
            500,
        )


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command():
        """初始化演示数据（幂等）。"""
        from .seed import seed_all

        result = seed_all()
        print("初始化结果：", result)

    @app.cli.command("reset")
    def reset_command():
        """清空业务数据并重新初始化。"""
        from .seed import reset_all, seed_all

        reset_all()
        print("初始化结果：", seed_all())

    @app.cli.command("verify-chain")
    def verify_chain_command():
        """校验联盟链完整性。"""
        from .audit import chain

        print(chain.verify_chain())


def _register_frontend(app: Flask) -> None:
    """托管前端构建产物（frontend/dist）。

    前端使用 hash 路由，因此仅需把任意非 /api 路径回落到 index.html 即可。
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir = os.path.join(project_dir, "frontend", "dist")

    if not os.path.isdir(dist_dir):
        @app.get("/")
        def index_without_build():
            return jsonify(
                {
                    "code": 0,
                    "message": "FedShield 后端运行中；前端尚未构建",
                    "data": {
                        "api": "/api/health",
                        "hint": "请进入 frontend 目录执行 npm install && npm run dev（开发模式），"
                                "或 npm run build 后由本服务托管静态资源",
                    },
                    "requestId": request_id(),
                }
            )

        return

    @app.get("/")
    def index():
        return send_from_directory(dist_dir, "index.html")

    @app.get("/<path:path>")
    def static_files(path: str):
        if path.startswith("api/"):
            return jsonify({"code": 404, "message": "接口不存在", "data": None, "requestId": request_id()}), 404
        target = os.path.join(dist_dir, path)
        if os.path.isfile(target):
            return send_from_directory(dist_dir, path)
        return send_from_directory(dist_dir, "index.html")


# 供 flask --app backend.app:create_app run 使用
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
