import re
from typing import Any

import tiktoken


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
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, len(re.findall(r"\w+|[^\w\s]", text)))
