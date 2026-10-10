"""Stateless, deterministic ranking (``POST /recall``) and near-duplicates (``POST /similar``).

The host sends the candidate items of one over-budget view layer; MemoryOS
ranks them with the v2 recall primitives (bilingual BM25, optional dense
cosine, RRF fusion), adds fixed hint and recency bonuses, and keeps the best
items within ``budget_tokens`` and ``k``. ``/similar`` lists item pairs whose
dense cosine reaches a threshold. No LLM, no database.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.base import EmbeddingClient, cosine_similarity
from memoryos_lite.retrieval.lexical import content_tokens, tokenize
from memoryos_lite.tokenizer import TokenEstimator

RECALL_SCHEMA: Literal["memoryos_recall/v1"] = "memoryos_recall/v1"
SIMILAR_SCHEMA: Literal["memoryos_similar/v1"] = "memoryos_similar/v1"

# Ranking constants (listed in docs/specs/memoryos-service-contract.md).
RRF_K = 60  # same fusion constant as v2 recall
THREAD_BONUS = 0.02  # item thread_id equals hints.thread_id
ROLE_BONUS = 0.01  # hints.role is one of the item's roles
RECENCY_MAX = 0.005  # newest seq gets this much, oldest none, linear by seq rank
SCORE_DECIMALS = 6
EMBEDDING_CACHE_SIZE = 8192


class RecallItem(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    kind: str | None = Field(default=None, max_length=32)
    thread_id: str | None = Field(default=None, max_length=128)
    roles: list[str] = Field(default_factory=list, max_length=16)
    seq: int = Field(default=0, ge=0)


class RecallHints(BaseModel):
    thread_id: str | None = None
    role: str | None = None


class RecallRequest(BaseModel):
    schema_: Literal["memoryos_recall/v1"] = Field(alias="schema")
    query: str = Field(default="", max_length=4000)
    items: list[RecallItem] = Field(max_length=500)
    hints: RecallHints = Field(default_factory=RecallHints)
    budget_tokens: int = Field(ge=1, le=200_000)
    k: int = Field(default=40, ge=1, le=500)

    @model_validator(mode="after")
    def _unique_ids(self) -> RecallRequest:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("item ids must be unique")
        return self


class RecallRanked(BaseModel):
    id: str
    score: float
    why: list[str]


class RecallDiagnostics(BaseModel):
    dense: bool
    token_estimator: str


class RecallResponse(BaseModel):
    schema_: Literal["memoryos_recall/v1"] = Field(default=RECALL_SCHEMA, alias="schema")
    ranked: list[RecallRanked]
    dropped: list[str]
    tokens_used: int
    diagnostics: RecallDiagnostics

    model_config = {"populate_by_name": True}


class SimilarItem(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)


class SimilarRequest(BaseModel):
    schema_: Literal["memoryos_similar/v1"] = Field(alias="schema")
    items: list[SimilarItem] = Field(max_length=500)
    threshold: float = Field(default=0.88, gt=0, le=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> SimilarRequest:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("item ids must be unique")
        return self


class SimilarPair(BaseModel):
    a: str
    b: str
    score: float


class SimilarDiagnostics(BaseModel):
    dense: bool


class SimilarResponse(BaseModel):
    schema_: Literal["memoryos_similar/v1"] = Field(default=SIMILAR_SCHEMA, alias="schema")
    pairs: list[SimilarPair]
    diagnostics: SimilarDiagnostics

    model_config = {"populate_by_name": True}


class SimilarUnavailableError(RuntimeError):
    """``/similar`` needs dense embeddings; BM25 does not stand in for them."""


def _rrf_ranks(scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    return {item_id: rank for rank, (item_id, _score) in enumerate(ordered, start=1)}


class Recaller:
    """Ranks items; the only state is a rebuildable embedding cache."""

    def __init__(
        self, tokenizer: TokenEstimator, embedding_client: EmbeddingClient | None = None
    ) -> None:
        self.tokenizer = tokenizer
        self.embedding_client = embedding_client
        self._vectors: OrderedDict[str, list[float]] = OrderedDict()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        assert self.embedding_client is not None
        keys = [hashlib.sha256(text.encode()).hexdigest() for text in texts]
        missing = {
            key: text for key, text in zip(keys, texts, strict=True) if key not in self._vectors
        }
        if missing:
            vectors = self.embedding_client.embed_batch(list(missing.values()))
            if len(vectors) != len(missing):
                raise RuntimeError("embedding batch size mismatch")
            self._vectors.update(zip(missing, vectors, strict=True))
        for key in keys:
            self._vectors.move_to_end(key)
        while len(self._vectors) > max(EMBEDDING_CACHE_SIZE, len(keys)):
            self._vectors.popitem(last=False)
        return [self._vectors[key] for key in keys]

    def _dense_scores(self, request: RecallRequest) -> dict[str, float] | None:
        """Cosine per item, or None when the dense ranker is unavailable."""

        if self.embedding_client is None:
            return None
        if not request.query.strip():
            return {}
        try:
            vectors = self._embed([request.query] + [item.text for item in request.items])
        except Exception:
            return None
        query_vector, item_vectors = vectors[0], vectors[1:]
        return {
            item.id: score
            for item, vector in zip(request.items, item_vectors, strict=True)
            if (score := float(cosine_similarity(query_vector, vector))) > 0
        }

    def recall(self, request: RecallRequest) -> RecallResponse:
        items = request.items
        query_tokens = tokenize(request.query)
        query_content = content_tokens(query_tokens)
        lexical: dict[str, float] = {}
        if items and query_content:
            corpus = [tokenize(item.text) for item in items]
            if any(corpus):
                scores = BM25Okapi(corpus).get_scores(query_tokens)
                lexical = {
                    item.id: float(score)
                    for item, tokens, score in zip(items, corpus, scores, strict=True)
                    if query_content & content_tokens(tokens)
                }
        dense = self._dense_scores(request)
        lexical_rank = _rrf_ranks(lexical)
        dense_rank = _rrf_ranks(dense or {})
        seqs = sorted({item.seq for item in items})
        seq_rank = {seq: index for index, seq in enumerate(seqs)}
        scored: list[tuple[float, int, str, list[str]]] = []
        for item in items:
            why: list[str] = []
            score = 0.0
            if item.id in lexical_rank:
                score += 1.0 / (RRF_K + lexical_rank[item.id])
                why.append("bm25")
            if item.id in dense_rank:
                score += 1.0 / (RRF_K + dense_rank[item.id])
                why.append("dense")
            if request.hints.thread_id is not None and item.thread_id == request.hints.thread_id:
                score += THREAD_BONUS
                why.append("thread")
            if request.hints.role is not None and request.hints.role in item.roles:
                score += ROLE_BONUS
                why.append("role")
            if len(seqs) > 1:
                score += RECENCY_MAX * seq_rank[item.seq] / (len(seqs) - 1)
            scored.append((round(score, SCORE_DECIMALS), item.seq, item.id, why))
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        texts = {item.id: item.text for item in items}
        ranked: list[RecallRanked] = []
        dropped: list[str] = []
        used = 0
        for score, _seq, item_id, why in scored:
            tokens = self.tokenizer.count(texts[item_id])
            if len(ranked) >= request.k or used + tokens > request.budget_tokens:
                dropped.append(item_id)
                continue
            ranked.append(RecallRanked(id=item_id, score=score, why=why))
            used += tokens
        return RecallResponse(
            ranked=ranked,
            dropped=dropped,
            tokens_used=used,
            diagnostics=RecallDiagnostics(
                dense=dense is not None, token_estimator=self.tokenizer.name
            ),
        )

    def similar(self, request: SimilarRequest) -> SimilarResponse:
        """Near-duplicate pairs by dense cosine; raises when no embedding is available."""

        if self.embedding_client is None:
            raise SimilarUnavailableError("similar_unavailable")
        try:
            vectors = np.asarray(self._embed([item.text for item in request.items]), dtype=float)
        except Exception as exc:
            raise SimilarUnavailableError("similar_unavailable") from exc
        pairs: list[SimilarPair] = []
        if len(request.items) > 1:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            unit = vectors / np.where(norms == 0, 1.0, norms)
            cosine = np.round(unit @ unit.T, SCORE_DECIMALS)
            for i, j in zip(*np.triu_indices(len(request.items), k=1), strict=True):
                score = float(cosine[i, j])
                if score >= request.threshold:
                    a, b = sorted((request.items[i].id, request.items[j].id))
                    pairs.append(SimilarPair(a=a, b=b, score=score))
        pairs.sort(key=lambda pair: (-pair.score, pair.a, pair.b))
        return SimilarResponse(pairs=pairs, diagnostics=SimilarDiagnostics(dense=True))
