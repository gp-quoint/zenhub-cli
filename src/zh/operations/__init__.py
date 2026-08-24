"""Load named GraphQL operations from ``zh/operations/*.graphql``."""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files

from zh.errors import ZhApiError

_OP_START = re.compile(r"^(query|mutation)\s+(\w+)\b", re.MULTILINE)


def _parse_operations(text: str) -> dict[str, str]:
    """Split a document into ``{OperationName: source}`` (one op per entry)."""
    starts = [(m.start(), m.group(2)) for m in _OP_START.finditer(text)]
    if not starts:
        return {}
    out: dict[str, str] = {}
    for i, (start, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        body = text[start:end].strip()
        if name in out:
            msg = f"Duplicate GraphQL operation name {name!r}"
            raise ZhApiError(msg)
        out[name] = body
    return out


@lru_cache(maxsize=32)
def _document_ops(document: str) -> dict[str, str]:
    path = files("zh.operations").joinpath(f"{document}.graphql")
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ZhApiError(f"GraphQL document not found: operations/{document}.graphql") from exc
    return _parse_operations(text)


def op(document: str, name: str) -> str:
    """Return the source for a named operation in ``operations/{document}.graphql``."""
    ops = _document_ops(document)
    try:
        return ops[name]
    except KeyError as exc:
        available = ", ".join(sorted(ops)) or "(none)"
        raise ZhApiError(
            f"Unknown GraphQL operation {name!r} in operations/{document}.graphql. Available: {available}",
        ) from exc


def clear_operations_cache() -> None:
    """Drop cached documents (tests)."""
    _document_ops.cache_clear()
