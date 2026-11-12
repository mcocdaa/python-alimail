"""Registry of all documented Alimail OpenAPI operations.

The registry is generated from the official OpenAPI document by
``scripts/gen_operations.py`` and shipped as ``operations.json`` next to this
module.  It powers :meth:`alimail.client.Client.call` and ``alimail ops``.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any

_PLACEHOLDER = re.compile(r"\{([^}]+)\}")


@dataclass(frozen=True)
class Operation:
    """Metadata for one API operation."""

    name: str
    method: str
    path: str
    summary: str = ""
    tags: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    operation_id: str = ""
    params: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def path_params(self) -> tuple[str, ...]:
        return tuple(_PLACEHOLDER.findall(self.path))

    def build_path(self, values: Mapping[str, Any] | None = None) -> str:
        """Fill ``{placeholders}`` with URL-encoded values."""
        values = values or {}
        missing = [p for p in self.path_params if p not in values]
        if missing:
            raise KeyError(
                f"operation {self.name!r} requires path parameters: {', '.join(missing)}"
            )

        def replace(match: re.Match[str]) -> str:
            raw = str(values[match.group(1)])
            return raw if raw.startswith("$") else urllib.parse.quote(raw, safe="")

        return _PLACEHOLDER.sub(replace, self.path)

    def describe(self) -> str:
        scopes = ", ".join(self.scopes) or "-"
        return f"{self.name:<40} {self.method:<6} {self.path:<55} {self.summary}  [{scopes}]"


@lru_cache(maxsize=1)
def _load() -> dict[str, Operation]:
    raw = resources.files(__package__).joinpath("operations.json").read_text(encoding="utf-8")
    entries = json.loads(raw)
    registry: dict[str, Operation] = {}
    for entry in entries:
        operation = Operation(
            name=entry["name"],
            method=entry["method"],
            path=entry["path"],
            summary=entry.get("summary", ""),
            tags=tuple(entry.get("tags", ())),
            scopes=tuple(entry.get("scopes", ())),
            operation_id=entry.get("operation_id", ""),
            params=tuple(entry.get("params", ())),
        )
        registry[operation.name] = operation
    return registry


def all_operations() -> tuple[Operation, ...]:
    """Return every documented operation, sorted by name."""
    return tuple(sorted(_load().values(), key=lambda op: op.name))


def get_operation(name: str) -> Operation:
    """Look up an operation by friendly name or by its official operation id."""
    registry = _load()
    if name in registry:
        return registry[name]
    lowered = name.lower()
    for operation in registry.values():
        if operation.name.lower() == lowered or operation.operation_id.lower() == lowered:
            return operation
    for operation in registry.values():
        if lowered in operation.name.lower():
            return operation
    raise KeyError(f"unknown operation {name!r}; run `alimail ops list` to see all names")


def iter_operations(tag: str | None = None) -> Iterator[Operation]:
    for operation in all_operations():
        if tag is None or tag in operation.tags:
            yield operation


def load_raw() -> list[dict[str, Any]]:
    """Raw JSON entries (used by the CLI and the docs generator)."""
    raw = resources.files(__package__).joinpath("operations.json").read_text(encoding="utf-8")
    return json.loads(raw)
