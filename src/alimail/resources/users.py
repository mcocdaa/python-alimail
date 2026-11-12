"""Users resource (organization directory)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from . import q

REQUEST_SELECT_FIELDS = ("id", "email", "name", "nickname", "status", "type", "departmentIds")


class UsersResource:
    """``/v2/users`` family."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        *,
        size: int | None = None,
        filter: str | None = None,
        cursor: str | None = None,
        orderby: str | None = None,
        order: str | None = None,
        select: str | None = None,
    ) -> dict[str, Any]:
        """List users of the organization.

        Note: the pagination parameter is ``size`` (not ``limit``).
        """
        return self._client.request(
            "GET",
            "/v2/users",
            params={
                "size": size,
                "filter": filter,
                "cursor": cursor,
                "orderby": orderby,
                "order": order,
                "$select": select,
            },
        )

    def iter_all(
        self, *, size: int = 100, filter: str | None = None
    ) -> Iterator[Mapping[str, Any]]:
        """Yield every user, following the cursor."""
        yield from self._client.paginate(
            "GET", "/v2/users", item_key="users", params={"size": size, "filter": filter}
        )

    def get(self, identifier: str, *, select: str | None = None) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/users/{q(identifier)}", params={"$select": select})

    def shared_with_me(self, identifier: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/users/{q(identifier)}/sharedWithMe")

    def shared_members(self, identifier: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/users/{q(identifier)}/sharedMembers")

    def mailbox_settings(self, identifier: str, *, select: str | None = None) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/users/{q(identifier)}/mailboxSettings", params={"$select": select}
        )
