import re
from functools import lru_cache
from typing import Any

import tiktoken


@lru_cache(maxsize=1024)
def _count_tokens(text: str, use_tiktoken: bool) -> int:
    if use_tiktoken:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=()))
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


class TokenEstimator:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding: Any | None
        try:
            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            self._encoding = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        return _count_tokens(text, self._encoding is not None)
