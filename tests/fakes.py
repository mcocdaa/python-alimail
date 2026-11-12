"""Deterministic, offline test doubles shared by the alimail test suite.

No real socket is opened and no credential file from the user profile is
touched: every test injects one of these objects instead.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.parse
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alimail._http import RawResponse
from alimail.auth import NullCache
from alimail.client import Client
from alimail.config import Credentials

APP_BASE = "https://api.example.test"
TOKEN_ENDPOINT_SUFFIX = "/oauth2/v2.0/token"
_TESTS_DIR = Path(__file__).resolve().parent


class _TempDir:
    """Minimal fork of ``tempfile.TemporaryDirectory``.

    ``tempfile.mkdtemp`` creates the directory with mode ``0o700``; some
    sandboxed Windows sessions then refuse writes below it.  Creating the
    directory with the default mode avoids that trap while keeping the API
    used by the tests (``name`` / ``cleanup``).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = str(path)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def temp_directory() -> _TempDir:
    """Create a writable temporary directory and return its handle."""
    bases = [Path(tempfile.gettempdir()), _TESTS_DIR / ".tmp"]
    last_error: OSError | None = None
    for base in bases:
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            last_error = exc
            continue
        for _ in range(5):
            path = base / f"alimail-tests-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            try:
                path.mkdir()
                probe = path / "probe.txt"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                return _TempDir(path)
            except OSError as exc:  # pragma: no cover - sandbox dependent
                last_error = exc
                shutil.rmtree(path, ignore_errors=True)
    raise RuntimeError(  # pragma: no cover - sandbox dependent
        f"no writable temporary directory available: {last_error}"
    )


@dataclass(frozen=True)
class RecordedCall:
    """One request captured by :class:`FakeTransport`."""

    method: str
    url: str
    headers: Mapping[str, str] | None = None
    json_body: Any = None
    form: Mapping[str, Any] | None = None
    data: bytes | None = None
    timeout: float | None = None
    verify_ssl: bool = True


def json_response(
    status: int = 200,
    data: Any = None,
    headers: Mapping[str, str] | None = None,
) -> RawResponse:
    """Build a :class:`RawResponse` for the fake transport queue."""
    return RawResponse(status, data, dict(headers or {}))


def url_path(url: str) -> str:
    """Return the path component of *url* (without the query string)."""
    return urllib.parse.urlsplit(url).path


def url_query(url: str) -> dict[str, list[str]]:
    """Parse the query string of *url* keeping blank values."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)


class FakeTransport:
    """Drop-in replacement for :func:`alimail._http.request`.

    * ``responses`` is a FIFO queue of :class:`RawResponse` objects (or
      exceptions, which are raised); when it is exhausted ``default`` is
      returned, so a test that only cares about the request can ignore replies.
    * ``auto_token`` makes the fake answer the OAuth2 token endpoint itself and
      keep token traffic out of ``calls`` (it is recorded in ``token_calls``),
      which keeps request-order assertions easy to read.
    """

    def __init__(
        self,
        responses: Sequence[RawResponse | BaseException] | None = None,
        *,
        auto_token: str | None = None,
        default: RawResponse | None = None,
    ) -> None:
        self._queue: list[RawResponse | BaseException] = list(responses or [])
        self._auto_token = auto_token
        self._default = default if default is not None else RawResponse(200, {})
        self.calls: list[RecordedCall] = []
        self.token_calls: list[RecordedCall] = []

    # -- transport protocol -------------------------------------------
    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any = None,
        form: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
        verify_ssl: bool = True,
    ) -> RawResponse:
        call = RecordedCall(
            method=method.upper(),
            url=url,
            headers=dict(headers) if headers is not None else None,
            json_body=json_body,
            form=dict(form) if form is not None else None,
            data=data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
        if self._auto_token is not None and url.split("?", 1)[0].endswith(TOKEN_ENDPOINT_SUFFIX):
            self.token_calls.append(call)
            return RawResponse(200, {"access_token": self._auto_token, "expires_in": 3600})
        self.calls.append(call)
        item: RawResponse | BaseException = self._queue.pop(0) if self._queue else self._default
        if isinstance(item, BaseException):
            raise item
        return item

    # -- assertions helpers ------------------------------------------
    def push(self, *responses: RawResponse | BaseException) -> None:
        """Append responses to the queue."""
        self._queue.extend(responses)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def pending(self) -> int:
        """Number of queued responses that were not consumed."""
        return len(self._queue)

    @property
    def urls(self) -> list[str]:
        return [call.url for call in self.calls]

    @property
    def last_call(self) -> RecordedCall:
        return self.calls[-1]


class RecordingCache:
    """In-memory token cache that records every operation."""

    def __init__(self, data: Mapping[str, dict[str, Any]] | None = None) -> None:
        self.data: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (data or {}).items()}
        self.gets: list[str] = []
        self.sets: list[tuple[str, dict[str, Any]]] = []
        self.deletes: list[str] = []

    def get(self, key: str) -> dict[str, Any] | None:
        self.gets.append(key)
        value = self.data.get(key)
        return dict(value) if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.sets.append((key, dict(value)))
        self.data[key] = dict(value)

    def delete(self, key: str) -> None:
        self.deletes.append(key)
        self.data.pop(key, None)


class FakeClock:
    """Injectable monotonic wall clock for token expiry tests."""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_client(
    responses: Sequence[RawResponse | BaseException] | None = None,
    *,
    auth: str = "app",
    token: str = "test-access-token",
    base: str = APP_BASE,
    email: str | None = None,
    credentials: Credentials | None = None,
    **client_kwargs: Any,
) -> tuple[Client, FakeTransport]:
    """Build a :class:`Client` wired to a :class:`FakeTransport`.

    With ``auth="app"`` the OAuth2 token endpoint is answered automatically so
    ``transport.calls`` only contains API requests.  With ``auth="mcp"`` the
    client uses the personal token directly and no token request is issued.
    """
    auto_token = token if (credentials is None and auth == "app") else None
    transport = FakeTransport(responses, auto_token=auto_token)
    if credentials is None:
        if auth == "app":
            credentials = Credentials(
                base=base,
                app_id="test-app-id",
                app_secret="test-app-secret",
                email=email,
            )
        else:
            credentials = Credentials(base=base, token=token, email=email)
    client_kwargs.setdefault("cache", NullCache())
    client = Client(credentials=credentials, transport=transport, **client_kwargs)
    return client, transport


__all__ = [
    "APP_BASE",
    "FakeClock",
    "FakeTransport",
    "RecordingCache",
    "RecordedCall",
    "TOKEN_ENDPOINT_SUFFIX",
    "json_response",
    "make_client",
    "url_path",
    "url_query",
]
