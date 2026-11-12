"""Security related resources: quarantine, message rules, audit reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import q


class QuarantineResource:
    """``/v2/users/{email}/quarantine/messages``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def search(self, email: str, **params: Any) -> dict[str, Any]:
        """Search quarantine messages; query parameters are passed through."""
        return self._client.request(
            "GET", f"/v2/users/{q(email)}/quarantine/messages/search", params=dict(params)
        )

    def get(self, email: str, message_id: str) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/users/{q(email)}/quarantine/messages/{q(message_id)}"
        )

    def attachments(self, email: str, message_id: str) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/users/{q(email)}/quarantine/messages/{q(message_id)}/attachments"
        )

    def release(
        self, email: str, message_id: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Release a quarantined message back to the inbox (write operation)."""
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/quarantine/messages/{q(message_id)}/release",
            json=dict(payload or {}),
        )


class MessageRulesResource:
    """``/v2/messageRules/allowBlockLists`` (domain level allow/block lists)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def allow_block_lists(self, **params: Any) -> dict[str, Any]:
        return self._client.request(
            "GET", "/v2/messageRules/allowBlockLists", params=dict(params) or None
        )


class ReportsResource:
    """``/v2/reports`` (audit log search)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def search(self, *, start: str, end: str, **params: Any) -> dict[str, Any]:
        """Search audit logs in a time range (ISO-8601 timestamps)."""
        body = {"startTime": start, "endTime": end}
        body.update(params)
        return self._client.request("POST", "/v2/reports", json=body)
