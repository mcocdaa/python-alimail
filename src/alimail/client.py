"""The :class:`Client` object: authentication, requests, pagination and resources."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator, Mapping
from typing import Any

from . import _http
from .auth import FileTokenCache, TokenCache, TokenManager, Transport
from .config import Credentials, load_credentials
from .errors import error_from_response

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF = 0.5


class Client:
    """Client for the Alibaba Mail OpenAPI.

    Parameters
    ----------
    app_id, app_secret:
        Application credentials created in the mailbox admin console
        (高级应用 / API 开放平台).  Usually supplied through environment
        variables or ``alimail_creds.json`` instead.
    token:
        Personal MCP token; when present it is used directly as a bearer
        token instead of the OAuth2 client-credentials flow.
    base:
        API host, defaults to ``https://alimail-cn.aliyuncs.com``.  Overseas
        tenants usually use ``https://alimail-sg.aliyuncs.com``.
    cache:
        Token cache implementation; defaults to a JSON file in the user cache
        directory (see :func:`alimail.config.token_cache_path`).
    transport:
        Callable used for HTTP requests; inject a fake for tests.
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        *,
        base: str | None = None,
        token: str | None = None,
        email: str | None = None,
        credentials: Credentials | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        cache: TokenCache | None = None,
        transport: Transport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff: float = DEFAULT_BACKOFF,
        verify_ssl: bool = True,
    ) -> None:
        self.credentials = credentials or load_credentials(
            app_id=app_id,
            app_secret=app_secret,
            base=base,
            token=token,
            email=email,
        )
        self.email = self.credentials.email
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff = backoff
        self.verify_ssl = verify_ssl
        self._transport: Transport = transport or _http.request
        self._tokens = TokenManager(
            self.credentials,
            cache=cache if cache is not None else FileTokenCache(),
            transport=self._transport,
            timeout=timeout,
            verify_ssl=self.verify_ssl,
        )
        self._init_resources()

    # ------------------------------------------------------------------
    # constructors
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, **kwargs: Any) -> Client:
        """Build a client from environment variables / credential files."""
        return cls(**kwargs)

    @classmethod
    def from_mcp_token(cls, token: str, *, email: str | None = None, **kwargs: Any) -> Client:
        """Build a client that authenticates with a personal MCP token."""
        return cls(token=token, email=email, **kwargs)

    # ------------------------------------------------------------------
    # authentication
    # ------------------------------------------------------------------
    @property
    def base(self) -> str:
        """Effective API host (may switch to the fallback host after a token fetch)."""
        return self._tokens.base

    @property
    def mode(self) -> str:
        return self.credentials.mode

    def token(self, force: bool = False) -> str:
        """Return a valid bearer token, refreshing it when needed."""
        return self._tokens.get(force=force)

    def invalidate_token(self) -> None:
        self._tokens.invalidate()

    # ------------------------------------------------------------------
    # requests
    # ------------------------------------------------------------------
    def raw(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        form: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> _http.RawResponse:
        """Send a request and return the raw response without raising on 4xx/5xx."""
        method = method.upper()
        idempotent = method in ("GET", "HEAD", "OPTIONS")
        attempts = 0
        refreshed = False
        while True:
            request_headers = {
                "Authorization": f"Bearer {self.token()}",
                "Accept": "application/json",
            }
            if headers:
                request_headers.update(headers)
            url = _http.build_url(self.base, path, params)
            try:
                response = self._transport(
                    method,
                    url,
                    headers=request_headers,
                    json_body=json,
                    form=form,
                    data=data,
                    timeout=self.timeout if timeout is None else timeout,
                    verify_ssl=self.verify_ssl,
                )
            except Exception as exc:  # noqa: BLE001 - transport errors are retried below
                from .errors import TransportError

                if not isinstance(exc, TransportError):
                    raise
                # Never retry a non-idempotent request on a transport failure:
                # the server may already have processed it (e.g. sending mail).
                if not idempotent or attempts >= self.max_retries:
                    raise
                attempts += 1
                time.sleep(self.backoff * (2 ** (attempts - 1)))
                continue

            if response.status == 401 and self.mode == "app" and not refreshed:
                refreshed = True
                self._tokens.invalidate()
                continue

            if (
                response.status == 429 or (response.status >= 500 and idempotent)
            ) and attempts < self.max_retries:
                delay = self.backoff * (2**attempts)
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    with contextlib.suppress(ValueError):
                        delay = max(delay, float(retry_after))
                attempts += 1
                time.sleep(delay)
                continue

            return response

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        form: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Send a request, raising :class:`alimail.errors.APIError` on failure."""
        response = self.raw(
            method,
            path,
            params=params,
            json=json,
            form=form,
            data=data,
            headers=headers,
            timeout=timeout,
        )
        if not response.ok:
            raise error_from_response(
                response.status, response.data, method=method.upper(), path=path
            )
        return response.data

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def paginate(
        self,
        method: str,
        path: str,
        *,
        item_key: str | None = None,
        cursor_key: str = "nextCursor",
        params: Mapping[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> Iterator[Any]:
        """Iterate over all items of a cursor-paginated endpoint."""
        query = dict(params or {})
        seen: set[str] = set()
        pages = 0
        while True:
            data = self.request(method, path, params=query)
            if item_key is None:
                if isinstance(data, dict):
                    items = next((v for v in data.values() if isinstance(v, list)), [])
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
            else:
                items = data.get(item_key, []) if isinstance(data, dict) else []
            yield from items or []
            pages += 1
            if max_pages is not None and pages >= max_pages:
                return
            cursor = data.get(cursor_key) if isinstance(data, dict) else None
            if not cursor or cursor in seen:
                return
            seen.add(str(cursor))
            query["cursor"] = cursor

    def call(
        self,
        name: str,
        *,
        path: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        json: Any = None,
        **query_kwargs: Any,
    ) -> Any:
        """Call any of the 112 documented operations by name.

        ``path`` fills path placeholders, ``query``/keyword arguments become
        query parameters and ``json`` is sent as the request body.  Operation
        names are listed by ``alimail ops list`` or
        :func:`alimail.operations.all_operations`.
        """
        from .operations import get_operation

        operation = get_operation(name)
        path_params = dict(path or {})
        merged_query = dict(query or {})
        merged_query.update({k: v for k, v in query_kwargs.items() if v is not None})
        for placeholder in operation.path_params:
            if placeholder in merged_query:
                path_params[placeholder] = merged_query.pop(placeholder)
        resolved = operation.build_path(path_params)
        return self.request(
            operation.method,
            resolved,
            params=merged_query or None,
            json=json,
        )

    # ------------------------------------------------------------------
    # resources
    # ------------------------------------------------------------------
    def _init_resources(self) -> None:
        from .resources.calendars import CalendarsResource
        from .resources.directory import (
            ContactsResource,
            DepartmentsResource,
            DomainsResource,
            GroupsResource,
            OrganizationResource,
        )
        from .resources.mail import MailResource
        from .resources.security import MessageRulesResource, QuarantineResource, ReportsResource
        from .resources.stream import StreamResource
        from .resources.users import UsersResource

        self.users = UsersResource(self)
        self.mail = MailResource(self)
        self.calendars = CalendarsResource(self)
        self.organization = OrganizationResource(self)
        self.domains = DomainsResource(self)
        self.departments = DepartmentsResource(self)
        self.groups = GroupsResource(self)
        self.contacts = ContactsResource(self)
        self.quarantine = QuarantineResource(self)
        self.message_rules = MessageRulesResource(self)
        self.reports = ReportsResource(self)
        self.stream = StreamResource(self)

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release resources (kept for API symmetry; nothing to close today)."""

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
