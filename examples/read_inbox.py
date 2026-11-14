#!/usr/bin/env python3
"""示例：读取某个邮箱的收件箱（需要 Mail.Read.All）。

运行前配置凭据（二选一）：

    企业应用模式：
        export ALIMAIL_APP_ID="你的应用ID"
        export ALIMAIL_APP_SECRET="你的应用Secret"

    个人 MCP token 模式：
        export ALIMAIL_MCP_TOKEN="你的MCP Token"
        export ALIMAIL_EMAIL="user@example.com"

也可以用 --email 指定要读取的邮箱。本脚本不硬编码任何真实凭据、邮箱或域名。

用法：
    python examples/read_inbox.py user@example.com [--size 5]
    python examples/read_inbox.py --size 5          # 邮箱取自 ALIMAIL_EMAIL
"""

from __future__ import annotations

import argparse
import os
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


def extract_messages(result: Any) -> list[Any]:
    """从列表响应里取出邮件数组，兼容 list / dict 两种返回结构。"""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("messages", "value", "items"):
            value = result.get(key)
            if isinstance(value, list):
                return value
    return []


def sender_of(message: Any) -> str:
    """从邮件对象里取发件人地址，字段缺失时返回 ?。"""
    if not isinstance(message, dict):
        return "?"
    raw = message.get("from") or message.get("sender") or {}
    if isinstance(raw, dict):
        return str(raw.get("email") or raw.get("address") or "?")
    return str(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="读取阿里邮箱收件箱（需要 Mail.Read.All）")
    parser.add_argument(
        "email",
        nargs="?",
        default=os.environ.get("ALIMAIL_EMAIL"),
        help="要读取的邮箱地址；缺省取环境变量 ALIMAIL_EMAIL",
    )
    parser.add_argument("--size", type=int, default=5, help="读取最近多少封，默认 5")
    args = parser.parse_args()

    if not args.email:
        raise SystemExit(
            "缺少邮箱地址。请传入参数或在环境变量中设置 ALIMAIL_EMAIL：\n"
            "  python examples/read_inbox.py user@example.com --size 5"
        )

    client = make_client()

    try:
        # inbox() 直接使用收件箱固定数字 ID（INBOX_FOLDER_ID = "2"）；若需按显示名解析可用 find_folder_id()
        result = client.mail.inbox(args.email, size=max(1, args.size))
        messages = extract_messages(result)

        print(f"{args.email} 收件箱取到 {len(messages)} 封\n")
        for message in messages:
            if not isinstance(message, dict):
                print(message)
                continue
            flag = "[已读]" if message.get("isRead") else "[未读]"
            subject = message.get("subject") or "(无主题)"
            print(f"{flag} {sender_of(message):<32} {subject}")

        # 再演示一次「按 ID 读单封详情」
        if messages and isinstance(messages[0], dict):
            message_id = messages[0].get("id")
            if message_id:
                detail = client.mail.message(args.email, message_id)
                print("\n--- 第一封详情 ---")
                if isinstance(detail, dict):
                    print("主题:", detail.get("subject") or "(无主题)")
                    print("发件人:", sender_of(detail))
                    print("ID:", detail.get("id") or message_id)
                    body = detail.get("body")
                    if isinstance(body, dict):
                        text = body.get("bodyText") or body.get("content") or ""
                        print("正文:", (text or "（无纯文本正文）")[:500])
                else:
                    print(detail)
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
