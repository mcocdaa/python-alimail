"""Resource groups exposed as attributes of :class:`alimail.client.Client`."""

from __future__ import annotations

import urllib.parse
from collections.abc import Mapping
from typing import Any


def q(value: Any, *, safe: str = "") -> str:
    """URL-encode a path segment, keeping ``$root`` style placeholders intact."""
    text = str(value)
    if text.startswith("$"):
        return text
    return urllib.parse.quote(text, safe=safe)


def recipients(addresses: Any) -> list[dict[str, str]]:
    """Normalise recipients to ``[{"email": ...}]``."""
    if addresses is None:
        return []
    if isinstance(addresses, str):
        addresses = [addresses]
    result = []
    for item in addresses:
        if isinstance(item, Mapping):
            result.append(dict(item))
        else:
            result.append({"email": str(item)})
    return result
