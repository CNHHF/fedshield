# -*- coding: utf-8 -*-
"""FedShield 后端启动入口。

用法：
    python run.py               # 启动服务并自动初始化演示数据（若为空库）
    python run.py --seed        # 仅初始化演示数据
    python run.py --reset       # 清空并重新初始化演示数据
    python run.py --port 5001   # 指定端口
    python run.py --no-seed     # 不自动初始化数据
"""

from __future__ import annotations

import argparse
import sys

from backend.app import create_app
from backend.extensions import db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FedShield 隐私计算平台后端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=5000, help="监听端口（默认 5000）")
    parser.add_argument("--seed", action="store_true", help="初始化演示数据后退出")
    parser.add_argument("--reset", action="store_true", help="清空并重新初始化演示数据后退出")
    parser.add_argument("--no-seed", action="store_true", help="启动时不自动初始化演示数据")
    parser.add_argument("--debug", action="store_true", help="开启调试模式")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app()

    with app.app_context():
        db.create_all()
        from backend.seed import reset_all, seed_all

        if args.reset:
            reset_all()
        if args.reset or args.seed:
            result = seed_all()
            print("[FedShield] 数据初始化结果：", result)
            if args.seed or args.reset:
                return 0
        elif not args.no_seed:
            # 空库时自动灌入演示数据，保证前端打开即有内容
            from backend.models import User

            if User.query.count() == 0:
                result = seed_all()
                print("[FedShield] 检测到空数据库，已自动初始化演示数据：", result)

    print(f"[FedShield] 后端服务启动：http://{args.host}:{args.port}")
    print(f"[FedShield] 健康检查：http://{args.host}:{args.port}/api/health")
    print("[FedShield] 演示账号：risk.officer / compliance.lead / merchant.demo / regulator.eu / security.admin")
    print("[FedShield] 统一口令：FedShield@2026，MFA 动态码：123456")
    # 启动预热：匿踪查询索引（保证首次查询即满足 ≤300ms 指标）
    with app.app_context():
        from backend.app import _warm_up_caches

        _warm_up_caches(app)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
