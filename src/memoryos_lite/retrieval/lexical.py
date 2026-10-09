"""Bilingual tokenizer shared by the BM25 searchers."""

from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    """Bilingual tokenizer: Latin tokens + CJK unigrams + CJK bigrams."""
    normalized = text.lower()
    tokens: list[str] = re.findall(r"[a-z0-9]+", normalized)
    cjk_chars = [char for char in normalized if "一" <= char <= "鿿"]
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
    return tokens
