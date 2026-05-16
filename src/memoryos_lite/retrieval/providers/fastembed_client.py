"""Local embedding provider using fastembed (ONNX-based, no GPU needed).

Provides real semantic embeddings without requiring an external API key.
Default model: BAAI/bge-small-en-v1.5 (384 dims, ~33MB).
"""

from __future__ import annotations

from typing import Any

_model_cache: dict[str, Any] = {}


class FastEmbedClient:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        if model_name not in _model_cache:
            _model_cache[model_name] = TextEmbedding(model_name=model_name)
        self._model = _model_cache[model_name]
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            sample = list(self._model.embed(["test"]))[0]
            self._dim = len(sample)
        return self._dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dim
        result = list(self._model.embed([text]))[0]
        return result.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results = list(self._model.embed(texts))
        return [r.tolist() for r in results]
