"""Credential discovery for the Alimail OpenAPI client.

Resolution order (first hit wins):

1. explicit arguments
2. environment variables
3. ``./alimail_creds.json`` (project-local, git-ignored)
4. ``~/.alimail/creds.json``
5. personal MCP account file (``%APPDATA%\\Alimail\\accounts.json`` on
   Windows, ``~/.alimail/accounts.json`` elsewhere)

Application credentials look like ``{"app_id": "...", "app_secret": "..."}``;
the personal access variant is
``{"accounts": [{"email": "...", "token": "...", "baseUrl": "..."}]}``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError

DEFAULT_BASE = "https://alimail-cn.aliyuncs.com"
SG_BASE = "https://alimail-sg.aliyuncs.com"
CREDS_FILENAME = "alimail_creds.json"

_REGISTRATION_HINT = (
    "没有找到可用的阿里邮箱凭据。任选一种方式配置：\n"
    "  A) 企业应用（推荐，需管理员在 邮箱管理后台 → 高级应用 → API 开放平台 创建应用）：\n"
    "     export ALIMAIL_APP_ID=...\n"
    "     export ALIMAIL_APP_SECRET=...\n"
    "     或写入 ./alimail_creds.json："
    '{"app_id": "...", "app_secret": "...", "base": "https://alimail-cn.aliyuncs.com"}\n'
    "  B) 个人 MCP token（需邮箱版本支持）：\n"
    "     export ALIMAIL_MCP_TOKEN=... ALIMAIL_EMAIL=you@example.com\n"
    "     或写入 ~/.alimail/accounts.json："
    '{"accounts": [{"email": "...", "token": "...", "baseUrl": "..."}]}'
)


@dataclass(frozen=True)
class Credentials:
    """Resolved credentials for one caller."""

    base: str = DEFAULT_BASE
    app_id: str | None = None
    app_secret: str | None = None
    token: str | None = None
    email: str | None = None
    source: str = ""

    @property
    def mode(self) -> str:
        """``"app"`` for application credentials, ``"mcp"`` for a bearer token."""
        if self.app_id and self.app_secret:
            return "app"
        if self.token:
            return "mcp"
        return "none"

    @property
    def base_is_default(self) -> bool:
        return self.base == DEFAULT_BASE


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _accounts_paths(home: Path | None = None) -> list[Path]:
    home = home or _home()
    paths = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "Alimail" / "accounts.json")
    paths.append(home / ".alimail" / "accounts.json")
    return paths


def _from_accounts_file(path: Path, email: str | None = None) -> Credentials | None:
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    accounts = data.get("accounts") or []
    if not isinstance(accounts, list) or not accounts:
        return None
    chosen = accounts[0]
    if email:
        for account in accounts:
            if str(account.get("email", "")).lower() == email.lower():
                chosen = account
                break
    if not isinstance(chosen, dict) or not chosen.get("token"):
        return None
    return Credentials(
        base=str(chosen.get("baseUrl") or DEFAULT_BASE).rstrip("/"),
        token=str(chosen["token"]),
        email=chosen.get("email") or email,
        source=str(path),
    )


def load_credentials(
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    base: str | None = None,
    token: str | None = None,
    email: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Credentials:
    """Resolve credentials using the documented order."""
    env = env if env is not None else os.environ
    cwd = cwd or Path.cwd()
    home = home or _home()

    email = email or env.get("ALIMAIL_EMAIL")
    base = (base or env.get("ALIMAIL_BASE") or "").rstrip("/") or None

    # 1) explicit arguments win over everything else
    if token:
        return Credentials(
            base=base or DEFAULT_BASE, token=token, email=email, source="arguments/env"
        )
    if app_id and app_secret:
        return Credentials(
            base=base or DEFAULT_BASE,
            app_id=app_id,
            app_secret=app_secret,
            email=email,
            source="arguments/env",
        )

    # 2) environment variables (application credentials, then a personal token)
    env_app_id = env.get("ALIMAIL_APP_ID")
    env_app_secret = env.get("ALIMAIL_APP_SECRET")
    if env_app_id and env_app_secret:
        return Credentials(
            base=base or DEFAULT_BASE,
            app_id=env_app_id,
            app_secret=env_app_secret,
            email=email,
            source="arguments/env",
        )
    env_token = env.get("ALIMAIL_MCP_TOKEN")
    if env_token:
        return Credentials(
            base=base or DEFAULT_BASE, token=env_token, email=email, source="arguments/env"
        )

    # 2) project-local credentials file
    local = cwd / CREDS_FILENAME
    data = _read_json(local)
    if isinstance(data, dict) and (data.get("app_id") or data.get("token")):
        if data.get("token"):
            return Credentials(
                base=str(base or data.get("base") or DEFAULT_BASE).rstrip("/"),
                token=str(data["token"]),
                email=email or data.get("email"),
                source=str(local),
            )
        return Credentials(
            base=str(base or data.get("base") or DEFAULT_BASE).rstrip("/"),
            app_id=str(data.get("app_id")),
            app_secret=str(data.get("app_secret") or ""),
            email=email or data.get("email"),
            source=str(local),
        )

    # 3) user credentials file
    user_file = home / ".alimail" / "creds.json"
    data = _read_json(user_file)
    if isinstance(data, dict) and (data.get("app_id") or data.get("token")):
        if data.get("token"):
            return Credentials(
                base=str(base or data.get("base") or DEFAULT_BASE).rstrip("/"),
                token=str(data["token"]),
                email=email or data.get("email"),
                source=str(user_file),
            )
        return Credentials(
            base=str(base or data.get("base") or DEFAULT_BASE).rstrip("/"),
            app_id=str(data.get("app_id")),
            app_secret=str(data.get("app_secret") or ""),
            email=email or data.get("email"),
            source=str(user_file),
        )

    # 4) personal MCP account file
    for path in _accounts_paths(home):
        creds = _from_accounts_file(path, email)
        if creds is not None:
            if base:
                creds = Credentials(
                    base=base,
                    token=creds.token,
                    email=creds.email,
                    source=creds.source,
                )
            return creds

    raise ConfigError(_REGISTRATION_HINT)


def token_cache_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """Return the platform specific cache file used for access tokens."""
    env = env if env is not None else os.environ
    home = home or _home()
    local = env.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "alimail" / "token-cache.json"
    cache_home = env.get("XDG_CACHE_HOME")
    if cache_home:
        return Path(cache_home) / "alimail" / "token-cache.json"
    return home / ".cache" / "alimail" / "token-cache.json"
