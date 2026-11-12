"""Read-only permission self check.

``alimail check`` (or :func:`run`) calls a set of read-only endpoints and
reports which OAuth scopes are already granted to the application.  It is the
fastest way to confirm that an application was configured correctly, and to
see what is missing after adding permissions.

A scope change requires fetching a **new** access token; the check uses the
regular client, so run ``alimail token --force`` (or pass a fresh cache) after
changing permissions in the console.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import Client
from .errors import AlimailError, APIError, TransportError

OK = "ok"
DENIED = "denied"
ERROR = "error"


@dataclass
class CheckResult:
    """Outcome of one probe."""

    name: str
    scope: str
    method: str
    path: str
    status: str = OK
    http_status: int | None = None
    detail_error_code: str | None = None
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.status == OK


@dataclass
class CheckReport:
    email: str | None = None
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return bool(self.results) and self.passed == self.total

    def missing_scopes(self) -> list[str]:
        seen: list[str] = []
        for result in self.results:
            scope = (result.scope or "").strip()
            if not result.passed and scope and scope != "-" and scope not in seen:
                seen.append(scope)
        return seen


def _probe(report: CheckReport, name: str, scope: str, method: str, path: str, fn: Any) -> None:
    result = CheckResult(name=name, scope=scope, method=method, path=path)
    try:
        fn()
    except APIError as exc:
        result.http_status = exc.status
        result.detail_error_code = exc.detail_error_code
        result.message = exc.message or ""
        result.status = DENIED if exc.status == 403 else ERROR
    except TransportError as exc:
        result.status = ERROR
        result.message = str(exc)
    except AlimailError as exc:  # token acquisition failed etc.
        result.status = ERROR
        result.message = str(exc)
    report.results.append(result)


def run(client: Client, email: str | None = None) -> CheckReport:
    """Probe read-only endpoints and return a :class:`CheckReport`."""
    report = CheckReport(email=email)
    _probe(
        report,
        "组织信息",
        "Organization.Read.All",
        "GET",
        "/v2/organization/$current",
        client.organization.get,
    )
    _probe(report, "域名列表", "Domain.Read.All", "GET", "/v2/domains", client.domains.list)
    users = None
    try:
        users = client.users.list(size=5)
        report.results.append(CheckResult("用户列表", "User.Read.All", "GET", "/v2/users"))
    except APIError as exc:
        report.results.append(
            CheckResult(
                "用户列表",
                "User.Read.All",
                "GET",
                "/v2/users",
                DENIED if exc.status == 403 else ERROR,
                exc.status,
                exc.detail_error_code,
                exc.message or "",
            )
        )

    if email is None and isinstance(users, dict):
        for user in users.get("users", []):
            candidate = user.get("email")
            if candidate and user.get("status", "NORMAL") == "NORMAL":
                email = candidate
                report.email = email
                break

    _probe(
        report,
        "根部门子部门",
        "Department.Read.All",
        "GET",
        "/v2/departments/$root/departments",
        lambda: client.departments.children("$root"),
    )
    _probe(report, "邮件组列表", "Group.Read.All", "GET", "/v2/groups", client.groups.list)
    _probe(
        report,
        "域级黑白名单",
        "MessageRule.Read.All",
        "GET",
        "/v2/messageRules/allowBlockLists",
        client.message_rules.allow_block_lists,
    )
    _probe(
        report,
        "审计日志",
        "Report.Read.All",
        "POST",
        "/v2/reports",
        lambda: client.reports.search(
            start="1970-01-01T00:00:00Z", end="1970-01-01T00:00:01Z", size=1
        ),
    )

    if not email:
        report.results.append(
            CheckResult(
                "用户维度测试", "-", "-", "-", ERROR, message="拿不到邮箱地址，请用 --email 指定"
            )
        )
        return report

    _probe(
        report,
        "用户详情",
        "User.Read.All",
        "GET",
        f"/v2/users/{email}",
        lambda: client.users.get(email),
    )
    _probe(
        report,
        "邮件文件夹",
        "Mail.Read.All",
        "GET",
        f"/v2/users/{email}/mailFolders",
        lambda: client.mail.folders(email),
    )
    _probe(
        report,
        "收件箱列表",
        "Mail.Read.All",
        "GET",
        f"/v2/users/{email}/mailFolders/2/messages",
        lambda: client.mail.inbox(email, size=1),
    )
    _probe(
        report,
        "日历列表",
        "Calendar.Read.All",
        "GET",
        f"/v2/users/{email}/calendars",
        lambda: client.calendars.list(email),
    )
    _probe(
        report,
        "隔离区搜索",
        "Quarantine.Read.All",
        "GET",
        f"/v2/users/{email}/quarantine/messages/search",
        lambda: client.quarantine.search(email, size=1),
    )
    _probe(
        report,
        "共享账号",
        "User.Read.All",
        "GET",
        f"/v2/users/{email}/sharedWithMe",
        lambda: client.users.shared_with_me(email),
    )
    return report


def format_report(report: CheckReport) -> str:
    """Render a compact ✅/❌ table."""
    lines = []
    if report.email:
        lines.append(f"账号: {report.email}  通过 {report.passed}/{report.total}")
    else:
        lines.append(f"通过 {report.passed}/{report.total}")
    lines.append("")
    lines.append(f"{'状态':<5}{'接口':<14}{'Scope':<26}说明")
    lines.append("-" * 86)
    for result in report.results:
        if result.passed:
            mark = "✅"
            note = ""
        elif result.status == DENIED:
            mark = "❌"
            note = result.detail_error_code or "accessDenied"
        else:
            mark = "⚠️"
            note = result.detail_error_code or result.message
        lines.append(f"{mark:<5}{result.name:<14}{result.scope:<26}{note}")
    missing = report.missing_scopes()
    if missing:
        lines.append("")
        lines.append("还需在应用里补充的 scope: " + ", ".join(missing))
    return "\n".join(lines)
