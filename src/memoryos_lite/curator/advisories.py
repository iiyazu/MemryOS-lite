"""Advisory v2 projection for curated memories."""

from __future__ import annotations

import json
from hashlib import sha256

from memoryos_lite.store_curator import CuratedMemoryRow

ADVISORY_SCHEMA_V2 = "memoryos_external_advisories/v2"
PROPOSAL_TYPE_CURATED_MEMORY = "curated_memory"
ADVISORY_KIND_BY_MEMORY_KIND = {
    "fact": "room_fact",
    "lesson": "room_fact",
    "decision": "room_decision",
    "rule": "project_rule",
    "preference": "user_preference",
}


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
