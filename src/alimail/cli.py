"""Command line interface: ``alimail ...``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ._version import __version__
from .check import format_report
from .check import run as run_check
from .client import Client
from .errors import AlimailError, ConfigError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DENIED = 3


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _dump(data: Any, pretty: bool = True) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _print_users(data: Any) -> None:
    if not isinstance(data, dict):
        _dump(data)
        return
    users = data.get("users") or []
    print(f"共 {data.get('total', len(users))} 个用户 (hasMore={data.get('hasMore')})")
    print(f"{'邮箱':<38}{'姓名':<16}{'状态':<10}{'类型'}")
    print("-" * 78)
    for user in users:
        print(
            f"{user.get('email', ''):<38}{str(user.get('name', '')):<16}"
            f"{str(user.get('status', '')):<10}{user.get('type', '')}"
        )


def _print_messages(data: Any) -> None:
    if not isinstance(data, dict):
        _dump(data)
        return
    messages = data.get("messages") or []
    print(f"{len(messages)} 封邮件 (hasMore={data.get('hasMore')})")
    print(f"{'时间':<21}{'发件人':<38}{'主题'}")
    print("-" * 100)
    for message in messages:
        sender = message.get("from") or {}
        email = sender.get("email", "") if isinstance(sender, dict) else ""
        print(
            f"{str(message.get('receivedDateTime', '')):<21}{email:<38}{message.get('subject', '')}"
        )


def _print_folders(data: Any) -> None:
    if not isinstance(data, dict):
        _dump(data)
        return
    print(f"{'ID':<6}{'名称':<18}{'总数':<8}{'未读'}")
    print("-" * 42)
    for folder in data.get("folders") or []:
        print(
            f"{str(folder.get('id', '')):<6}{folder.get('displayName', ''):<18}"
            f"{str(folder.get('totalItemCount', '')):<8}{folder.get('unreadItemCount', '')}"
        )


def _client(args: argparse.Namespace) -> Client:
    return Client(
        app_id=args.app_id,
        app_secret=args.app_secret,
        base=args.base,
        timeout=args.timeout,
    )


def _email(args: argparse.Namespace, client: Client) -> str:
    email = getattr(args, "email", None) or client.email
    if not email:
        raise ConfigError("缺少邮箱地址：用 --email 指定（或设置 ALIMAIL_EMAIL）")
    return email


def _parse_pairs(pairs: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"参数格式应为 key=value: {pair!r}")
        key, value = pair.split("=", 1)
        result[key] = value
    return result


# ----------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------
def cmd_token(args: argparse.Namespace) -> int:
    client = _client(args)
    token = client.token(force=args.force)
    print(f"mode: {client.mode}")
    print(f"base: {client.base}")
    if args.json:
        _dump({"mode": client.mode, "base": client.base, "token": token})
    else:
        print(f"token: {token[:10]}...{token[-4:]} (len={len(token)})")
    return EXIT_OK


def cmd_org(args: argparse.Namespace) -> int:
    _dump(_client(args).organization.get(), pretty=not args.json)
    return EXIT_OK


def cmd_users(args: argparse.Namespace) -> int:
    data = _client(args).users.list(size=args.size, filter=args.filter)
    if not args.json:
        _print_users(data)
    else:
        _dump(data, pretty=False)
    return EXIT_OK


def cmd_folders(args: argparse.Namespace) -> int:
    client = _client(args)
    data = client.mail.folders(_email(args, client))
    if not args.json:
        _print_folders(data)
    else:
        _dump(data, pretty=False)
    return EXIT_OK


def cmd_inbox(args: argparse.Namespace) -> int:
    client = _client(args)
    data = client.mail.inbox(_email(args, client), size=args.size)
    if not args.json:
        _print_messages(data)
    else:
        _dump(data, pretty=False)
    return EXIT_OK


def cmd_read(args: argparse.Namespace) -> int:
    client = _client(args)
    _dump(client.mail.message(_email(args, client), args.message_id), pretty=not args.json)
    return EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    client = _client(args)
    data = client.mail.search(_email(args, client), args.query, size=args.size)
    if not args.json:
        _print_messages(data)
    else:
        _dump(data, pretty=False)
    return EXIT_OK


def cmd_send(args: argparse.Namespace) -> int:
    client = _client(args)
    sender = args.sender or client.email
    if not sender:
        raise ConfigError("缺少发件邮箱：用 --from 指定")
    recipients = [item.strip() for item in args.to.split(",") if item.strip()]
    if not args.yes:
        print("DRY RUN —— 即将发送：")
        print(f"  from:    {sender}")
        print(f"  to:      {', '.join(recipients)}")
        print(f"  subject: {args.subject}")
        print(f"  text:    {args.text or ''}")
        print("确认发送请加 --yes")
        return EXIT_USAGE
    result = client.mail.send(
        sender,
        to=recipients,
        subject=args.subject,
        text=args.text,
        html=args.html,
    )
    _dump(result, pretty=not args.json)
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    client = _client(args)
    report = run_check(client, args.email)
    if args.json:
        payload = {
            "email": report.email,
            "passed": report.passed,
            "total": report.total,
            "all_passed": report.all_passed,
            "missing_scopes": report.missing_scopes(),
            "results": [
                {
                    "name": result.name,
                    "scope": result.scope,
                    "method": result.method,
                    "path": result.path,
                    "status": result.status,
                    "passed": result.passed,
                    "http_status": result.http_status,
                    "detail_error_code": result.detail_error_code,
                    "message": result.message,
                }
                for result in report.results
            ],
        }
        _dump(payload, pretty=False)
    else:
        print(format_report(report))
    if report.all_passed:
        return EXIT_OK
    return EXIT_DENIED


def cmd_call(args: argparse.Namespace) -> int:
    client = _client(args)
    path_params = _parse_pairs(args.path)
    query = _parse_pairs(args.query)
    body = json.loads(args.json_body) if args.json_body else None
    result = client.call(args.operation, path=path_params, query=query, json=body)
    _dump(result, pretty=not args.json)
    return EXIT_OK


def cmd_ops(args: argparse.Namespace) -> int:
    from .operations import all_operations, get_operation

    if args.action == "show":
        if not args.name:
            raise ValueError("用法: alimail ops show <operation-name>")
        operation = get_operation(args.name)
        print(f"name:   {operation.name}")
        print(f"method: {operation.method}")
        print(f"path:   {operation.path}")
        print(f"summary: {operation.summary}")
        print(f"scopes: {', '.join(operation.scopes) or '-'}")
        print(f"operationId: {operation.operation_id}")
        if operation.params:
            print("params:")
            for param in operation.params:
                required = "required" if param.get("required") else "optional"
                print(f"  - {param.get('name')} ({param.get('in')}, {required})")
        return EXIT_OK

    operations = all_operations()
    if args.grep:
        needle = args.grep.lower()
        operations = tuple(
            op
            for op in operations
            if needle in op.name.lower()
            or needle in op.path.lower()
            or needle in op.summary.lower()
        )
    if args.tag:
        operations = tuple(op for op in operations if args.tag in op.tags)
    print(f"{len(operations)} operations")
    print(f"{'name':<38}{'method':<8}{'path':<52}summary")
    print("-" * 130)
    for operation in operations:
        print(f"{operation.name:<38}{operation.method:<8}{operation.path:<52}{operation.summary}")
    return EXIT_OK


def cmd_raw(args: argparse.Namespace) -> int:
    client = _client(args)
    query = _parse_pairs(args.query)
    body = json.loads(args.json_body) if args.json_body else None
    response = client.raw(args.method, args.path, params=query or None, json=body)
    print(f"HTTP {response.status}")
    _dump(response.data, pretty=not args.json)
    return EXIT_OK if response.ok else EXIT_ERROR


# ----------------------------------------------------------------------
# parser
# ----------------------------------------------------------------------
def _add_global(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", help="应用 ID（client_id），默认读环境变量 ALIMAIL_APP_ID")
    parser.add_argument("--app-secret", help="应用 Secret，默认读环境变量 ALIMAIL_APP_SECRET")
    parser.add_argument("--base", help="API Host，默认 https://alimail-cn.aliyuncs.com")
    parser.add_argument("--timeout", type=float, default=30.0, help="请求超时秒数")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alimail",
        description="阿里邮箱（Alibaba Mail）OpenAPI 命令行工具 —— 非官方",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_global(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("token", help="打印/验证访问令牌")
    p.add_argument("--force", action="store_true", help="忽略缓存，强制重新获取")
    p.set_defaults(func=cmd_token)

    p = sub.add_parser("org", help="获取组织信息")
    p.set_defaults(func=cmd_org)

    p = sub.add_parser("users", help="查询用户列表")
    p.add_argument("--size", type=int, default=20)
    p.add_argument("--filter", help="过滤表达式，例如 (email=*)")
    p.set_defaults(func=cmd_users)

    p = sub.add_parser("folders", help="查询邮件文件夹")
    p.add_argument("--email")
    p.set_defaults(func=cmd_folders)

    p = sub.add_parser("inbox", help="查询收件箱")
    p.add_argument("--email")
    p.add_argument("--size", type=int, default=10)
    p.set_defaults(func=cmd_inbox)

    p = sub.add_parser("read", help="读取一封邮件")
    p.add_argument("message_id")
    p.add_argument("--email")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("search", help="搜索邮件")
    p.add_argument("query")
    p.add_argument("--email")
    p.add_argument("--size", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("send", help="发送邮件（会创建草稿再发送）")
    p.add_argument("--from", dest="sender", help="发件邮箱")
    p.add_argument("--to", required=True, help="收件人，多个用逗号分隔")
    p.add_argument("--subject", required=True)
    p.add_argument("--text", help="纯文本正文")
    p.add_argument("--html", help="HTML 正文")
    p.add_argument("--yes", action="store_true", help="确认发送（不加则只做 dry-run）")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("check", help="只读权限自检")
    p.add_argument("--email", help="用于用户维度探测的邮箱，默认自动选取第一个用户")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("call", help="按 operation 名称调用任意接口")
    p.add_argument("operation")
    p.add_argument("--path", action="append", metavar="KEY=VALUE", help="路径参数，可重复")
    p.add_argument("--query", action="append", metavar="KEY=VALUE", help="查询参数，可重复")
    p.add_argument("--json-body", "--body", dest="json_body", help="JSON 请求体")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("ops", help="列出/查看接口")
    p.add_argument("action", nargs="?", default="list", choices=["list", "show"])
    p.add_argument("name", nargs="?")
    p.add_argument("--grep", help="按名称/路径/说明过滤")
    p.add_argument("--tag", help="按标签过滤")
    p.set_defaults(func=cmd_ops)

    p = sub.add_parser("raw", help="直接发原始请求")
    p.add_argument("method")
    p.add_argument("path")
    p.add_argument("--query", action="append", metavar="KEY=VALUE")
    p.add_argument("--json-body", "--body", dest="json_body")
    p.set_defaults(func=cmd_raw)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or EXIT_OK)
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except AlimailError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyError as exc:
        print(f"未知接口或参数: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
