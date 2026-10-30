"""Canonical JSON for hashing and signing (build plan §11.2).

A hash is only a commitment if the bytes being hashed are reproducible. Two JSON
encoders that order keys differently, or escape non-ASCII differently, produce
different hashes for the same data - and then a receipt that was perfectly valid
fails to verify a year later because someone upgraded a library.

So the form is pinned exactly:

    json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

encoded UTF-8. `ensure_ascii=False` matters here more than usual: the payload
carries Marathi and Hindi text, and escaping it would make the stored canonical
string unreadable to the admin checking a receipt by eye.

The canonical string is **stored** alongside the receipt rather than
recomputed on read, so verification hashes the bytes that were actually signed.
"""

from __future__ import annotations

import json
from typing import Any


def canonicalise(payload: dict[str, Any]) -> str:
    """The one canonical JSON form (§11.2)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return canonicalise(payload).encode("utf-8")


def diff(original: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Field-level differences between two payloads, for the tamper demo (§11.3).

    Returns a flat list of `{path, from, to}` so the website can show "emi:
    4,600 -> 4,000" rather than two blobs of JSON. Flat paths (`teachback.0.q`)
    because the UI renders a table, and a nested diff would need a tree widget
    to say something simple.
    """
    changes: list[dict[str, Any]] = []

    def walk(left: Any, right: Any, path: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                walk(
                    left.get(key, _MISSING),
                    right.get(key, _MISSING),
                    f"{path}.{key}" if path else key,
                )
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                walk(
                    left[index] if index < len(left) else _MISSING,
                    right[index] if index < len(right) else _MISSING,
                    f"{path}.{index}",
                )
            return
        if left != right:
            changes.append(
                {
                    "path": path,
                    "from": None if left is _MISSING else left,
                    "to": None if right is _MISSING else right,
                }
            )

    walk(original, candidate, "")
    return changes


class _Missing:
    """Sentinel for a key present on one side only. Not `None`, because `None`
    is a legitimate value and "absent" and "null" are different edits."""

    def __repr__(self) -> str:  # pragma: no cover
        return "<missing>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Missing)

    def __hash__(self) -> int:
        return hash("<missing>")


_MISSING = _Missing()
