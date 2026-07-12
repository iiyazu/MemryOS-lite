"""Deterministic embedding provider used by tests and offline eval.

Hash-based 1536-dim embeddings. Identical input → identical output, so test
assertions on cosine scores are reproducible. Different inputs project into
different subspaces via a simple PRNG-per-chunk scheme, so cosine between
dissimilar strings averages near zero as expected.

Not meant for production retrieval quality — use
``OpenAIEmbeddingClient`` or another real provider for that.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable
from typing import Any


class DeterministicEmbeddingClient:
    DIM = 1536

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.DIM
        # Expand hash into DIM floats via repeated SHA-256. Each 32-byte
        # block yields 8 float32s; we take 192 blocks to reach 1536 dims.
        floats: list[float] = []
        counter = 0
        while len(floats) < self.DIM:
            payload = f"{text}|{counter}".encode()
            digest = hashlib.sha256(payload).digest()
            for offset in range(0, 32, 4):
                raw = struct.unpack("!I", digest[offset : offset + 4])[0]
                # map uint32 to [-1, 1]
                floats.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
                if len(floats) == self.DIM:
                    break
            counter += 1
        # L2 normalize
        norm = sum(f * f for f in floats) ** 0.5
        if norm == 0.0:
            return floats
        return [f / norm for f in floats]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class FakePageDraftClient:
    """Deterministic paging client for eval/test — wraps heuristic draft fn.

    Accepts a callable ``draft_fn(session_id, messages) -> MemoryPageDraft``
    so the caller (evals.py) can inject ``PagingAgent._heuristic_draft``
    without creating a circular import.
    """

    def __init__(self, draft_fn: Callable[..., Any]) -> None:
        self._draft_fn = draft_fn

    def create_draft(self, messages: Any, context_pages: Any = None) -> Any:
        return self._draft_fn("_eval_", messages)
