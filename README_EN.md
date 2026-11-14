# python-alimail

English | [简体中文](README.md)

[![CI](https://github.com/mcocdaa/python-alimail/actions/workflows/ci.yml/badge.svg)](https://github.com/mcocdaa/python-alimail/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/alimail.svg)](https://pypi.org/project/alimail/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**Unofficial** Python SDK and CLI for the [Alibaba Mail (Alibaba Enterprise Mail / 阿里邮箱)](https://mailhelp.aliyun.com/docs/) OpenAPI v2.
Zero runtime dependencies (Python standard library only), 112 documented operations, and built-in OAuth2 scope diagnostics.

> **Unofficial Notice**
> This is an independent open-source project and is **not affiliated with, endorsed by, or sponsored by** Alibaba Cloud or Alibaba Mail.
> Official documentation is the source of truth for API behavior. No official logos or trademarks are included.
> Always validate in a test tenant before running write operations in production.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Authentication Modes & Credential Discovery](#authentication-modes--credential-discovery)
- [Quickstart](#quickstart)
- [Python API Overview](#python-api-overview)
- [CLI Reference](#cli-reference)
- [Permission Matrix & Self-Check](#permission-matrix--self-check)
- [Architecture](#architecture)
- [Common Pitfalls](#common-pitfalls)
- [Development & Testing](#development--testing)
- [License](#license)

---

## Features

| Feature | Details |
|---|---|
| Zero runtime dependencies | Pure Python standard library (`urllib.request`, `json`, `ssl`, `argparse`); no third-party runtime packages |
| 112 OpenAPI operations | Full registry covering organization, domains, users, departments, groups, shared contacts, mail, calendars, quarantine, message rules, audit reports, and file streaming |
| Dual authentication modes | Enterprise application (`app_id` / `app_secret` via OAuth2 `client_credentials`) and personal MCP token |
| Built-in permission self-check | `alimail check` probes 13 read-only endpoints and renders a per-scope ✅/❌/⚠️ matrix (supports `--json` output and exit code `3` on missing scopes) |
| Silent CN -> SG host fallback | Automatically falls back from `https://alimail-cn.aliyuncs.com` to `https://alimail-sg.aliyuncs.com` on default host token failure |
| Hardened token cache | Atomic `0o600` temp-file + replace writes inside a `0o700` directory (`FileTokenCache`), plus automatic refresh 120s before expiry and single retry on `401` |
| Typed error hierarchy | `APIError` subclasses (`AuthError`, `PermissionDenied`, `NotFound`, `RateLimitError`, `ServerError`), `TransportError`, and `ConfigError` |
| Python SDK + CLI | Same client powers programmatic automation (`Client`) and terminal workflows (`alimail`) |
| Offline test suite | All unit tests run offline with mocked HTTP transports and zero real credentials |

---

## Installation

Requires **Python >= 3.10**.

```bash
pip install alimail
```

Install from source for development:

```bash
git clone https://github.com/mcocdaa/python-alimail.git
cd python-alimail
pip install -e ".[dev]"
```

---

## Authentication Modes & Credential Discovery

### Mode 1: Enterprise Application (OAuth2 `client_credentials`)

Recommended for organization-wide automation (requires an admin account on Standard, AI Premium, or Localization editions; Free edition does not include API Open Platform):

```bash
export ALIMAIL_APP_ID="your-app-id"
export ALIMAIL_APP_SECRET="your-app-secret"
export ALIMAIL_BASE="https://alimail-cn.aliyuncs.com"  # or https://alimail-sg.aliyuncs.com
```

### Mode 2: Personal MCP Token (Single Mailbox, AI Premium Edition)

Generated in Webmail under Settings -> AI -> MCP Service:

```bash
export ALIMAIL_MCP_TOKEN="your-mcp-token"
export ALIMAIL_EMAIL="user@example.com"
```

### Credential Resolution Order

Credentials are resolved in the following order (first match wins):

1. Explicit `Client(...)` constructor arguments or CLI flags (`--app-id`, `--app-secret`, `--base`)
2. Environment variables (`ALIMAIL_APP_ID` / `ALIMAIL_APP_SECRET`, or `ALIMAIL_MCP_TOKEN`, plus `ALIMAIL_BASE`, `ALIMAIL_EMAIL`)
3. Project-local file `./alimail_creds.json` (git-ignored)
4. User config file `~/.alimail/creds.json`
5. Personal MCP accounts file (`%APPDATA%\Alimail\accounts.json` on Windows, `~/.alimail/accounts.json` elsewhere)

See [docs/quickstart.md](docs/quickstart.md) for step-by-step setup instructions.

---

## Quickstart

### Python

```python
from alimail import Client

client = Client.from_env()
print(client.token()[:8] + "...")
print(client.users.list(size=5))
print(client.mail.inbox("user@example.com", size=5))
```

Or with a personal MCP token:

```python
from alimail import Client

client = Client.from_mcp_token("your-mcp-token", email="user@example.com")
print(client.mail.inbox("user@example.com", size=5))
```

### CLI

```bash
# 1. Verify credentials and acquire/cache a token
alimail token

# 2. Run read-only permission self-check
alimail check --email user@example.com

# 3. Read the 5 most recent inbox messages
alimail inbox --email user@example.com --size 5
```

---

## Python API Overview

### Resource Methods

| Capability | Example |
|---|---|
| Acquire / verify token | `client.token(force=False)` |
| Organization info | `client.organization.get()` |
| Domains | `client.domains.list()` |
| Users (list / get) | `client.users.list(size=10)` / `client.users.get("user@example.com")` |
| Departments | `client.departments.children("$root")` |
| Groups | `client.groups.list()` |
| Shared contacts | `client.contacts.folders()` / `client.contacts.contacts(folder_id)` |
| Mail folders & inbox | `client.mail.folders("user@example.com")` / `client.mail.inbox("user@example.com", size=20)` |
| Read & search messages | `client.mail.message("user@example.com", message_id)` / `client.mail.search("user@example.com", query="subject:hello")` |
| Drafts & send (2-step) | `client.mail.create_draft(...)` / `client.mail.send("user@example.com", to=["a@example.com"], subject="Hi", text="Body")` |
| Batch delete / move / mark read | `client.mail.delete(...)` / `client.mail.move(...)` / `client.mail.mark_read(...)` |
| Calendars & events | `client.calendars.list("user@example.com")` / `client.calendars.events("user@example.com", calendar_id)` |
| Quarantine & message rules | `client.quarantine.search("user@example.com", size=20)` / `client.message_rules.allow_block_lists()` |
| Audit reports | `client.reports.search(start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z")` |

### Low-Level & Generic Methods

| Method | Description |
|---|---|
| `client.request(method, path, ...)` | Send an authenticated request, decode JSON, and raise typed `APIError` on non-2xx |
| `client.raw(method, path, ...)` | Return `RawResponse(status, data, headers)` without raising on HTTP error statuses |
| `client.paginate(method, path, item_key=...)` | Lazy cursor-pagination iterator following `nextCursor` |
| `client.call(operation_name, path=..., query=..., json=...)` | Invoke any of the 112 operations by friendly name or `operationId` |

### Exception Hierarchy

```python
from alimail import (
    APIError,
    AuthError,  # 401
    PermissionDenied,  # 403
    NotFound,  # 404
    RateLimitError,  # 429 (40 req/s domain limit)
    ServerError,  # 5xx
    TransportError,  # Network / TLS / timeout
    ConfigError,  # Missing credentials
)
```

---

## CLI Reference

```bash
alimail token [--force]                              # Acquire/inspect bearer token
alimail org                                          # Get current organization info
alimail users [--size 20] [--filter "(email=*)"]     # List users
alimail folders --email user@example.com             # List mail folders
alimail inbox --email user@example.com [--size 10]   # List inbox messages
alimail read <message-id> --email user@example.com   # Read one message
alimail search --email user@example.com [--size 20] "subject:hello"
alimail send --from user@example.com --to a@example.com \
  --subject "Hi" --text "Body" [--html "..."] [--yes] # Dry-run by default; requires --yes to send
alimail check [--email user@example.com]             # Run read-only permission self-check
alimail call <operation-name> [--path k=v ...] [--query k=v ...] [--json-body '{"k":"v"}']
alimail ops [list] [--grep keyword] [--tag category] # List 112 operations
alimail ops show <operation-name>                    # Inspect operation metadata and scopes
alimail raw GET /v2/domains [--query k=v ...] [--json-body '{"k":"v"}']
```

Global options: `--app-id`, `--app-secret`, `--base`, `--timeout`, `--json`, `--version`.

---

## Permission Matrix & Self-Check

Alibaba Mail OpenAPI defines **27 OAuth scopes**. Run `alimail check` to probe 13 read-only endpoints and verify which scopes are active (pass `--json` for machine-readable output):

```bash
alimail check --email user@example.com
alimail --json check --email user@example.com
```

Exit codes: `0` when all probes pass, `3` (`EXIT_DENIED`) when one or more probes are denied or errored.

Key scope groups (see [docs/permissions.md](docs/permissions.md) for the complete 27-scope reference):

| Scope | Coverage |
|---|---|
| `Organization.Read.All` / `Organization.ReadWrite.All` | Organization metadata (`GET /v2/organization/$current`) |
| `Domain.Read.All` / `Domain.ReadWrite.All` | Domain listing, verification, management |
| `User.Read.All` / `User.Write.All` / `User.ReadWrite.All` | User directory, details, `sharedWithMe` |
| `Department.Read.All` / `Department.ReadWrite.All` | Department tree (`$root`) and hierarchy |
| `Group.Read.All` / `Group.ReadWrite.All` | Mail groups and memberships |
| `SharedContact.Read.All` / `SharedContact.ReadWrite.All` | Public shared contacts and folders |
| `Mail.Read.All` / `Mail.ReadWrite.All` / `Mail.Send.All` | Reading mail, folders/drafts/mutations, sending mail |
| `Calendar.Read.All` / `Calendar.ReadWrite.All` | Calendars, events, free/busy schedule |
| `Quarantine.Read.All` / `Quarantine.ReadWrite.All` | Quarantine search, inspection, release |
| `MessageRule.Read.All` / `MessageRule.Write.All` / `MessageRule.ReadWrite.All` | Domain-level allow/block lists |
| `Report.Read.All` | Audit logs (`POST /v2/reports`) |
| `ConditionalAccessPolicy.Read.All` / `ConditionalAccessPolicy.ReadWrite.All` | Conditional access policies |

---

## Architecture

```text
src/alimail/
├── __init__.py        # Public exports (Client, Credentials, errors, operations)
├── _http.py           # Standard-library urllib HTTP transport + gzip/JSON decoding + verify_ssl
├── auth.py            # FileTokenCache (0o700 dir / atomic 0o600 file), NullCache, TokenManager (CN->SG fallback)
├── config.py          # Multi-source credential discovery & platform cache path resolution
├── client.py          # Client: auth refresh, retries/backoff, pagination, operation dispatch
├── errors.py          # AlimailError, ConfigError, TransportError, APIError hierarchy
├── operations.py      # 112-operation registry backed by operations.json + difflib suggestions
├── check.py           # Read-only 13-probe permission diagnostics (run & format_report)
├── cli.py             # argparse CLI (`alimail`) with human & compact `--json` formatting
└── resources/
    ├── users.py       # UsersResource
    ├── mail.py        # MailResource (INBOX_FOLDER_ID = "2", two-step send)
    ├── calendars.py   # CalendarsResource
    ├── directory.py   # Organization, Domains, Departments, Groups, Contacts resources
    ├── security.py    # Quarantine, MessageRules, Reports resources
    └── stream.py      # StreamResource (binary chunk upload)
```

---

## Common Pitfalls

1. **Pagination uses `size`, not `limit`**: `GET /v2/users?limit=10` returns an empty `users` array even when `total > 0`. Use `client.users.list(size=10)`.
2. **Numeric `folderId`**: Mail folder endpoints require numeric IDs (`INBOX_FOLDER_ID = "2"`), not display names. Use `client.mail.inbox(...)` or `client.mail.find_folder_id(...)`.
3. **`/v2/users/$current` is not supported**: Pass an explicit email address (`$current` only works on `/v2/organization/$current`).
4. **Refresh token after adding scopes**: Existing tokens do not inherit newly added scopes; run `alimail token --force` or `client.token(force=True)`.
5. **Two-step send flow**: Sending mail creates a draft first and then calls `POST .../messages/{id}/send` (handled automatically by `client.mail.send()`).

See [docs/pitfalls.md](docs/pitfalls.md) for all 10 field-verified notes.

---

## Development & Testing

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
pytest -v
```

All tests use `FakeTransport` and temporary directories — no network calls or live credentials are required. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

---

## License

[MIT](LICENSE) © 2026 mcocdaa and contributors
