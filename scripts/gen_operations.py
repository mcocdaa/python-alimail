#!/usr/bin/env python3
"""Generate ``src/alimail/operations.json`` from the official OpenAPI document.

The official document is YAML served at::

    https://mailhelp.aliyun.com/openapi/definition?branch=master

Usage::

    python scripts/gen_operations.py                     # fetch from the official URL
    python scripts/gen_operations.py --spec spec.yaml    # use a local copy
    python scripts/gen_operations.py --spec spec.yaml --out src/alimail/operations.json

The parser is deliberately small: it only understands the ``paths`` section of
the OpenAPI document and relies on the stable 2/4/6/8 space indentation used by
the generated document.  That keeps the generator dependency free (no PyYAML).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

SPEC_URL = "https://mailhelp.aliyun.com/openapi/definition?branch=master"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "alimail" / "operations.json"
METHODS = ("get", "post", "put", "delete", "patch", "head", "options")

_PATH_RE = re.compile(r"^  (/[^:]+):\s*$")
_METHOD_RE = re.compile(r"^    (get|post|put|delete|patch|head|options):\s*$")


def fetch_spec(url: str = SPEC_URL) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "python-alimail codegen (+https://github.com/mcocdaa/python-alimail)",
            "Accept": "text/yaml, application/yaml, text/plain, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "ignore")


def _camel_to_snake(value: str) -> str:
    """``departmentService`` -> ``department_service``; keeps existing underscores."""
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", value)
    return value.lower()


def _slug_operation_id(operation_id: str) -> str:
    """Turn an official operation id into a friendly snake_case name."""
    if not operation_id:
        return ""
    name = _camel_to_snake(operation_id)
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    if "_service_" in name:
        name = name.rsplit("_service_", 1)[1]
    else:
        name = re.sub(r"^(?:alimailpb|com_alibaba_alimail)_", "", name)
    return name.strip("_")


def _parse_block(lines: list[str]) -> dict:
    """Parse the fields of a single operation block."""
    block = "\n".join(lines)
    summary = ""
    match = re.search(r"^      summary:\s*(.+)$", block, re.M)
    if match:
        summary = match.group(1).strip().strip('"').strip("'")
    operation_id = ""
    match = re.search(r"^      operationId:\s*(\S+)$", block, re.M)
    if match:
        operation_id = match.group(1).strip()
    tags: list[str] = []
    tags_match = re.search(r"^      tags:\s*$(.*?)^      \S", block, re.M | re.S)
    if tags_match:
        tags = [
            t.strip().strip('"').strip("'")
            for t in re.findall(r"^\s+-\s*(.+)$", tags_match.group(1), re.M)
        ]
    scopes: list[str] = []
    security_match = re.search(
        r"^      security:\s*$(.*?)(?=^      \S|^  /\S|\Z)", block, re.M | re.S
    )
    if security_match:
        scopes = re.findall(r"^\s+-\s*([A-Za-z][\w.]*\.All)$", security_match.group(1), re.M)
    params: list[dict] = []
    params_match = re.search(r"^      parameters:\s*$(.*?)(?=^      \S|\Z)", block, re.M | re.S)
    if params_match:
        for chunk in re.split(r"^\s*- name:\s*", params_match.group(1), flags=re.M)[1:]:
            name_match = re.match(r"([\w$.-]+)", chunk)
            location = re.search(r"^\s+in:\s*(\w+)", chunk, re.M)
            required = re.search(r"^\s+required:\s*(true|false)", chunk, re.M)
            if name_match:
                params.append(
                    {
                        "name": name_match.group(1),
                        "in": location.group(1) if location else "query",
                        "required": bool(required and required.group(1) == "true"),
                    }
                )
    return {
        "summary": summary,
        "operation_id": operation_id,
        "tags": tags,
        "scopes": scopes,
        "params": params,
    }


def parse_spec(text: str) -> list[dict]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "paths:")
    except StopIteration as exc:  # pragma: no cover - malformed spec
        raise SystemExit("spec does not contain a top level `paths:` section") from exc
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^[A-Za-z]", lines[i]):
            end = i
            break

    operations: list[dict] = []
    current_path: str | None = None
    current_start: int | None = None
    current_method: str | None = None

    def flush() -> None:
        nonlocal current_start, current_method, current_path
        if current_path and current_start is not None and current_method:
            operations.append(
                {
                    "method": current_method,
                    "path": current_path,
                    "start": current_start,
                }
            )
        current_start = None
        current_method = None

    for i in range(start + 1, end):
        line = lines[i]
        path_match = _PATH_RE.match(line)
        if path_match:
            flush()
            current_path = path_match.group(1).strip()
            continue
        method_match = _METHOD_RE.match(line)
        if method_match and current_path:
            flush()
            current_method = method_match.group(1).upper()
            current_start = i

    # last operation: compute its own end by scanning forward from start
    if current_path and current_start is not None and current_method:
        operations.append({"method": current_method, "path": current_path, "start": current_start})

    # attach parsed fields using line ranges
    operations.sort(key=lambda item: item["start"])
    for index, operation in enumerate(operations):
        block_end = operations[index + 1]["start"] if index + 1 < len(operations) else end
        operation.update(_parse_block(lines[operation["start"] : block_end]))

    # friendly names, de-duplicated
    seen: dict[str, int] = {}
    for operation in operations:
        base = _slug_operation_id(operation.get("operation_id", "")) or ""
        if not base:
            base = (
                operation["method"].lower()
                + "_"
                + re.sub(r"[^a-z0-9]+", "_", operation["path"].lower()).strip("_")
            )
        count = seen.get(base, 0) + 1
        seen[base] = count
        operation["name"] = base if count == 1 else f"{base}_{count}"

    operations.sort(key=lambda item: (item["path"], item["method"]))
    return [
        {
            "name": op["name"],
            "method": op["method"],
            "path": op["path"],
            "summary": op.get("summary", ""),
            "tags": op.get("tags", []),
            "scopes": op.get("scopes", []),
            "operation_id": op.get("operation_id", ""),
            "params": op.get("params", []),
        }
        for op in operations
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", help="local OpenAPI (YAML) file")
    parser.add_argument("--url", default=SPEC_URL, help="remote OpenAPI document URL")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    args = parser.parse_args(argv)

    if args.spec:
        text = Path(args.spec).read_text(encoding="utf-8")
    else:
        print(f"fetching {args.url} ...", file=sys.stderr)
        text = fetch_spec(args.url)
    operations = parse_spec(text)
    if not operations:
        print("no operations parsed, refusing to write an empty registry", file=sys.stderr)
        return 1
    Path(args.out).write_text(
        json.dumps(operations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(operations)} operations to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
