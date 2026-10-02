"""Deterministic quote grounding for curator sources.

A quote is accepted only when it is an exact substring of the cited message
(or uniquely recoverable after whitespace/case normalization, in which case
it is rewritten to the exact original span).  Quotes shorter than
``MIN_QUOTE_CHARS`` are rejected outright.
"""

from __future__ import annotations

MIN_QUOTE_CHARS = 8


def normalize_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _match_from(content: str, start: int, target: str) -> int | None:
    """Return the end offset of ``target`` matched from ``start``, or ``None``.

    Matching case-folds per character and treats any run of whitespace in
    ``content`` as the single spaces present in the normalized ``target``.
    """

    index = start
    position = 0
    length = len(content)
    while position < len(target):
        if index >= length:
            return None
        char = content[index]
        if char.isspace():
            if target[position] != " ":
                return None
            while index < length and content[index].isspace():
                index += 1
            position += 1
            continue
        expanded = char.casefold()
        if target[position : position + len(expanded)] != expanded:
            return None
        position += len(expanded)
        index += 1
    return index


def normalized_spans(content: str, target: str) -> list[tuple[int, int]]:
    if not target:
        return []
    spans: list[tuple[int, int]] = []
    for start in range(len(content)):
        first = content[start]
        if first.isspace() or not target.startswith(first.casefold()):
            continue
        end = _match_from(content, start, target)
        if end is not None:
            spans.append((start, end))
    return spans


def repair_quote(content: str, quote: str) -> str | None:
    """Return an exact original span for ``quote`` within ``content``.

    ``None`` means the quote cannot be grounded: it is too short, absent, or
    its normalized form is ambiguous.
    """

    if len(quote) < MIN_QUOTE_CHARS:
        return None
    if quote in content:
        return quote
    target = normalize_text(quote)
    if not target:
        return None
    spans = normalized_spans(content, target)
    unique_spans = set(spans)
    if len(unique_spans) != 1:
        return None
    start, end = unique_spans.pop()
    return content[start:end]


def ground_quote(
    content_by_message: dict[str, str],
    message_id: object,
    quote: object,
) -> str | None:
    """Ground one source against the session messages rendered in the prompt."""

    if not isinstance(message_id, str) or not isinstance(quote, str):
        return None
    content = content_by_message.get(message_id)
    if content is None:
        return None
    return repair_quote(content, quote)
