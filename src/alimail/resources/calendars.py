"""Calendars and events resource."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import q


class CalendarsResource:
    """``/v2/users/{email}/calendars`` family."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, email: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/users/{q(email)}/calendars")

    def get(self, email: str, calendar_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/users/{q(email)}/calendars/{q(calendar_id)}")

    def events(
        self,
        email: str,
        calendar_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
        size: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List events in a time window (ISO-8601 strings)."""
        return self._client.request(
            "GET",
            f"/v2/users/{q(email)}/calendars/{q(calendar_id)}/eventsview",
            params={"start": start, "end": end, "size": size, "cursor": cursor},
        )

    def get_event(self, email: str, calendar_id: str, event_id: str) -> dict[str, Any]:
        return self._client.request(
            "GET",
            f"/v2/users/{q(email)}/calendars/{q(calendar_id)}/events/{q(event_id)}",
        )

    def create_event(
        self, email: str, calendar_id: str, event: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/calendars/{q(calendar_id)}/events",
            json=event,
        )

    def delete_event(self, email: str, calendar_id: str, event_id: str) -> dict[str, Any]:
        return self._client.request(
            "DELETE",
            f"/v2/users/{q(email)}/calendars/{q(calendar_id)}/events/{q(event_id)}",
        )

    def schedule(self, email: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Query free/busy information (``/calendars/getSchedule``)."""
        return self._client.request(
            "POST", f"/v2/users/{q(email)}/calendars/getSchedule", json=payload
        )
