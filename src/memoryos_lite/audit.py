"""Stateless dependency audit (``POST /audit``): which messages relied on a replaced convention.

The host sends the old and the new statement and the messages written while the old one was in
force (its own time window). MemoryOS ranks them by three fused lists and lets an LLM judge the
top ``k``:

- rule expansion: the old statement plus every code span or identifier of either statement, one
  short query each, BM25 and dense, RRF-fused (dependents copy the identifiers they rely on);
- LLM expansion: a few queries describing how messages would talk about the old behaviour, BM25
  and dense (catches dependents that paraphrase);
- recency: the newest messages of the window.

The judge must quote each dependency verbatim; a quote that is not an exact substring drops the
flag. Design and evidence: the DepRecall benchmark (xmuse handson/exp-dep-recall, rounds 1-3).
No database, no state.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict, defaultdict
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.base import EmbeddingClient
from memoryos_lite.retrieval.lexical import content_tokens, tokenize

AUDIT_SCHEMA: Literal["memoryos_audit/v1"] = "memoryos_audit/v1"
RRF_K = 60
RECENT = 20  # newest messages fused as the third list
EXPANSIONS = 4
JUDGE_CHARS = 1500  # what the judge sees of each message; quotes are checked against the full text
QUOTE_CHARS = 120
GENERIC = frozenset({"md", "py", "spec", "true", "false"})
EMBEDDING_CACHE_SIZE = 8192


class AuditStatement(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8000)


class AuditItem(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8000)
    speaker: str | None = Field(default=None, max_length=128)
    seq: int = Field(default=0, ge=0)


class AuditRequest(BaseModel):
    schema_: Literal["memoryos_audit/v1"] = Field(alias="schema")
    old: AuditStatement
    new: AuditStatement
    items: list[AuditItem] = Field(max_length=2000)
    k: int = Field(default=20, ge=1, le=60)
    expand: bool = True

    @model_validator(mode="after")
    def _unique_ids(self) -> AuditRequest:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("item ids must be unique")
        return self


class AuditFlag(BaseModel):
    id: str
    quote: str


class AuditUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AuditDiagnostics(BaseModel):
    queries: int
    expanded: int  # LLM expansion queries used (0: off or failed)
    dense: bool
    judged: int
    dropped_quotes: int  # flags whose quote was not an exact substring
    llm_calls: int = 0
    usage: AuditUsage | None = None


class AuditResponse(BaseModel):
    schema_: Literal["memoryos_audit/v1"] = Field(default=AUDIT_SCHEMA, alias="schema")
    flagged: list[AuditFlag]
    candidates: list[str]  # the judged top-k, best first
    diagnostics: AuditDiagnostics

    model_config = {"populate_by_name": True}


# ---- deterministic retrieval ---------------------------------------------------------------------
def rrf(*rankings: list[str]) -> list[str]:
    score: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            score[item_id] += 1.0 / (RRF_K + rank)
    return sorted(score, key=lambda item_id: (-score[item_id], item_id))


def rule_queries(old: str, new: str) -> list[str]:
    """Backticked spans of both statements (3+ letters or digits), else their ASCII identifiers."""
    both = old + "\n" + new
    spans = [s.strip() for s in re.findall(r"`([^`\n]+)`", both)]
    spans = [
        s for s in spans if len(re.findall(r"[A-Za-z0-9]", s)) >= 3 and s.lower() not in GENERIC
    ]
    if not spans:  # a decision typed by a person: no code spans, but often the names it is about
        spans = [
            w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.]{2,}", both) if w.lower() not in GENERIC
        ]
    return list(dict.fromkeys(spans))


class Retriever:
    """BM25 and dense rankings over one request's items; the state is a rebuildable vector cache."""

    def __init__(self, embedding_client: EmbeddingClient | None = None) -> None:
        self.embedding_client = embedding_client
        self._vectors: OrderedDict[str, list[float]] = OrderedDict()

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        if self.embedding_client is None:
            return None
        keys = [hashlib.sha256(text.encode()).hexdigest() for text in texts]
        missing = {
            key: text for key, text in zip(keys, texts, strict=True) if key not in self._vectors
        }
        try:
            if missing:
                vectors = self.embedding_client.embed_batch(list(missing.values()))
                if len(vectors) != len(missing):
                    return None
                self._vectors.update(zip(missing, vectors, strict=True))
        except Exception:
            return None
        for key in keys:
            self._vectors.move_to_end(key)
        while len(self._vectors) > max(EMBEDDING_CACHE_SIZE, len(keys)):
            self._vectors.popitem(last=False)
        return [self._vectors[key] for key in keys]

    def rank(self, items: list[AuditItem], queries: list[str]) -> tuple[list[str], bool]:
        """RRF over BM25 and dense, one ranking each per query: (ids best first, dense used)."""
        if not items or not queries:
            return [], False
        corpus = [tokenize(item.text) for item in items]
        bm25 = BM25Okapi(corpus) if any(corpus) else None
        rankings: list[list[str]] = []
        for query in queries:
            q_tokens = tokenize(query)
            q_content = content_tokens(q_tokens)
            if bm25 is not None and q_content:
                scores = bm25.get_scores(q_tokens)
                hits = [
                    (float(s), item.id)
                    for item, toks, s in zip(items, corpus, scores, strict=True)
                    if q_content & content_tokens(toks)
                ]
                rankings.append([i for _, i in sorted(hits, key=lambda p: (-p[0], p[1]))])
        vectors = self._embed(queries + [item.text[:2000] for item in items])
        if vectors is not None:
            unit = np.asarray(vectors, dtype=float)
            norms = np.linalg.norm(unit, axis=1, keepdims=True)
            unit = unit / np.where(norms == 0, 1.0, norms)
            sims = unit[len(queries) :] @ unit[: len(queries)].T  # items x queries
            for col in range(len(queries)):
                order = sorted(range(len(items)), key=lambda i: (-sims[i, col], items[i].id))
                rankings.append([items[i].id for i in order if sims[i, col] > 0])
        return rrf(*rankings), vectors is not None


def recent(items: list[AuditItem]) -> list[str]:
    return [item.id for item in sorted(items, key=lambda item: (-item.seq, item.id))[:RECENT]]


def verify(
    items: list[AuditItem], candidates: list[str], verdicts: object
) -> tuple[list[AuditFlag], int]:
    """Flags from the judge's reply: candidates with dep=1 and a verbatim, short quote."""
    text = {item.id: item.text for item in items}
    flags, dropped = [], 0
    if not isinstance(verdicts, dict):
        return [], 0
    for item_id in candidates:
        v = verdicts.get(item_id)
        if not isinstance(v, dict) or v.get("dep") not in (1, True, "1"):
            continue
        quote = v.get("quote")
        if (
            isinstance(quote, str)
            and quote.strip()
            and len(quote) <= QUOTE_CHARS + 20
            and quote in text[item_id]
        ):
            flags.append(AuditFlag(id=item_id, quote=quote))
        else:
            dropped += 1
    return flags, dropped


# ---- prompts -------------------------------------------------------------------------------------
EXPAND_SYSTEM = (
    "You help find chat messages of a software team that relied on a coding convention which "
    "has just been replaced. Reply with one JSON object only."
)
JUDGE_SYSTEM = (
    "You review a software team's chat messages against a convention that has just been "
    "replaced. You decide each message yourself and quote the message exactly. Reply with one "
    "JSON object only."
)


def expand_prompt(old: str, new: str) -> str:
    return (
        f"OLD convention (now replaced):\n{old}\n\nNEW decision:\n{new}\n\n"
        f"Write exactly {EXPANSIONS} short search queries (each under 25 words) describing how "
        "messages that relied on the OLD convention would talk about the old behaviour: done "
        "reports, reviews, test results, handoffs. Use the language and the concrete wording a "
        "teammate would use, identifiers included.\n"
        'Reply as {"queries": ["...", "...", "...", "..."]}.'
    )


def judge_prompt(old: str, new: str, items: list[AuditItem]) -> str:
    rows = "\n\n".join(
        f"[{item.id}] {item.speaker or '?'}:\n{item.text[:JUDGE_CHARS]}" for item in items
    )
    return (
        f"OLD convention (now replaced):\n{old}\n\nNEW decision:\n{new}\n\nMESSAGES:\n{rows}\n\n"
        "For each message decide dep = 1 if it states, implements, verifies, or reviews "
        "behaviour that must change under the NEW decision (a done or status report about the "
        "old behaviour, test results or review findings about it, a plan or handoff committing "
        "to it). dep = 0 otherwise: it only mentions a file or function, reports generic "
        "progress, is about another convention, or is unrelated.\n"
        f'For dep = 1 give "quote": an exact substring of that message (at most {QUOTE_CHARS} '
        'characters) showing the dependency; for dep = 0 use "".\n'
        'Reply as {"verdicts": {"<message id>": {"dep": 0 or 1, "quote": "..."}, ...}} with '
        "every message id."
    )


__all__ = [
    "AUDIT_SCHEMA",
    "AuditDiagnostics",
    "AuditFlag",
    "AuditItem",
    "AuditRequest",
    "AuditResponse",
    "AuditStatement",
    "AuditUsage",
    "Retriever",
    "expand_prompt",
    "judge_prompt",
    "recent",
    "rrf",
    "rule_queries",
    "verify",
]
