"""Superseded-source marks: which raw evidence states a value that is no longer current.

Curated memories are grounded by verbatim quotes, so a raw message or document
that contains the exact quote behind a now-superseded memory (and no quote of
an active memory) states an outdated value. Matching by quote text needs no
message or document ids, so it works for session messages, archive documents,
and hosts that keep the memories themselves (they send the marks in the
request).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from memoryos_lite.curator.grounding import MIN_QUOTE_CHARS, normalize_text
from memoryos_lite.store_curator import CuratedMemoryRow

T = TypeVar("T")


@dataclass(frozen=True)
class SupersededQuote:
    """Text that grounded a superseded memory, and the current statement if known."""

    quote: str
    current: str | None = None


def _quote(source: Any) -> str:
    value = source.get("quote", "") if isinstance(source, dict) else getattr(source, "quote", "")
    return value if isinstance(value, str) else ""


def superseded_quotes(rows: Sequence[CuratedMemoryRow | Any]) -> list[SupersededQuote]:
    """Marks for every quote that grounds only superseded memories.

    ``rows`` are curated rows or any memory objects with ``status``, ``kind``,
    ``topic_key``, ``statement`` and ``sources`` (dicts or objects with ``quote``),
    such as RoomMem's oracle views.
    """

    active = [row for row in rows if row.status == "active"]
    active_quotes = {normalize_text(_quote(source)) for row in active for source in row.sources}
    current = {(row.kind == "lesson", row.topic_key): row.statement for row in active}
    marks: dict[str, SupersededQuote] = {}
    for row in rows:
        if row.status != "superseded":
            continue
        for source in row.sources:
            quote = _quote(source)
            key = normalize_text(quote)
            if len(quote) < MIN_QUOTE_CHARS or key in active_quotes or key in marks:
                continue
            marks[key] = SupersededQuote(
                quote=quote, current=current.get((row.kind == "lesson", row.topic_key))
            )
    return list(marks.values())


def match_superseded(text: str, marks: Sequence[SupersededQuote]) -> SupersededQuote | None:
    """Return the first mark whose quote occurs in ``text`` (whitespace/case-insensitive)."""

    if not marks:
        return None
    normalized = normalize_text(text)
    for mark in marks:
        if normalize_text(mark.quote) in normalized:
            return mark
    return None


def demote_superseded(
    items: Sequence[T],
    text_of: Callable[[T], str],
    marks: Sequence[SupersededQuote],
) -> list[T]:
    """Stable partition: items without a superseded quote first, the rest after."""

    if not marks:
        return list(items)
    fresh: list[T] = []
    stale: list[T] = []
    for item in items:
        (stale if match_superseded(text_of(item), marks) is not None else fresh).append(item)
    return [*fresh, *stale]


__all__ = [
    "SupersededQuote",
    "demote_superseded",
    "match_superseded",
    "superseded_quotes",
]
