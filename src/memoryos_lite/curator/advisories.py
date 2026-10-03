"""Advisory v2/v3 projections for curated memories."""

from __future__ import annotations

import json
from hashlib import sha256

from memoryos_lite.schemas import SessionScope
from memoryos_lite.store_curator import CuratedMemoryRow

ADVISORY_SCHEMA_V2 = "memoryos_external_advisories/v2"
ADVISORY_SCHEMA_V3 = "memoryos_external_advisories/v3"
PROPOSAL_TYPE_CURATED_MEMORY = "curated_memory"
ADVISORY_KIND_BY_MEMORY_KIND = {
    "fact": "room_fact",
    "lesson": "room_fact",
    "decision": "room_decision",
    "rule": "project_rule",
    "preference": "user_preference",
}
ADVISORY_KIND_BY_MEMORY_KIND_MODULE = {
    "fact": "module_fact",
    "lesson": "module_lesson",
    "decision": "module_decision",
    "rule": "project_rule",
    "preference": "user_preference",
}
ADVISORY_V3_ITEM_KEYS = frozenset(
    {
        "advisory_id",
        "fingerprint",
        "proposal_type",
        "kind",
        "memory_kind",
        "scope",
        "topic_key",
        "version",
        "occurrences",
        "content",
        "source_refs",
        "supersedes_advisory_id",
    }
)
ADVISORY_V3_KINDS = frozenset(
    {
        "module_fact",
        "module_lesson",
        "module_decision",
        "room_fact",
        "room_decision",
        "project_rule",
        "user_preference",
    }
)
V3_MAX_SOURCE_REFS = 8
V3_MAX_QUOTE_BYTES = 1024
V3_MAX_CONTENT_BYTES = 4096


def advisory_identity(
    kind: str,
    statement: str,
    sources: list[dict[str, str]],
) -> tuple[str, str]:
    """Return the stable ``(advisory_id, fingerprint)`` for one memory.

    The fingerprint is sha256 over (kind, content, sources), so any consumer
    can recompute it from the advisory payload alone.
    """

    canonical = json.dumps(
        {"kind": kind, "content": statement, "sources": sources},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
    return f"advisory_{fingerprint[:40]}", fingerprint


def build_advisory_v2_items(
    rows: list[CuratedMemoryRow],
    superseded_rows: dict[str, CuratedMemoryRow] | None = None,
) -> list[dict[str, object]]:
    superseded_rows = superseded_rows or {}
    items: list[dict[str, object]] = []
    for row in rows:
        advisory_id, fingerprint = advisory_identity(row.kind, row.statement, row.sources)
        supersedes_advisory_id: str | None = None
        if row.supersedes_id is not None:
            superseded = superseded_rows.get(row.supersedes_id)
            if superseded is not None:
                supersedes_advisory_id = advisory_identity(
                    superseded.kind,
                    superseded.statement,
                    superseded.sources,
                )[0]
        items.append(
            {
                "advisory_id": advisory_id,
                "fingerprint": fingerprint,
                "proposal_type": PROPOSAL_TYPE_CURATED_MEMORY,
                "kind": ADVISORY_KIND_BY_MEMORY_KIND[row.kind],
                "topic_key": row.topic_key,
                "content": row.statement,
                "source_refs": [
                    {
                        "source_type": "message",
                        "source_id": source["message_id"],
                        "session_id": row.session_id,
                        "quote": source["quote"],
                    }
                    for source in row.sources
                ],
                "supersedes_advisory_id": supersedes_advisory_id,
            }
        )
    return items


def _truncate_utf8_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


def _v3_kind(memory_kind: str, session_scope: SessionScope | None) -> str:
    if session_scope is not None and session_scope.type == "module":
        return ADVISORY_KIND_BY_MEMORY_KIND_MODULE[memory_kind]
    return ADVISORY_KIND_BY_MEMORY_KIND[memory_kind]


def _v3_scope(kind: str, session_scope: SessionScope | None) -> dict[str, str]:
    if kind.startswith("module_") and session_scope is not None:
        return {"type": "module", "id": session_scope.id}
    if kind == "project_rule":
        return {"type": "project"}
    if kind == "user_preference":
        return {"type": "user"}
    return {"type": "room"}


def build_advisory_v3_items(
    rows: list[CuratedMemoryRow],
    superseded_rows: dict[str, CuratedMemoryRow] | None = None,
    *,
    session_scope: SessionScope | None,
    message_info: dict[str, tuple[str | None, str | None]],
) -> list[dict[str, object]]:
    superseded_rows = superseded_rows or {}
    items: list[dict[str, object]] = []
    for row in rows:
        advisory_id, fingerprint = advisory_identity(row.kind, row.statement, row.sources)
        supersedes_advisory_id: str | None = None
        if row.supersedes_id is not None:
            superseded = superseded_rows.get(row.supersedes_id)
            if superseded is not None:
                supersedes_advisory_id = advisory_identity(
                    superseded.kind,
                    superseded.statement,
                    superseded.sources,
                )[0]
        kind = _v3_kind(row.kind, session_scope)
        scope = _v3_scope(kind, session_scope)
        kept_sources = row.sources[-V3_MAX_SOURCE_REFS:]
        source_refs: list[dict[str, object]] = []
        for source in kept_sources:
            message_id = source["message_id"]
            external_id, activity_type = message_info.get(message_id, (None, None))
            source_refs.append(
                {
                    "source_type": "message",
                    "source_id": message_id,
                    "session_id": row.session_id,
                    "external_id": external_id,
                    "activity_type": activity_type,
                    "quote": _truncate_utf8_bytes(source["quote"], V3_MAX_QUOTE_BYTES),
                }
            )
        items.append(
            {
                "advisory_id": advisory_id,
                "fingerprint": fingerprint,
                "proposal_type": PROPOSAL_TYPE_CURATED_MEMORY,
                "kind": kind,
                "memory_kind": row.kind,
                "scope": scope,
                "topic_key": row.topic_key,
                "version": row.version,
                "occurrences": row.occurrences,
                "content": _truncate_utf8_bytes(row.statement, V3_MAX_CONTENT_BYTES),
                "source_refs": source_refs,
                "supersedes_advisory_id": supersedes_advisory_id,
            }
        )
    return items
