"""Bilingual tokenizer shared by the BM25 searchers."""

from __future__ import annotations

import re

ENGLISH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
    }
)


def tokenize(text: str) -> list[str]:
    """Bilingual tokenizer: Latin tokens + CJK unigrams + CJK bigrams."""
    normalized = text.lower()
    tokens: list[str] = re.findall(r"[a-z0-9]+", normalized)
    cjk_chars = [char for char in normalized if "一" <= char <= "鿿"]
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
    return tokens


def content_tokens(tokens: list[str]) -> set[str]:
    """The tokens that carry content: ``tokens`` minus English stopwords."""
    return {token for token in tokens if token not in ENGLISH_STOPWORDS}
