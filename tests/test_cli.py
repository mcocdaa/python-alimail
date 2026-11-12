"""Tests for the command line interface (:mod:`alimail.cli`)."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from alimail.check import DENIED, CheckReport, CheckResult, format_report
from alimail.cli import (
    EXIT_DENIED,
    EXIT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    build_parser,
    main,
)
from alimail.errors import ConfigError, TransportError
from tests.fakes import APP_BASE, json_response, make_client, url_path, url_query

EMAIL = "user@example.test"
ENCODED_EMAIL = "user%40example.test"


def run_cli(argv):
    """Run ``alimail.cli.main`` and capture its output."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def patched_client(client):
    return patch("alimail.cli._client", return_value=client)


class CliGlobalTests(unittest.TestCase):
    def test_version_flag_prints_the_version(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("alimail 0.1.0", stdout.getvalue())

    def test_missing_command_is_a_usage_error(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("usage", stderr.getvalue())

    def test_exit_code_constants(self):
        self.assertEqual((EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_DENIED), (0, 1, 2, 3))

    def test_ops_command_does_not_need_credentials(self):
        # No client patch: ``ops`` is pure metadata and must not touch auth.
        code, out, _ = run_cli(["ops", "list"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("112 operations", out)

    def test_parser_builds(self):
        parser = build_parser()
        self.assertEqual(parser.prog, "alimail")


class CliOpsTests(unittest.TestCase):
    def test_ops_list(self):
        code, out, _ = run_cli(["ops", "list"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("112 operations", out)
        self.assertIn("list_users", out)
        self.assertIn("GET", out)

    def test_ops_default_action_is_list(self):
        code, out, _ = run_cli(["ops"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("112 operations", out)

    def test_ops_list_grep_filters(self):
        code, out, _ = run_cli(["ops", "list", "--grep", "users"])
        self.assertEqual(code, EXIT_OK)
        count = int(out.splitlines()[0].split()[0])
        self.assertLess(count, 112)
        self.assertGreater(count, 0)
        self.assertIn("list_users", out)

    def test_ops_list_tag_filters(self):
        code, out, _ = run_cli(["ops", "list", "--tag", "用户"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("list_users", out)
        count = int(out.splitlines()[0].split()[0])
        self.assertLess(count, 112)

    def test_ops_show_detail(self):
        code, out, _ = run_cli(["ops", "show", "list_users"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("name:   list_users", out)
        self.assertIn("method: GET", out)
        self.assertIn("path:   /v2/users", out)
        self.assertIn("operationId: alimailpb_ud_UserService_ListUsers", out)
        self.assertIn("params:", out)
        self.assertIn("size (query, optional)", out)

    def test_ops_show_without_name_is_a_usage_error(self):
        code, _, err = run_cli(["ops", "show"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("参数错误", err)

    def test_ops_show_unknown_operation_is_a_friendly_usage_error(self):
        # Regression: a KeyError used to escape main() as a traceback.
        code, _, err = run_cli(["ops", "show", "nope_operation"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("未知接口", err)
        self.assertNotIn("Traceback", err)

    def test_call_unknown_operation_is_a_friendly_usage_error(self):
        client, _ = make_client([])
        with patched_client(client):
            code, _, err = run_cli(["call", "nope_operation"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("未知接口", err)
        self.assertNotIn("Traceback", err)


class CliDirectoryCommandTests(unittest.TestCase):
    def test_users_prints_a_table(self):
        data = {
            "users": [
                {
                    "email": EMAIL,
                    "name": "张三",
                    "status": "NORMAL",
                    "type": "USER",
                }
            ],
            "total": 1,
            "hasMore": False,
        }
        client, transport = make_client([json_response(200, data)], email=EMAIL)
        with patched_client(client):
            code, out, _ = run_cli(["users", "--size", "2"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("共 1 个用户 (hasMore=False)", out)
        self.assertIn(EMAIL, out)
        self.assertIn("张三", out)
        self.assertEqual(url_query(transport.calls[0].url), {"size": ["2"]})

    def test_users_json_output_is_parseable(self):
        data = {"users": [], "total": 0}
        client, _ = make_client([json_response(200, data)], email=EMAIL)
        with patched_client(client):
            code, out, _ = run_cli(["--json", "users"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out), data)

    def test_org_prints_json(self):
        client, transport = make_client([json_response(200, {"name": "Example Org"})])
        with patched_client(client):
            code, out, _ = run_cli(["org"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Example Org", out)
        self.assertEqual(url_path(transport.calls[0].url), "/v2/organization/$current")

    def test_token_command_prints_masked_token(self):
        client, transport = make_client([json_response(200, {"ok": True})])
        with patched_client(client):
            code, out, _ = run_cli(["token"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("mode: app", out)
        self.assertIn(f"base: {APP_BASE}", out)
        self.assertIn("token: test-acces...oken (len=17)", out)
        self.assertEqual(len(transport.token_calls), 1)

    def test_token_command_json_output(self):
        client, _ = make_client([])
        with patched_client(client):
            code, out, _ = run_cli(["--json", "token"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn('"token": "test-access-token"', out)

    def test_token_force_fetches_again(self):
        client, transport = make_client(
            [json_response(200, {"access_token": "tok-1", "expires_in": 3600})]
        )
        with patched_client(client):
            code, out, _ = run_cli(["token", "--force"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(transport.token_calls), 1)


class CliMailCommandTests(unittest.TestCase):
    def test_folders_prints_folders(self):
        client, transport = make_client(
            [
                json_response(
                    200,
                    {
                        "folders": [
                            {
                                "id": "2",
                                "displayName": "收件箱",
                                "totalItemCount": 3,
                                "unreadItemCount": 1,
                            }
                        ]
                    },
                )
            ],
            email=EMAIL,
        )
        with patched_client(client):
            code, out, _ = run_cli(["folders", "--email", EMAIL])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("收件箱", out)
        self.assertEqual(
            url_path(transport.calls[0].url),
            f"/v2/users/{ENCODED_EMAIL}/mailFolders",
        )

    def test_inbox_prints_messages(self):
        client, transport = make_client(
            [
                json_response(
                    200,
                    {
                        "messages": [
                            {
                                "subject": "Hello",
                                "from": {"email": "sender@example.test"},
                                "receivedDateTime": "2026-01-01T00:00:00Z",
                            }
                        ],
                        "hasMore": False,
                    },
                )
            ],
            email=EMAIL,
        )
        with patched_client(client):
            code, out, _ = run_cli(["inbox", "--email", EMAIL, "--size", "5"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("1 封邮件 (hasMore=False)", out)
        self.assertIn("Hello", out)
        call = transport.calls[0]
        self.assertEqual(
            url_path(call.url),
            f"/v2/users/{ENCODED_EMAIL}/mailFolders/2/messages",
        )
        self.assertEqual(url_query(call.url)["size"], ["5"])

    def test_read_prints_message_json(self):
        client, transport = make_client([json_response(200, {"id": "m1", "subject": "Hello"})])
        with patched_client(client):
            code, out, _ = run_cli(["read", "m1", "--email", EMAIL])
        self.assertEqual(code, EXIT_OK)
        self.assertIn('"subject": "Hello"', out)
        self.assertEqual(
            url_path(transport.calls[0].url),
            f"/v2/users/{ENCODED_EMAIL}/messages/m1",
        )

    def test_search_sends_the_query_body(self):
        client, transport = make_client([json_response(200, {"messages": []})])
        with patched_client(client):
            code, out, _ = run_cli(["search", "hello", "--email", EMAIL, "--size", "3"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("0 封邮件", out)
        self.assertEqual(
            transport.calls[0].json_body,
            {"email": EMAIL, "query": "hello", "cursor": "", "size": 3},
        )

    def test_inbox_without_email_returns_config_error(self):
        client, _ = make_client([], email=None)
        with patched_client(client):
            code, _, err = run_cli(["inbox"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("配置错误", err)


class CliSendTests(unittest.TestCase):
    def test_dry_run_returns_usage_exit(self):
        client, transport = make_client([], email="sender@example.test")
        with patched_client(client):
            code, out, _ = run_cli(
                [
                    "send",
                    "--to",
                    "a@example.test, b@example.test",
                    "--subject",
                    "Hi",
                    "--text",
                    "body text",
                ]
            )
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("DRY RUN", out)
        self.assertIn("from:    sender@example.test", out)
        self.assertIn("a@example.test, b@example.test", out)
        self.assertIn("subject: Hi", out)
        self.assertIn("确认发送请加 --yes", out)
        self.assertEqual(transport.call_count, 0)

    def test_send_yes_runs_the_two_step_flow(self):
        client, transport = make_client(
            [
                json_response(200, {"message": {"id": "msg-1"}}),
                json_response(200, {"sent": True}),
            ],
            email="sender@example.test",
        )
        with patched_client(client):
            code, out, _ = run_cli(
                [
                    "send",
                    "--to",
                    "a@example.test",
                    "--subject",
                    "Hi",
                    "--text",
                    "body",
                    "--yes",
                ]
            )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(
            url_path(transport.calls[0].url),
            "/v2/users/sender%40example.test/messages",
        )
        self.assertEqual(
            url_path(transport.calls[1].url),
            "/v2/users/sender%40example.test/messages/msg-1/send",
        )
        self.assertIn('"draft"', out)
        self.assertIn('"send"', out)

    def test_send_from_override(self):
        client, transport = make_client(
            [
                json_response(200, {"message": {"id": "msg-1"}}),
                json_response(200, {}),
            ],
            email="sender@example.test",
        )
        with patched_client(client):
            run_cli(
                [
                    "send",
                    "--from",
                    "robot@example.test",
                    "--to",
                    "a@example.test",
                    "--subject",
                    "Hi",
                    "--yes",
                ]
            )
        self.assertEqual(
            transport.calls[0].json_body["message"]["from"]["email"],
            "robot@example.test",
        )

    def test_send_without_sender_returns_config_error(self):
        client, transport = make_client([], email=None)
        with patched_client(client):
            code, _, err = run_cli(["send", "--to", "a@example.test", "--subject", "Hi"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("配置错误", err)
        self.assertEqual(transport.call_count, 0)


class CliRawAndCallTests(unittest.TestCase):
    def test_raw_get_prints_status_and_body(self):
        client, transport = make_client([json_response(200, {"ok": True})])
        with patched_client(client):
            code, out, _ = run_cli(
                [
                    "raw",
                    "GET",
                    "/v2/users",
                    "--query",
                    "a=1",
                    "--json-body",
                    '{"x": 2}',
                ]
            )
        self.assertEqual(code, EXIT_OK)
        self.assertIn("HTTP 200", out)
        self.assertIn('"ok": true', out)
        call = transport.calls[0]
        self.assertEqual(call.method, "GET")
        self.assertEqual(url_path(call.url), "/v2/users")
        self.assertEqual(url_query(call.url), {"a": ["1"]})
        self.assertEqual(call.json_body, {"x": 2})

    def test_raw_error_status_returns_error_exit(self):
        client, _ = make_client([json_response(404, {"message": "missing"})])
        with patched_client(client):
            code, out, _ = run_cli(["raw", "GET", "/v2/users"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("HTTP 404", out)

    def test_raw_invalid_pair_returns_usage_exit(self):
        client, transport = make_client([])
        with patched_client(client):
            code, _, err = run_cli(["raw", "GET", "/v2/users", "--query", "bad"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("参数错误", err)
        self.assertEqual(transport.call_count, 0)

    def test_raw_invalid_json_returns_usage_exit(self):
        client, transport = make_client([])
        with patched_client(client):
            code, _, err = run_cli(["raw", "POST", "/v2/users", "--json-body", "{"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("参数错误", err)
        self.assertEqual(transport.call_count, 0)

    def test_call_operation_with_path_and_query(self):
        client, transport = make_client([json_response(200, {"id": "d1"})])
        with patched_client(client):
            code, out, _ = run_cli(
                [
                    "call",
                    "get_department",
                    "--path",
                    "id=d1",
                    "--query",
                    "$select=id",
                ]
            )
        self.assertEqual(code, EXIT_OK)
        call = transport.calls[0]
        self.assertEqual(url_path(call.url), "/v2/departments/d1")
        self.assertEqual(url_query(call.url), {"$select": ["id"]})
        self.assertIn('"id": "d1"', out)

    def test_call_operation_with_json_body(self):
        client, transport = make_client([json_response(200, {})])
        with patched_client(client):
            code, _, _ = run_cli(
                [
                    "call",
                    "send_message",
                    "--path",
                    f"email={EMAIL}",
                    "--path",
                    "id=m1",
                    "--json-body",
                    '{"email": "user@example.test"}',
                ]
            )
        self.assertEqual(code, EXIT_OK)
        call = transport.calls[0]
        self.assertEqual(
            url_path(call.url),
            f"/v2/users/{ENCODED_EMAIL}/messages/m1/send",
        )
        self.assertEqual(call.json_body, {"email": EMAIL})

    def test_call_invalid_pair_returns_usage_exit(self):
        client, _ = make_client([])
        with patched_client(client):
            code, _, err = run_cli(["call", "list_users", "--path", "bad"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("参数错误", err)

    def test_call_api_error_returns_error_exit(self):
        client, _ = make_client([json_response(403, {"message": "denied", "detailErrorCode": "x"})])
        with patched_client(client):
            code, _, err = run_cli(["call", "list_users"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("错误:", err)
        self.assertIn("403", err)


class CliCheckTests(unittest.TestCase):
    def _report(self, *, passed=True):
        results = [
            CheckResult("组织信息", "Organization.Read.All", "GET", "/v2/org"),
            CheckResult(
                "域名列表",
                "Domain.Read.All",
                "GET",
                "/v2/domains",
                status="ok" if passed else DENIED,
                http_status=200 if passed else 403,
                detail_error_code=None if passed else "accessDenied",
            ),
        ]
        return CheckReport(email=EMAIL, results=results)

    def test_check_success_returns_zero(self):
        client, _ = make_client([], email=EMAIL)
        report = self._report(passed=True)
        with patched_client(client), patch("alimail.cli.run_check", return_value=report):
            code, out, _ = run_cli(["check"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("通过 2/2", out)
        self.assertIn("✅", out)
        self.assertEqual(format_report(report) + "\n", out)

    def test_check_denied_returns_three(self):
        client, _ = make_client([], email=EMAIL)
        report = self._report(passed=False)
        with patched_client(client), patch("alimail.cli.run_check", return_value=report):
            code, out, _ = run_cli(["check"])
        self.assertEqual(code, EXIT_DENIED)
        self.assertIn("❌", out)
        self.assertIn("还需在应用里补充的 scope: Domain.Read.All", out)

    def test_check_forwards_the_email_argument(self):
        client, _ = make_client([], email=EMAIL)
        report = self._report(passed=True)
        with (
            patched_client(client),
            patch("alimail.cli.run_check", return_value=report) as run_check,
        ):
            run_cli(["check", "--email", "other@example.test"])
        run_check.assert_called_once_with(client, "other@example.test")


class CliErrorHandlingTests(unittest.TestCase):
    def test_missing_credentials_return_error_exit(self):
        with patch(
            "alimail.client.load_credentials",
            side_effect=ConfigError("没有找到可用的阿里邮箱凭据"),
        ):
            code, _, err = run_cli(["users"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("配置错误", err)

    def test_transport_error_returns_error_exit(self):
        client, _ = make_client([TransportError("dns failure")], max_retries=0)
        with patched_client(client):
            code, _, err = run_cli(["org"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("错误:", err)
        self.assertIn("dns failure", err)

    def test_send_uses_the_configured_email_when_present(self):
        client, transport = make_client([json_response(200, {})], email="configured@example.test")
        with patched_client(client):
            code, out, _ = run_cli(["send", "--to", "a@example.test", "--subject", "Hi"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("from:    configured@example.test", out)
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
