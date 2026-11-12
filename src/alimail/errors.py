"""Error hierarchy for the Alimail OpenAPI client."""

from __future__ import annotations

from typing import Any


class AlimailError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(AlimailError):
    """Raised when no usable credentials are configured."""


class TransportError(AlimailError):
    """Raised when the HTTP request never produced a response (DNS, TLS, timeout...)."""


class APIError(AlimailError):
    """Raised when the API answered with a non-2xx status."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        detail_error_code: str | None = None,
        developer_message: str | None = None,
        payload: Any = None,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.detail_error_code = detail_error_code
        self.developer_message = developer_message
        self.payload = payload
        self.method = method
        self.path = path
        super().__init__(self.__str__())

    def __str__(self) -> str:
        parts = [f"HTTP {self.status}"]
        if self.detail_error_code:
            parts.append(self.detail_error_code)
        if self.message:
            parts.append(self.message)
        text = " | ".join(parts)
        if self.method and self.path:
            text = f"{text} ({self.method} {self.path})"
        return text


class AuthError(APIError):
    """401 - token missing, expired or rejected."""


class PermissionDenied(APIError):
    """403 - the application does not hold the required scope."""


class NotFound(APIError):
    """404 - the requested resource does not exist."""


class RateLimitError(APIError):
    """429 - rate limit hit (40 requests/second/domain by default)."""


class ServerError(APIError):
    """5xx - the service failed."""


def error_from_response(
    status: int,
    payload: Any,
    *,
    method: str | None = None,
    path: str | None = None,
) -> APIError:
    """Build the most specific exception for a non-2xx response."""
    detail = message = developer = None
    if isinstance(payload, dict):
        detail = payload.get("detailErrorCode")
        message = payload.get("message")
        developer = payload.get("developerMessage")
    if not message:
        message = "request failed"
    kwargs = {
        "detail_error_code": detail,
        "developer_message": developer,
        "payload": payload,
        "method": method,
        "path": path,
    }
    if status == 401:
        return AuthError(status, message, **kwargs)
    if status == 403:
        return PermissionDenied(status, message, **kwargs)
    if status == 404:
        return NotFound(status, message, **kwargs)
    if status == 429:
        return RateLimitError(status, message, **kwargs)
    if status >= 500:
        return ServerError(status, message, **kwargs)
    return APIError(status, message, **kwargs)
