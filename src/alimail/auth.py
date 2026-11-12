"""OAuth2 client-credentials token handling with an on-disk cache."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from . import _http
from .config import SG_BASE, Credentials, token_cache_path
from .errors import AlimailError, TransportError

Transport = Callable[..., _http.RawResponse]


class TokenCache(Protocol):
    """Pluggable cache used by :class:`TokenManager`."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...

    def delete(self, key: str) -> None: ...


class NullCache:
    """Cache that never stores anything (useful for tests)."""

    def get(self, key: str) -> dict[str, Any] | None:
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        return None

    def delete(self, key: str) -> None:
        return None


class FileTokenCache:
    """JSON file cache; writes atomically and never raises on IO errors."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else token_cache_path()
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._load().get(key)
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[key] = value
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                pass

    def delete(self, key: str) -> None:
        with self._lock:
            data = self._load()
            if key in data:
                data.pop(key)
                with contextlib.suppress(OSError):
                    self.path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )

    def clear(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink()


def cache_key(credentials: Credentials) -> str:
    """Cache entries are scoped by application and base URL."""
    return f"{credentials.app_id or 'mcp'}@{credentials.base}"


class TokenManager:
    """Obtain, cache and refresh application access tokens."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        cache: TokenCache | None = None,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.time,
        skew: float = 120.0,
        timeout: float = 30.0,
    ) -> None:
        self.credentials = credentials
        self.cache = cache if cache is not None else FileTokenCache()
        self.transport = transport or _http.request
        self.clock = clock
        self.skew = skew
        self.timeout = timeout
        self.base = credentials.base
        self._token: str | None = credentials.token if credentials.mode == "mcp" else None
        self._expires_at = float("inf") if self._token else 0.0
        self._lock = threading.Lock()

    def get(self, force: bool = False) -> str:
        """Return a valid token, refreshing it when needed."""
        if self.credentials.mode == "mcp":
            assert self._token is not None
            return self._token
        if self.credentials.mode != "app":
            raise AlimailError("credentials do not support token acquisition")
        with self._lock:
            if not force and self._token and self._expires_at > self.clock() + self.skew:
                return self._token
            cached = None if force else self.cache.get(cache_key(self.credentials))
            if cached and float(cached.get("expires_at", 0)) > self.clock() + self.skew:
                self._token = str(cached["access_token"])
                self._expires_at = float(cached["expires_at"])
                self.base = str(cached.get("base") or self.credentials.base)
                return self._token
            token, expires_in, base = self._fetch()
            self._token = token
            self.base = base
            self._expires_at = self.clock() + expires_in
            self.cache.set(
                cache_key(self.credentials),
                {
                    "access_token": token,
                    "expires_at": self._expires_at,
                    "base": base,
                    "app_id": self.credentials.app_id,
                },
            )
            return token

    def invalidate(self) -> None:
        """Drop the cached token.  A personal MCP token cannot be refreshed,
        so invalidation is a no-op in that mode."""
        if self.credentials.mode == "mcp":
            return
        self._token = None
        self._expires_at = 0.0
        if self.credentials.mode == "app":
            self.cache.delete(cache_key(self.credentials))

    def _fetch(self) -> tuple[str, float, str]:
        assert self.credentials.app_id and self.credentials.app_secret
        bases = [self.credentials.base]
        if self.credentials.base_is_default:
            bases.append(SG_BASE)
        last_error: str | None = None
        for base in bases:
            try:
                response = self.transport(
                    "POST",
                    base + "/oauth2/v2.0/token",
                    headers={"Accept": "application/json"},
                    form={
                        "grant_type": "client_credentials",
                        "client_id": self.credentials.app_id,
                        "client_secret": self.credentials.app_secret,
                    },
                    timeout=self.timeout,
                )
            except TransportError as exc:
                last_error = f"{base}: {exc}"
                continue
            if (
                response.ok
                and isinstance(response.data, dict)
                and response.data.get("access_token")
            ):
                payload: Mapping[str, Any] = response.data
                expires_in = float(payload.get("expires_in") or 3600)
                return str(payload["access_token"]), expires_in, base
            last_error = f"{base}: HTTP {response.status} {response.data!r}"
        raise AlimailError(f"failed to obtain access token ({last_error})")
