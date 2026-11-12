"""Minimal HTTP transport built on the standard library.

Only ``urllib.request`` is used so that the package keeps zero runtime
dependencies.  The transport is injectable on :class:`alimail.client.Client`
which makes it easy to unit test without touching the network.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import TransportError

USER_AGENT = "python-alimail/0.1.0 (+https://github.com/mcocdaa/python-alimail)"


@dataclass
class RawResponse:
    """A transport level response: status, decoded payload and headers."""

    status: int
    data: Any
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def build_url(base: str, path: str, params: Mapping[str, Any] | None = None) -> str:
    """Join *base* and *path* and append a query string when *params* is given."""
    base = base.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    url = base + path
    if not params:
        return url
    clean = {k: v for k, v in params.items() if v is not None}
    if not clean:
        return url
    query = urllib.parse.urlencode(clean, doseq=True)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def _decode_body(data: bytes, headers: Mapping[str, str]) -> Any:
    if not data:
        return None
    encoding = (headers.get("content-encoding") or "").lower()
    if encoding == "gzip":
        with contextlib.suppress(OSError):  # pragma: no cover - server lied about encoding
            data = gzip.decompress(data)
    content_type = (headers.get("content-type") or "").lower()
    if "json" in content_type or data[:1] in (b"{", b"["):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:  # pragma: no cover - binary payloads
        return data


def request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    json_body: Any = None,
    form: Mapping[str, Any] | None = None,
    data: bytes | None = None,
    timeout: float = 30.0,
    user_agent: str = USER_AGENT,
    verify_ssl: bool = True,
) -> RawResponse:
    """Perform one HTTP request and return a :class:`RawResponse`.

    Network level failures raise :class:`alimail.errors.TransportError`; HTTP
    error statuses are returned normally so the caller can map them to the
    right exception type.
    """
    request_headers = {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if headers:
        request_headers.update(headers)

    body: bytes | None = data
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        body = urllib.parse.urlencode(form).encode("ascii")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
    context = None if verify_ssl else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
            resp_headers = {k.lower(): v for k, v in response.headers.items()}
            return RawResponse(response.status, _decode_body(raw, resp_headers), resp_headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        resp_headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return RawResponse(exc.code, _decode_body(raw, resp_headers), resp_headers)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError(f"{method.upper()} {url} failed: {exc}") from exc
