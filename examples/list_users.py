#!/usr/bin/env python3
"""示例：列出阿里邮箱用户（需要 User.Read.All）。

运行前配置凭据（二选一）：

    企业应用模式：
        export ALIMAIL_APP_ID="你的应用ID"
        export ALIMAIL_APP_SECRET="你的应用Secret"

    个人 MCP token 模式：
        export ALIMAIL_MCP_TOKEN="你的MCP Token"
        export ALIMAIL_EMAIL="user@example.com"

也可以把凭据放在 ./alimail_creds.json 或 ~/.alimail/creds.json（格式见 docs/quickstart.md）。
本脚本从环境变量 / 凭据文件读取凭据，不硬编码任何真实凭据、邮箱或域名。

用法：
    python examples/list_users.py [--size 10] [--all]
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

try:
    from alimail import APIError, Client
except ImportError:
    raise SystemExit(
        "未安装 alimail SDK。请先安装：\n"
        "  pip install alimail\n"
        "或在本仓库根目录执行：\n"
        '  pip install -e "."'
    ) from None


def make_client() -> Client:
    """从环境变量 / 凭据文件创建客户端；缺凭据时给出可操作提示。"""
    try:
        return Client.from_env()
    except Exception:  # 凭据缺失或凭据文件格式错误
        raise SystemExit(
            "未找到可用的阿里邮箱凭据。请任选一种方式配置：\n"
            '  export ALIMAIL_APP_ID="..." ALIMAIL_APP_SECRET="..."\n'
            '  export ALIMAIL_MCP_TOKEN="..." ALIMAIL_EMAIL="user@example.com"\n'
            "  或创建 ./alimail_creds.json（格式见 docs/quickstart.md）"
        ) from None


def print_user(user: Any) -> None:
    """打印一行用户信息；字段缺失时用占位符。"""
    if not isinstance(user, dict):
        print(user)
        return
    email = user.get("email") or user.get("id") or "-"
    name = user.get("displayName") or user.get("name") or "-"
    status = user.get("status") or "-"
    print(f"{email:<40} {name:<20} {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="列出阿里邮箱用户（需要 User.Read.All）")
    parser.add_argument(
        "--size", type=int, default=10, help="每页条数（注意参数名是 size，不是 limit）"
    )
    parser.add_argument("--all", action="store_true", help="自动翻页拉取全部用户")
    args = parser.parse_args()

    client = make_client()

    try:
        if args.all:
            # paginate 会根据 nextCursor 自动翻页，适合组织架构同步这类全量场景
            users = client.paginate("GET", "/v2/users", item_key="users", params={"size": 100})
            print(f"{'邮箱':<40} {'姓名':<20} 状态")
            count = 0
            for user in users:
                print_user(user)
                count += 1
            print(f"\n共 {count} 个用户")
        else:
            # users.list() 返回 {"users": [...], "total": N, "hasMore": bool, "nextCursor": ...}
            result = client.users.list(size=max(1, args.size))
            users = result.get("users") or []
            print(f"{'邮箱':<40} {'姓名':<20} 状态")
            for user in users:
                print_user(user)
            print(
                f"\n本页 {len(users)} 条 | total={result.get('total')} "
                f"hasMore={result.get('hasMore')} nextCursor={result.get('nextCursor')}"
            )
    except APIError as exc:
        print(
            f"调用失败：HTTP {exc.status} ({exc.detail_error_code}): {exc.message}", file=sys.stderr
        )
        return 1
    except Exception as exc:  # 例如 Host 不通、凭据配错等非 API 错误
        print(f"调用失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
