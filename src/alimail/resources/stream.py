"""File stream resource used by attachment upload sessions."""

from __future__ import annotations

from typing import Any

from . import q


class StreamResource:
    """``/v2/stream/{id}`` chunk upload."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def upload(
        self,
        stream_id: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> Any:
        """Upload one chunk to an upload session created by the mail APIs."""
        return self._client.request(
            "POST",
            f"/v2/stream/{q(stream_id)}",
            data=content,
            headers={"Content-Type": content_type},
        )
