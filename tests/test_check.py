"""Tests for the permission self check (:mod:`alimail.check`)."""

from __future__ import annotations

import unittest

from alimail.check import (
    DENIED,
    ERROR,
    OK,
    CheckReport,
    CheckResult,
    format_report,
    run,
)
from alimail.errors import TransportError
from tests.fakes import json_response, make_client, url_path, url_query

EMAIL = "user@example.test"
ENCODED_EMAIL = "user%40example.test"
TOTAL_PROBES = 13


def _successful_sequence(users=None, overrides=None):
    """Build the 13 responses consumed by :func:`alimail.check.run` in order."""
    if users is None:
        users = [{"email": EMAIL, "status": "NORMAL"}]
    responses = [
        json_response(200, {"name": "Org"}),
        json_response(200, {"domains": []}),
        json_response(200, {"users": users, "total": len(users)}),
        json_response(200, {"departments": []}),
        json_response(200, {"groups": []}),
        json_response(200, {"allowBlockLists": []}),
        json_response(200, {"results": []}),
        json_response(200, {"email": EMAIL}),
        json_response(200, {"folders": []}),
        json_response(200, {"messages": []}),
        json_response(200, {"calendars": []}),
        json_response(200, {"messages": []}),
        json_response(200, {"accounts": []}),
    ]
    for index, replacement in (overrides or {}).items():
        responses[index] = replacement
    return responses


class CheckRunSuccessTests(unittest.TestCase):
    def test_all_read_only_probes_pass(self):
        client, transport = make_client(_successful_sequence())
        report = run(client, EMAIL)
        self.assertEqual(report.email, EMAIL)
        self.assertEqual(report.total, TOTAL_PROBES)
        self.assertEqual(report.passed, TOTAL_PROBES)
        self.assertTrue(report.all_passed)
        self.assertEqual(report.missing_scopes(), [])
        self.assertEqual(transport.call_count, TOTAL_PROBES)

    def test_email_is_inferred_from_the_user_list(self):
        users = [
            {"email": "disabled@example.test", "status": "DISABLED"},
            {"email": EMAIL, "status": "NORMAL"},
        ]
        client, transport = make_client(_successful_sequence(users=users))
        report = run(client)
        self.assertEqual(report.email, EMAIL)
        self.assertEqual(report.passed, TOTAL_PROBES)
        user_dimension_calls = transport.calls[7:]
        self.assertEqual(len(user_dimension_calls), 6)
        for call in user_dimension_calls:
            self.assertIn(ENCODED_EMAIL, call.url)

    def test_email_inference_accepts_users_without_status(self):
        client, _ = make_client(_successful_sequence(users=[{"email": EMAIL}]))
        report = run(client)
        self.assertEqual(report.email, EMAIL)

    def test_probes_only_use_read_only_requests(self):
        client, transport = make_client(_successful_sequence())
        run(client, EMAIL)
        methods = {call.method for call in transport.calls}
        self.assertEqual(methods, {"GET", "POST"})
        post_calls = [call for call in transport.calls if call.method == "POST"]
        self.assertEqual(len(post_calls), 1)
        self.assertEqual(url_path(post_calls[0].url), "/v2/reports")

    def test_probe_paths_and_query_parameters(self):
        client, transport = make_client(_successful_sequence())
        run(client, EMAIL)
        calls = transport.calls
        self.assertEqual(url_path(calls[0].url), "/v2/organization/$current")
        self.assertEqual(url_path(calls[1].url), "/v2/domains")
        self.assertEqual(url_query(calls[2].url), {"size": ["5"]})
        self.assertEqual(url_path(calls[3].url), "/v2/departments/$root/departments")
        self.assertEqual(url_path(calls[4].url), "/v2/groups")
        self.assertEqual(url_path(calls[5].url), "/v2/messageRules/allowBlockLists")
        self.assertEqual(
            calls[6].json_body,
            {
                "startTime": "1970-01-01T00:00:00Z",
                "endTime": "1970-01-01T00:00:01Z",
                "size": 1,
            },
        )
        self.assertEqual(url_path(calls[7].url), f"/v2/users/{ENCODED_EMAIL}")
        self.assertEqual(url_path(calls[8].url), f"/v2/users/{ENCODED_EMAIL}/mailFolders")
        self.assertEqual(
            url_path(calls[9].url),
            f"/v2/users/{ENCODED_EMAIL}/mailFolders/2/messages",
        )
        self.assertEqual(url_query(calls[9].url)["size"], ["1"])
        self.assertEqual(url_path(calls[10].url), f"/v2/users/{ENCODED_EMAIL}/calendars")
        self.assertEqual(
            url_path(calls[11].url),
            f"/v2/users/{ENCODED_EMAIL}/quarantine/messages/search",
        )
        self.assertEqual(url_path(calls[12].url), f"/v2/users/{ENCODED_EMAIL}/sharedWithMe")

    def test_explicit_email_wins_over_the_user_list(self):
        client, transport = make_client(
            _successful_sequence(users=[{"email": "other@example.test"}])
        )
        report = run(client, "explicit@example.test")
        self.assertEqual(report.email, "explicit@example.test")
        self.assertEqual(url_path(transport.calls[7].url), "/v2/users/explicit%40example.test")


class CheckRunFailureTests(unittest.TestCase):
    def test_mixed_failures_are_reported(self):
        overrides = {
            1: json_response(403, {"message": "denied", "detailErrorCode": "accessDenied"}),
            4: json_response(403, {"message": "denied"}),
            6: json_response(500, {"message": "boom"}),
            9: json_response(403, {"message": "denied"}),
            11: json_response(500, {"message": "boom"}),
        }
        client, transport = make_client(_successful_sequence(overrides=overrides), max_retries=0)
        report = run(client, EMAIL)
        self.assertEqual(report.total, TOTAL_PROBES)
        self.assertEqual(report.passed, TOTAL_PROBES - 5)
        self.assertFalse(report.all_passed)
        self.assertEqual(
            report.missing_scopes(),
            [
                "Domain.Read.All",
                "Group.Read.All",
                "Report.Read.All",
                "Mail.Read.All",
                "Quarantine.Read.All",
            ],
        )
        statuses = {result.name: result.status for result in report.results}
        self.assertEqual(statuses["域名列表"], DENIED)
        self.assertEqual(statuses["邮件组列表"], DENIED)
        self.assertEqual(statuses["审计日志"], ERROR)
        self.assertEqual(statuses["隔离区搜索"], ERROR)
        self.assertEqual(transport.call_count, TOTAL_PROBES)

    def test_403_detail_error_code_is_kept(self):
        overrides = {
            1: json_response(403, {"message": "denied", "detailErrorCode": "scopeMissing"})
        }
        client, _ = make_client(_successful_sequence(overrides=overrides))
        report = run(client, EMAIL)
        domain = next(result for result in report.results if result.name == "域名列表")
        self.assertEqual(domain.status, DENIED)
        self.assertEqual(domain.http_status, 403)
        self.assertEqual(domain.detail_error_code, "scopeMissing")
        self.assertEqual(domain.message, "denied")

    def test_missing_user_email_short_circuits_user_dimension(self):
        overrides = {2: json_response(403, {"message": "denied"})}
        client, transport = make_client(_successful_sequence(overrides=overrides))
        report = run(client)
        self.assertIsNone(report.email)
        self.assertEqual(report.total, 8)
        self.assertEqual(report.passed, 6)
        self.assertEqual(report.missing_scopes(), ["User.Read.All"])
        last = report.results[-1]
        self.assertEqual(last.name, "用户维度测试")
        self.assertEqual(last.status, ERROR)
        self.assertIn("--email", last.message)
        self.assertEqual(transport.call_count, 7)
        text = format_report(report)
        self.assertIn("还需在应用里补充的 scope: User.Read.All", text)
        self.assertNotIn(", -", text)

    def test_user_list_server_error_is_marked_as_error(self):
        overrides = {2: json_response(500, {"message": "boom"})}
        client, _ = make_client(_successful_sequence(overrides=overrides), max_retries=0)
        report = run(client, EMAIL)
        users = next(result for result in report.results if result.name == "用户列表")
        self.assertEqual(users.status, ERROR)
        self.assertEqual(users.http_status, 500)
        self.assertEqual(report.missing_scopes(), ["User.Read.All"])

    def test_transport_error_is_reported_as_error(self):
        overrides = {0: TransportError("connection refused")}
        client, transport = make_client(_successful_sequence(overrides=overrides), max_retries=0)
        report = run(client, EMAIL)
        organization = report.results[0]
        self.assertEqual(organization.status, ERROR)
        self.assertIn("connection refused", organization.message)
        self.assertEqual(report.passed, TOTAL_PROBES - 1)
        self.assertEqual(transport.call_count, TOTAL_PROBES)

    def test_missing_scopes_are_deduplicated(self):
        overrides = {
            7: json_response(403, {"message": "denied"}),
            12: json_response(403, {"message": "denied"}),
        }
        client, _ = make_client(_successful_sequence(overrides=overrides))
        report = run(client, EMAIL)
        self.assertEqual(report.missing_scopes(), ["User.Read.All"])
        self.assertEqual(report.passed, TOTAL_PROBES - 2)


class CheckReportModelTests(unittest.TestCase):
    def test_result_passed_property(self):
        self.assertTrue(CheckResult("a", "s", "GET", "/a").passed)
        self.assertFalse(CheckResult("a", "s", "GET", "/a", status=DENIED).passed)
        self.assertFalse(CheckResult("a", "s", "GET", "/a", status=ERROR).passed)

    def test_report_counters(self):
        report = CheckReport(
            email=EMAIL,
            results=[
                CheckResult("a", "Scope.A", "GET", "/a"),
                CheckResult("b", "Scope.B", "GET", "/b", status=DENIED),
            ],
        )
        self.assertEqual(report.total, 2)
        self.assertEqual(report.passed, 1)
        self.assertFalse(report.all_passed)
        self.assertEqual(report.missing_scopes(), ["Scope.B"])

    def test_missing_scopes_ignores_placeholder_scopes(self):
        # Regression: the synthetic "no email" row uses "-" as its scope and
        # used to leak into the "scopes still missing" hint.
        report = CheckReport(
            results=[
                CheckResult("用户维度测试", "-", "-", "-", status=ERROR, message="no email"),
                CheckResult(
                    "组织信息",
                    "",
                    "GET",
                    "/v2/organization/$current",
                    status=DENIED,
                ),
                CheckResult(
                    "组织信息",
                    "  ",
                    "GET",
                    "/v2/organization/$current",
                    status=DENIED,
                ),
                CheckResult(
                    "域名列表",
                    "Domain.Read.All",
                    "GET",
                    "/v2/domains",
                    status=DENIED,
                ),
                CheckResult(
                    "域名列表",
                    " Domain.Read.All ",
                    "GET",
                    "/v2/domains",
                    status=DENIED,
                ),
            ]
        )
        self.assertEqual(report.missing_scopes(), ["Domain.Read.All"])

    def test_empty_report_all_passed_is_false(self):
        report = CheckReport()
        self.assertEqual(report.total, 0)
        self.assertFalse(report.all_passed)


class FormatReportTests(unittest.TestCase):
    def test_all_passed_report(self):
        client, _ = make_client(_successful_sequence())
        report = run(client, EMAIL)
        text = format_report(report)
        self.assertIn(f"账号: {EMAIL}  通过 {TOTAL_PROBES}/{TOTAL_PROBES}", text)
        self.assertIn("✅", text)
        self.assertNotIn("❌", text)
        self.assertNotIn("还需在应用里补充的 scope", text)

    def test_denied_report_lists_missing_scopes(self):
        report = CheckReport(
            email=EMAIL,
            results=[
                CheckResult("组织信息", "Organization.Read.All", "GET", "/v2/org"),
                CheckResult(
                    "域名列表",
                    "Domain.Read.All",
                    "GET",
                    "/v2/domains",
                    status=DENIED,
                    http_status=403,
                    detail_error_code="accessDenied",
                    message="denied",
                ),
            ],
        )
        text = format_report(report)
        self.assertIn(f"账号: {EMAIL}  通过 1/2", text)
        self.assertIn("✅", text)
        self.assertIn("❌", text)
        self.assertIn("accessDenied", text)
        self.assertIn("还需在应用里补充的 scope: Domain.Read.All", text)

    def test_error_report_uses_warning_mark(self):
        report = CheckReport(
            results=[
                CheckResult(
                    "审计日志",
                    "Report.Read.All",
                    "POST",
                    "/v2/reports",
                    status=ERROR,
                    message="boom",
                )
            ],
        )
        text = format_report(report)
        self.assertIn("⚠️", text)
        self.assertIn("boom", text)
        self.assertIn("通过 0/1", text)

    def test_report_without_email_or_results(self):
        text = format_report(CheckReport())
        self.assertIn("通过 0/0", text)
        self.assertNotIn("账号", text)

    def test_report_result_status_constants(self):
        self.assertEqual((OK, DENIED, ERROR), ("ok", "denied", "error"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
