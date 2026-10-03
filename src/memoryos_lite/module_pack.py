"""``module_pack/v1``: a bounded resume pack for the agent that owns a module.

When a module owner's session is compacted, killed, or restarted, the host asks
for this pack instead of a retrieval result. It is composed deterministically,
with no retrieval and no LLM, from the documents attached to the module session:

- contract revisions (``metadata.activity_type == "contract_revision"``): only
  the newest ``contract_version`` per ``contract_id``, as a pointer (id,
  version, sha256, one-line summary); the full text lives with the host;
- memory documents (``metadata.memory_kind``): per ``(memory_kind,
  topic_key)`` only the highest ``version``; lessons first (most
  ``occurrences``, then newest), then decisions and facts (newest first).

Every item is an attached archive document, so the host re-proves it through
its normal document/candidate source checks. Items are added until the token
budget is spent; what did not fit is counted in ``omitted``. Optionally, pairs
of included memories with different topic keys but highly similar text are
marked ``possible_conflict_with`` (embedding similarity, no LLM).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from memoryos_lite.schemas import SessionScope
from memoryos_lite.v3_contracts import ArchivalDocument

MODULE_PACK_SCHEMA = "memoryos_module_pack/v1"
DEFAULT_BUDGET = 1500
MAX_BUDGET = 4000
MAX_ITEMS = 24
MAX_TEXT_BYTES = 1024
SUMMARY_CHARS = 160
CONTRACT_KIND = "contract_revision"
LESSON_KIND = "lesson"
DECISION_KINDS = ("decision", "fact")

EmbedBatch = Callable[[list[str]], list[list[float]]]


class ModulePackError(ValueError):
    """The request cannot produce a module pack (not a module session, bad budget)."""


@dataclass(frozen=True)
class _Candidate:
    section: str
    document: ArchivalDocument
    item: dict[str, Any]
    tokens: int


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    return max(1, ascii_chars // 4 + (len(text) - ascii_chars))


def _truncate_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


def _int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _source_refs(document: ArchivalDocument) -> list[dict[str, Any]]:
    return [ref.model_dump(mode="json", exclude_none=True) for ref in document.source_refs]


def _contract_candidates(documents: Sequence[ArchivalDocument]) -> list[_Candidate]:
    newest: dict[str, ArchivalDocument] = {}
    for document in documents:
        meta = document.metadata
        if meta.get("activity_type") != CONTRACT_KIND:
            continue
        contract_id = meta.get("contract_id")
        if not isinstance(contract_id, str) or not contract_id:
            continue
        current = newest.get(contract_id)
        if current is None or _int(meta.get("contract_version")) > _int(
            current.metadata.get("contract_version")
        ):
            newest[contract_id] = document
    candidates = []
    for contract_id in sorted(newest):
        document = newest[contract_id]
        summary = document.metadata.get("contract_summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = next((line for line in document.text.splitlines() if line.strip()), "")
        summary = summary.strip()[:SUMMARY_CHARS]
        item = {
            "contract_id": contract_id,
            "version": _int(document.metadata.get("contract_version")),
            "document_id": document.id,
            "summary": summary,
            "content_sha256": sha256(document.text.encode("utf-8")).hexdigest(),
            "source_refs": _source_refs(document),
        }
        candidates.append(
            _Candidate("contracts", document, item, estimate_tokens(f"{contract_id} {summary}"))
        )
    return candidates


def _memory_candidates(documents: Sequence[ArchivalDocument]) -> list[_Candidate]:
    newest: dict[tuple[str, str], ArchivalDocument] = {}
    for document in documents:
        meta = document.metadata
        kind = meta.get("memory_kind")
        topic_key = meta.get("topic_key")
        if kind not in (LESSON_KIND, *DECISION_KINDS) or not isinstance(topic_key, str):
            continue
        key = (str(kind), topic_key)
        current = newest.get(key)
        if current is None or _int(meta.get("version")) >= _int(current.metadata.get("version")):
            newest[key] = document

    def item_for(document: ArchivalDocument, section: str) -> _Candidate:
        meta = document.metadata
        text = _truncate_bytes(document.text, MAX_TEXT_BYTES)
        item: dict[str, Any] = {
            "document_id": document.id,
            "memory_kind": meta.get("memory_kind"),
            "topic_key": meta.get("topic_key"),
            "version": _int(meta.get("version")),
            "text": text,
            "content_sha256": sha256(document.text.encode("utf-8")).hexdigest(),
            "source_refs": _source_refs(document),
        }
        if section == "lessons":
            item["occurrences"] = _int(meta.get("occurrences"), 1)
        return _Candidate(section, document, item, estimate_tokens(text))

    lessons = [
        item_for(document, "lessons")
        for (kind, _), document in newest.items()
        if kind == LESSON_KIND
    ]
    lessons.sort(key=lambda c: (-c.item["occurrences"], -c.item["version"], c.item["document_id"]))
    decisions = [
        item_for(document, "decisions")
        for (kind, _), document in newest.items()
        if kind in DECISION_KINDS
    ]
    decisions.sort(key=lambda c: (-c.item["version"], c.item["document_id"]))
    return lessons + decisions


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _mark_conflicts(
    items: list[dict[str, Any]],
    embed_batch: EmbedBatch,
    threshold: float,
) -> None:
    if len(items) < 2:
        return
    vectors = embed_batch([item["text"] for item in items])
    for i, left in enumerate(items):
        for j in range(i + 1, len(items)):
            right = items[j]
            if left["topic_key"] == right["topic_key"]:
                continue
            if _cosine(vectors[i], vectors[j]) >= threshold:
                left.setdefault("possible_conflict_with", []).append(right["document_id"])
                right.setdefault("possible_conflict_with", []).append(left["document_id"])


def build_module_pack(
    *,
    scope: SessionScope | None,
    documents: Sequence[ArchivalDocument],
    budget: int | None = None,
    embed_batch: EmbedBatch | None = None,
    conflict_threshold: float = 0.85,
) -> dict[str, Any]:
    if scope is None or scope.type != "module":
        raise ModulePackError("module_pack/v1 requires a module-scoped session")
    resolved_budget = DEFAULT_BUDGET if budget is None else budget
    if not 1 <= resolved_budget <= MAX_BUDGET:
        raise ModulePackError(f"module_pack/v1 budget must be between 1 and {MAX_BUDGET}")

    sections: dict[str, list[dict[str, Any]]] = {"contracts": [], "lessons": [], "decisions": []}
    omitted = {"contracts": 0, "lessons": 0, "decisions": 0}
    spent = 0
    count = 0
    for candidate in [*_contract_candidates(documents), *_memory_candidates(documents)]:
        if count >= MAX_ITEMS or spent + candidate.tokens > resolved_budget:
            omitted[candidate.section] += 1
            continue
        sections[candidate.section].append(candidate.item)
        spent += candidate.tokens
        count += 1

    diagnostics: dict[str, Any] = {"conflict_check": "unavailable"}
    memories = sections["lessons"] + sections["decisions"]
    if embed_batch is not None:
        _mark_conflicts(memories, embed_batch, conflict_threshold)
        diagnostics = {"conflict_check": "fastembed", "conflict_threshold": conflict_threshold}

    payload: dict[str, Any] = {
        "schema": MODULE_PACK_SCHEMA,
        "scope": scope.model_dump(),
        "sections": sections,
        "omitted": omitted,
        "estimated_tokens": spent,
        "budget": resolved_budget,
        "truncated": any(omitted.values()),
        "diagnostics": diagnostics,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["diagnostics_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return payload
