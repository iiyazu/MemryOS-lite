from __future__ import annotations

import json
from hashlib import sha256
from math import isfinite
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memoryos_lite.schemas import ContextPackage
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import ContextPackageV3

SOURCE_EVIDENCE_SCHEMA = "memoryos_source_evidence/v1"
DEFAULT_MAX_ITEMS = 8
DEFAULT_MAX_TOKENS = 800
DEFAULT_MAX_BYTES = 64 * 1024
MAX_ITEM_TEXT_BYTES = 8 * 1024
MAX_TOTAL_TEXT_BYTES = 32 * 1024
MAX_ID_BYTES = 512
MAX_SOURCE_REFS = 8
_EMPTY_ENVELOPE_TOO_LARGE = "source_evidence_empty_envelope_exceeds_byte_limit"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical_bytes(value)).hexdigest()}"


def _valid_id(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_ID_BYTES:
        return None
    return value


class CompactSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(pattern="^document$")
    source_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_id(self) -> CompactSourceRef:
        if len(self.source_id.encode("utf-8")) > MAX_ID_BYTES:
            raise ValueError("source evidence source ID exceeds limit")
        return self


class SourceEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    archive_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_refs: list[CompactSourceRef] = Field(min_length=1, max_length=MAX_SOURCE_REFS)
    text: str
    estimated_tokens: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    score: float = Field(allow_inf_nan=False)
    rank: int = Field(ge=1)
    truncated: Literal[False] = False

    @model_validator(mode="after")
    def validate_item(self) -> SourceEvidenceItem:
        if any(
            len(value.encode("utf-8")) > MAX_ID_BYTES
            for value in (self.item_id, self.archive_id, self.document_id)
        ):
            raise ValueError("source evidence item ID exceeds limit")
        if len(self.text.encode("utf-8")) > MAX_ITEM_TEXT_BYTES:
            raise ValueError("source evidence item text exceeds limit")
        expected = f"sha256:{sha256(self.text.encode('utf-8')).hexdigest()}"
        if self.content_sha256 != expected:
            raise ValueError("source evidence content hash mismatch")
        return self


class SourceEvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(alias="schema", pattern="^memoryos_source_evidence/v1$")
    items: list[SourceEvidenceItem] = Field(max_length=DEFAULT_MAX_ITEMS)
    omitted_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0, le=DEFAULT_MAX_TOKENS)
    truncated: bool
    diagnostics_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_envelope(self) -> SourceEvidenceEnvelope:
        if [item.rank for item in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError("source evidence ranks must be contiguous")
        if self.estimated_tokens != sum(item.estimated_tokens for item in self.items):
            raise ValueError("source evidence token count mismatch")
        if sum(len(item.text.encode("utf-8")) for item in self.items) > MAX_TOTAL_TEXT_BYTES:
            raise ValueError("source evidence total text exceeds limit")
        if self.truncated != (self.omitted_count > 0):
            raise ValueError("source evidence truncation flag mismatch")
        projected = self.model_dump(mode="json", by_alias=True, exclude={"diagnostics_digest"})
        if self.diagnostics_digest != _digest(projected):
            raise ValueError("source evidence diagnostics digest mismatch")
        return self


def _candidate(item: Any, *, rank: int, tokenizer: TokenEstimator) -> dict[str, object] | None:
    if item.layer != "archival":
        return None
    item_id = _valid_id(item.item_id)
    archive_id = _valid_id(item.metadata.get("archive_id"))
    document_id = _valid_id(item.metadata.get("document_id"))
    text = item.text
    if item_id is None or archive_id is None or document_id is None:
        return None
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_ITEM_TEXT_BYTES:
        return None
    refs: list[dict[str, str]] = []
    for ref in item.source_refs:
        source_type = getattr(ref.source_type, "value", ref.source_type)
        source_id = _valid_id(ref.source_id)
        if source_type != "document" or source_id is None:
            return None
        refs.append({"source_type": "document", "source_id": source_id})
    if not 1 <= len(refs) <= MAX_SOURCE_REFS:
        return None
    score = item.metadata.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    try:
        score_value = float(score)
    except OverflowError:
        return None
    if not isfinite(score_value):
        return None
    tokens = tokenizer.count(text)
    return {
        "item_id": item_id,
        "archive_id": archive_id,
        "document_id": document_id,
        "source_refs": refs,
        "text": text,
        "estimated_tokens": tokens,
        "content_sha256": f"sha256:{sha256(text.encode('utf-8')).hexdigest()}",
        "score": score_value,
        "rank": rank,
        "truncated": False,
    }


def _payload(items: list[dict[str, object]], omitted_count: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": SOURCE_EVIDENCE_SCHEMA,
        "items": items,
        "omitted_count": omitted_count,
        "estimated_tokens": sum(cast(int, item["estimated_tokens"]) for item in items),
        "truncated": omitted_count > 0,
    }
    payload["diagnostics_digest"] = _digest(payload)
    return payload


def build_source_evidence(
    package: ContextPackage,
    *,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, object]:
    """Project a full context package into a bounded, source-proven archival envelope."""
    if not 0 < max_items <= DEFAULT_MAX_ITEMS:
        raise ValueError("source evidence max_items must be between 1 and 8")
    if not 0 < max_tokens <= DEFAULT_MAX_TOKENS:
        raise ValueError("source evidence max_tokens must be between 1 and 800")
    if not 0 < max_bytes <= DEFAULT_MAX_BYTES:
        raise ValueError("source evidence max_bytes must be between 1 and 65536")
    raw_v3 = package.metadata.get("v3_context")
    if not isinstance(raw_v3, dict):
        raise ValueError("source_evidence_v3_context_missing")
    try:
        context = ContextPackageV3.model_validate(raw_v3)
    except Exception as exc:
        raise ValueError("source_evidence_v3_context_invalid") from exc

    tokenizer = TokenEstimator()
    eligible: list[dict[str, object]] = []
    omitted_count = 0
    for context_item in context.items:
        candidate = _candidate(
            context_item,
            rank=len(eligible) + 1,
            tokenizer=tokenizer,
        )
        if candidate is None:
            omitted_count += 1
        else:
            eligible.append(candidate)

    selected: list[dict[str, object]] = []
    used_tokens = 0
    used_text_bytes = 0
    for index, candidate_item in enumerate(eligible):
        item_tokens = cast(int, candidate_item["estimated_tokens"])
        item_text_bytes = len(cast(str, candidate_item["text"]).encode("utf-8"))
        if (
            len(selected) >= max_items
            or used_tokens + item_tokens > max_tokens
            or used_text_bytes + item_text_bytes > MAX_TOTAL_TEXT_BYTES
        ):
            omitted_count += len(eligible) - index
            break
        selected.append(candidate_item)
        used_tokens += item_tokens
        used_text_bytes += item_text_bytes

    while True:
        for rank, selected_item in enumerate(selected, start=1):
            selected_item["rank"] = rank
        payload = _payload(selected, omitted_count)
        if len(_canonical_bytes(payload)) <= max_bytes:
            validated = SourceEvidenceEnvelope.model_validate(payload)
            return validated.model_dump(mode="json", by_alias=True)
        if not selected:
            raise ValueError(_EMPTY_ENVELOPE_TOO_LARGE)
        selected.pop()
        omitted_count += 1


def validate_source_evidence(payload: object) -> dict[str, object]:
    envelope = SourceEvidenceEnvelope.model_validate(payload)
    if len(_canonical_bytes(envelope.model_dump(mode="json", by_alias=True))) > DEFAULT_MAX_BYTES:
        raise ValueError("source evidence byte limit exceeded")
    return envelope.model_dump(mode="json", by_alias=True)
