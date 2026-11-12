"""Organization directory resources: organization, domains, departments, groups, contacts."""

from __future__ import annotations

from typing import Any

from . import q


class OrganizationResource:
    """``/v2/organization/$current``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self) -> dict[str, Any]:
        return self._client.request("GET", "/v2/organization/$current")

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.request("PATCH", "/v2/organization/$current", json=payload)


class DomainsResource:
    """``/v2/domains``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        return self._client.request("GET", "/v2/domains")

    def get(self, domain_or_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/domains/{q(domain_or_id)}")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.request("POST", "/v2/domains", json=payload)

    def verify(self, domain: str) -> dict[str, Any]:
        return self._client.request("POST", f"/v2/domains/{q(domain)}/verify")

    def delete(self, domain: str) -> dict[str, Any]:
        return self._client.request("DELETE", f"/v2/domains/{q(domain)}")


class DepartmentsResource:
    """``/v2/departments``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, department_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/departments/{q(department_id)}")

    def children(self, department_id: str = "$root", *, size: int | None = None) -> dict[str, Any]:
        """List direct children of a department (``$root`` means the root)."""
        return self._client.request(
            "GET", f"/v2/departments/{q(department_id)}/departments", params={"size": size}
        )

    def users(
        self, department_id: str, *, size: int | None = None, select: str | None = None
    ) -> dict[str, Any]:
        return self._client.request(
            "GET",
            f"/v2/departments/{q(department_id)}/users",
            params={"size": size, "$select": select},
        )

    def chain(self, department_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/departments/{q(department_id)}/chain")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.request("POST", "/v2/departments", json=payload)


class GroupsResource:
    """``/v2/groups`` (mail groups)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, *, size: int | None = None, cursor: str | None = None) -> dict[str, Any]:
        return self._client.request("GET", "/v2/groups", params={"size": size, "cursor": cursor})

    def get(self, group_id_or_email: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/groups/{q(group_id_or_email)}")

    def members(self, group_id_or_email: str, *, size: int | None = None) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/groups/{q(group_id_or_email)}/members", params={"size": size}
        )


class ContactsResource:
    """``/v2/sharedContactFolders`` (shared contacts)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_folder(self, folder_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/sharedContactFolders/{q(folder_id)}")

    def folders(self, folder_id: str = "$root") -> dict[str, Any]:
        """List child folders of a shared-contact folder (``$root`` by default)."""
        return self._client.request("GET", f"/v2/sharedContactFolders/{q(folder_id)}/childFolders")

    def child_folders(self, folder_id: str = "$root") -> dict[str, Any]:
        return self.folders(folder_id)

    def contacts(self, folder_id: str, *, size: int | None = None) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/sharedContactFolders/{q(folder_id)}/contacts", params={"size": size}
        )

    def list(self, folder_id: str, *, size: int | None = None) -> dict[str, Any]:
        """Alias of :meth:`contacts` (friendly name for ``client.contacts.list(...)``)."""
        return self.contacts(folder_id, size=size)

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        return self._client.request("GET", f"/v2/sharedContacts/{q(contact_id)}")
