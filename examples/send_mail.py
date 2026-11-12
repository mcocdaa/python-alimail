#!/usr/bin/env python3
"""示例：发送一封纯文本邮件（需要 Mail.ReadWrite.All + Mail.Send.All）。

⚠️ 发送是不可逆操作。本示例默认 **dry-run**：只打印将要发送的内容，不调用任何接口。
确认无误后，显式设置环境变量才会真正发送：

    Windows PowerShell:  $env:ALIMAIL_EXAMPLE_SEND = "1"
    Linux / macOS:       export ALIMAIL_EXAMPLE_SEND=1

运行前配置凭据（二选一）：

    企业应用模式：
        export ALIMAIL_APP_ID="你的应用ID"
        export ALIMAIL_APP_SECRET="你的应用Secret"

    个人 MCP token 模式：
        export ALIMAIL_MCP_TOKEN="你的MCP Token"
        export ALIMAIL_EMAIL="user@example.com"

本脚本不硬编码任何真实凭据、邮箱或域名；发件人默认取环境变量 ALIMAIL_EMAIL。

用法：
    python examples/send_mail.py --to someone@example.com --subject "Hello" --text "正文"
    $env:ALIMAIL_EXAMPLE_SEND = "1"   # 确认后开启真正发送
    python examples/send_mail.py --to someone@example.com --subject "Hello" --text "正文" --yes
"""

from __future__ import annotations

import argparse
import json
import os
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser(description="发送纯文本邮件（默认 dry-run，不真正发送）")
    parser.add_argument("--to", required=True, help="收件人地址，多个用英文逗号分隔")
    parser.add_argument("--subject", required=True, help="邮件主题")
    parser.add_argument("--text", default="", help="纯文本正文")
    parser.add_argument(
        "--from",
        dest="sender",
        default=os.environ.get("ALIMAIL_EMAIL"),
        help="发件邮箱；缺省取环境变量 ALIMAIL_EMAIL",
    )
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（仅用于受控脚本）")
    args = parser.parse_args()

    recipients = [item.strip() for item in args.to.split(",") if item.strip()]
    if not recipients:
        raise SystemExit("收件人为空，请通过 --to 指定至少一个地址。")
    if not args.sender:
        raise SystemExit(
            "缺少发件邮箱。请设置环境变量 ALIMAIL_EMAIL，或用 --from 指定：\n"
            "  python examples/send_mail.py --from user@example.com --to someone@example.com ..."
        )

    print("发件人:", args.sender)
    print("收件人:", ", ".join(recipients))
    print("主题:", args.subject)
    print("正文:", args.text or "(空)")
    print()

    if os.environ.get("ALIMAIL_EXAMPLE_SEND") != "1":
        print("DRY-RUN：未真正发送。")
        print("确认要发送时，设置环境变量 ALIMAIL_EXAMPLE_SEND=1 后重新运行。")
        return 0

    if not args.yes:
        try:
            answer = input("发送是不可逆操作，确认发送？输入 yes 继续：")
        except EOFError:  # 非交互环境（如管道）默认取消
            answer = ""
        if answer.strip().lower() not in {"yes", "y"}:
            print("已取消，未发送。")
            return 0

    client = make_client()

    try:
        # mail.send() 内部按官方流程执行「创建草稿 → 发送草稿」两步
        result = client.mail.send(
            args.sender,
            to=recipients,
            subject=args.subject,
            text=args.text,
        )
        print("已提交发送：", json.dumps(result, ensure_ascii=False)[:500])
    except APIError as exc:
        print(
            f"发送失败：HTTP {exc.status} ({exc.detail_error_code}): {exc.message}", file=sys.stderr
        )
        return 1
    except Exception as exc:  # 例如 Host 不通、凭据配错等非 API 错误
        print(f"发送失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
