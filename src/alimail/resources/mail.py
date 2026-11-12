"""Mail resource: folders, messages, search, drafts, sending and attachments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from . import q, recipients

INBOX_FOLDER_ID = "2"
SENT_FOLDER_ID = "1"
SPAM_FOLDER_ID = "3"
DRAFT_FOLDER_ID = "5"
DELETED_FOLDER_ID = "6"

DEFAULT_MESSAGE_SELECT = "subject,from,receivedDateTime,isRead,id"


class MailResource:
    """``/v2/users/{email}/mailFolders`` and ``/v2/users/{email}/messages`` family."""

    INBOX = INBOX_FOLDER_ID
    SENT = SENT_FOLDER_ID
    SPAM = SPAM_FOLDER_ID
    DRAFT = DRAFT_FOLDER_ID
    DELETED = DELETED_FOLDER_ID

    def __init__(self, client: Any) -> None:
        self._client = client

    # -- folders -------------------------------------------------------
    def folders(self, email: str) -> dict[str, Any]:
        """List mail folders; the folder *id* is numeric (inbox = ``"2"``)."""
        return self._client.request("GET", f"/v2/users/{q(email)}/mailFolders")

    def find_folder_id(self, email: str, name: str = "inbox") -> str:
        target = name.lower()
        aliases = {
            "inbox": {"inbox", "收件箱"},
            "sent": {"sentitems", "sent", "已发送"},
            "draft": {"draft", "drafts", "草稿箱"},
            "spam": {"spam", "垃圾邮件"},
            "deleted": {"deleted", "已删除", "trash"},
        }
        wanted = aliases.get(target, {target})
        folders = self.folders(email).get("folders") or []
        for folder in folders:
            if str(folder.get("displayName", "")).lower() in wanted:
                return str(folder.get("id"))
        fallback = {
            "inbox": INBOX_FOLDER_ID,
            "sent": SENT_FOLDER_ID,
            "spam": SPAM_FOLDER_ID,
            "draft": DRAFT_FOLDER_ID,
            "deleted": DELETED_FOLDER_ID,
        }
        return fallback.get(target, target)

    # -- messages ------------------------------------------------------
    def messages(
        self,
        email: str,
        *,
        folder_id: str = INBOX_FOLDER_ID,
        size: int | None = None,
        cursor: str | None = None,
        select: str | None = DEFAULT_MESSAGE_SELECT,
        orderby: str | None = None,
    ) -> dict[str, Any]:
        return self._client.request(
            "GET",
            f"/v2/users/{q(email)}/mailFolders/{q(folder_id)}/messages",
            params={"size": size, "cursor": cursor, "$select": select, "orderby": orderby},
        )

    def inbox(
        self, email: str, *, size: int | None = 20, select: str | None = DEFAULT_MESSAGE_SELECT
    ) -> dict[str, Any]:
        return self.messages(email, folder_id=INBOX_FOLDER_ID, size=size, select=select)

    def message(self, email: str, message_id: str, *, select: str | None = None) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/users/{q(email)}/messages/{q(message_id)}", params={"$select": select}
        )

    def search(
        self,
        email: str,
        query: str,
        *,
        size: int = 20,
        cursor: str = "",
    ) -> dict[str, Any]:
        """Search a mailbox; ``query`` accepts the documented KQL style filters."""
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/messages/query",
            json={"email": email, "query": query, "cursor": cursor, "size": size},
        )

    def attachments(self, email: str, message_id: str) -> dict[str, Any]:
        return self._client.request(
            "GET", f"/v2/users/{q(email)}/messages/{q(message_id)}/attachments"
        )

    def delete(
        self, email: str, ids: Sequence[str], *, delete_type: str | None = None
    ) -> dict[str, Any]:
        """Move messages to the deleted folder (``deleteType`` defaults to USER_DELETED)."""
        body: dict[str, Any] = {"email": email, "ids": list(ids)}
        if delete_type:
            body["deleteType"] = delete_type
        return self._client.request("POST", f"/v2/users/{q(email)}/messages/batchDelete", json=body)

    def move(self, email: str, ids: Sequence[str], destination_folder_id: str) -> dict[str, Any]:
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/messages/move",
            json={"email": email, "ids": list(ids), "destinationFolderId": destination_folder_id},
        )

    def mark_read(self, email: str, ids: Sequence[str], *, read: bool = True) -> dict[str, Any]:
        """Batch mark messages read/unread (requires ``Mail.ReadWrite.All``)."""
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/messages/batchUpdate",
            json={"email": email, "ids": list(ids), "action": "markRead" if read else "markUnread"},
        )

    # -- drafts / sending ---------------------------------------------
    def create_draft(
        self,
        email: str,
        *,
        to: Iterable[str] | str,
        subject: str,
        text: str | None = None,
        html: str | None = None,
        cc: Iterable[str] | str | None = None,
        bcc: Iterable[str] | str | None = None,
        sender: str | None = None,
    ) -> dict[str, Any]:
        """Create a draft and return the API response (contains the message id)."""
        body: dict[str, Any] = {}
        if text is not None:
            body["bodyText"] = text
        if html is not None:
            body["bodyHtml"] = html
        message = {
            "subject": subject,
            "from": {"email": sender or email},
            "toRecipients": recipients(to),
            "body": body,
        }
        if cc:
            message["ccRecipients"] = recipients(cc)
        if bcc:
            message["bccRecipients"] = recipients(bcc)
        return self._client.request(
            "POST", f"/v2/users/{q(email)}/messages", json={"message": message}
        )

    def send_draft(
        self, email: str, message_id: str, *, save_to_sent: bool = True
    ) -> dict[str, Any]:
        return self._client.request(
            "POST",
            f"/v2/users/{q(email)}/messages/{q(message_id)}/send",
            json={"email": email, "id": message_id, "saveToSentItems": save_to_sent},
        )

    def send(
        self,
        email: str,
        *,
        to: Iterable[str] | str,
        subject: str,
        text: str | None = None,
        html: str | None = None,
        cc: Iterable[str] | str | None = None,
        bcc: Iterable[str] | str | None = None,
        sender: str | None = None,
        save_to_sent: bool = True,
    ) -> dict[str, Any]:
        """Create a draft then send it (the API's two-step send flow)."""
        draft = self.create_draft(
            email, to=to, subject=subject, text=text, html=html, cc=cc, bcc=bcc, sender=sender
        )
        message = draft.get("message") if isinstance(draft, dict) else None
        message_id = None
        if isinstance(message, dict):
            message_id = message.get("id")
        if not message_id and isinstance(draft, dict):
            message_id = draft.get("id")
        if not message_id:
            raise ValueError(f"create_draft response does not contain a message id: {draft!r}")
        result = self.send_draft(email, str(message_id), save_to_sent=save_to_sent)
        return {"draft": draft, "send": result}
