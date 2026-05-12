"""Prometheus business metrics for MemoryOS Lite.

All metrics are defined at module level. Engine code imports and
increments them at relevant call sites. The /metrics endpoint is
exposed via prometheus_client ASGI app mounted in api/app.py.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

INGEST_TOTAL = Counter(
    "memoryos_ingest_total",
    "Total messages ingested",
)

PAGE_TOTAL = Counter(
    "memoryos_page_total",
    "Total memory pages created",
    ["mode"],
)

PAGE_ERRORS_TOTAL = Counter(
    "memoryos_page_errors_total",
    "Total paging failures",
    ["stage"],
)

CONTEXT_BUILD_SECONDS = Histogram(
    "memoryos_context_build_seconds",
    "build_context latency in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

CONTEXT_TOKENS = Histogram(
    "memoryos_context_tokens",
    "Tokens in returned ContextPackage",
    buckets=(50, 100, 200, 500, 1000, 2000, 4000, 8000),
)

CONTEXT_BUDGET_USED_RATIO = Histogram(
    "memoryos_context_budget_used_ratio",
    "Ratio of estimated_tokens / budget",
    buckets=(0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0),
)

RETRIEVAL_HITS = Histogram(
    "memoryos_retrieval_hits",
    "Number of search hits returned",
    buckets=(0, 1, 2, 3, 5, 8, 10, 20),
)

EMBEDDING_SECONDS = Histogram(
    "memoryos_embedding_seconds",
    "Embedding call latency in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
