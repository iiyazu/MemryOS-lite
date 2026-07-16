from __future__ import annotations

import hashlib
import json
import math

import pytest
from pydantic import ValidationError

from memoryos_lite.schemas import ContextPackage
from memoryos_lite.source_evidence import (
    SOURCE_EVIDENCE_SCHEMA,
    SourceEvidenceV2Item,
    SourceEvidenceV2Ref,
    build_source_evidence,
    validate_source_evidence,
)
from memoryos_lite.v3_contracts import (
    ContextLayerItem,
    ContextPackageV3,
    SourceRef,
    SourceType,
)


def _item(
    item_id: str,
    text: str = "a grounded archival fact",
    *,
    layer: str = "archival",
    proved: bool = True,
    archive_id: str | None = "archive-1",
    document_id: str | None = "document-1",
    score: object = 0.75,
) -> ContextLayerItem:
    refs = (
        [SourceRef(source_type=SourceType.DOCUMENT, source_id=f"source-{item_id}")]
        if proved
        else [SourceRef(source_type=SourceType.MESSAGE, source_id=f"message-{item_id}")]
    )
    return ContextLayerItem(
        layer=layer,  # type: ignore[arg-type]
        item_id=item_id,
        text=text,
        estimated_tokens=9999,
        source_refs=refs,
        metadata={
            "archive_id": archive_id,
            "document_id": document_id,
            "score": score,
            "private": "not projected",
        },
    )


def _package(*items: ContextLayerItem) -> ContextPackage:
    v3 = ContextPackageV3(session_id="session-1", task="recall", items=list(items))
    return ContextPackage(
        session_id="session-1",
        task="recall",
        metadata={"v3_context": v3.model_dump(mode="json")},
    )


def _size(payload: object) -> int:
    return len(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def test_projects_exact_wire_with_complete_source_proof() -> None:
    envelope = build_source_evidence(
        _package(
            _item("recent", layer="recent"),
            _item("first", "first fact"),
            _item("unproved", proved=False),
            _item("second", "第二个事实", document_id="document-2"),
        )
    )

    assert set(envelope) == {
        "schema",
        "items",
        "omitted_count",
        "estimated_tokens",
        "truncated",
        "diagnostics_digest",
    }
    assert envelope["schema"] == SOURCE_EVIDENCE_SCHEMA
    assert [item["item_id"] for item in envelope["items"]] == ["first", "second"]
    assert [item["rank"] for item in envelope["items"]] == [1, 2]
    assert set(envelope["items"][0]) == {
        "item_id",
        "archive_id",
        "document_id",
        "source_refs",
        "text",
        "estimated_tokens",
        "content_sha256",
        "score",
        "rank",
        "truncated",
    }
    assert envelope["items"][0]["source_refs"] == [
        {"source_type": "document", "source_id": "source-first"}
    ]
    assert envelope["items"][0]["truncated"] is False
    assert envelope["omitted_count"] == 2
    assert envelope["truncated"] is True
    assert "private" not in json.dumps(envelope)
    assert validate_source_evidence(envelope) == envelope


def test_item_and_token_limits_drop_a_stable_whole_tail() -> None:
    items = [_item(f"item-{index}", "one two three") for index in range(10)]
    item_limited = build_source_evidence(_package(*items), max_items=3)
    assert [item["item_id"] for item in item_limited["items"]] == [
        "item-0",
        "item-1",
        "item-2",
    ]
    assert item_limited["omitted_count"] == 7

    token_limited = build_source_evidence(_package(*items), max_tokens=7)
    assert [item["item_id"] for item in token_limited["items"]] == [
        "item-0",
        "item-1",
    ]
    assert token_limited["omitted_count"] == 8
    assert token_limited["estimated_tokens"] <= 7


def test_text_and_byte_bounds_drop_items_without_partial_text() -> None:
    oversized = _item("oversized", "界" * 3000)
    byte_package = _package(_item("first", "alpha"), _item("second", "β" * 500))
    one_item = build_source_evidence(byte_package, max_items=1)
    envelope = build_source_evidence(
        byte_package,
        max_bytes=_size(one_item) + 80,
    )
    invalid = build_source_evidence(_package(oversized, _item("valid", "whole")))

    assert [item["item_id"] for item in envelope["items"]] == ["first"]
    assert envelope["items"][0]["text"] == "alpha"
    assert envelope["items"][0]["truncated"] is False
    assert envelope["omitted_count"] == 1
    assert [item["item_id"] for item in invalid["items"]] == ["valid"]
    assert invalid["omitted_count"] == 1


def test_invalid_ids_and_missing_proof_are_omitted_fail_closed() -> None:
    too_many_refs = _item("too-many-refs")
    too_many_refs.source_refs = [
        SourceRef(source_type=SourceType.DOCUMENT, source_id=f"source-{index}")
        for index in range(9)
    ]
    envelope = build_source_evidence(
        _package(
            _item("x" * 513),
            _item("missing-archive", archive_id=None),
            _item("missing-document", document_id=None),
            _item("no-document-proof", proved=False),
            _item("missing-score", score=None),
            too_many_refs,
        )
    )
    assert envelope["items"] == []
    assert envelope["omitted_count"] == 6


def test_empty_envelope_too_large_has_stable_reason() -> None:
    with pytest.raises(ValueError, match="source_evidence_empty_envelope_exceeds_byte_limit"):
        build_source_evidence(_package(), max_bytes=16)


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_non_finite_scores_are_omitted_before_json_serialization(score: float) -> None:
    envelope = build_source_evidence(
        _package(_item("invalid", score=score), _item("valid", "whole"))
    )

    assert [item["item_id"] for item in envelope["items"]] == ["valid"]
    assert envelope["omitted_count"] == 1
    assert envelope["truncated"] is True
    assert json.dumps(envelope, allow_nan=False)
    assert validate_source_evidence(envelope) == envelope


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("items", 0, "text"), "tampered"),
        (("items", 0, "rank"), 2),
        (("schema",), "memoryos_source_evidence/v2"),
        (("estimated_tokens",), 999),
        (("omitted_count",), 1),
        (("diagnostics_digest",), "sha256:" + "0" * 64),
        (("items", 0, "score"), math.nan),
    ],
)
def test_validation_rejects_mutated_evidence(path: tuple[object, ...], value: object) -> None:
    payload = build_source_evidence(_package(_item("fact")))
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        validate_source_evidence(payload)


def test_missing_or_invalid_v3_context_fails_closed() -> None:
    package = ContextPackage(session_id="session-1", task="recall")
    with pytest.raises(ValueError, match="source_evidence_v3_context_missing"):
        build_source_evidence(package)
    package.metadata["v3_context"] = {"items": "not-a-list"}
    with pytest.raises(ValueError, match="source_evidence_v3_context_invalid"):
        build_source_evidence(package)


def test_v2_refs_reject_internal_source_types_and_unscoped_messages() -> None:
    with pytest.raises(ValidationError):
        SourceEvidenceV2Ref(source_type="passage", source_id="passage-1")
    with pytest.raises(ValidationError):
        SourceEvidenceV2Ref(source_type="message", source_id="message-1")


def test_v2_items_reject_mixed_refs_and_archival_message_refs() -> None:
    common = {
        "item_id": "item-1",
        "text": "grounded fact",
        "estimated_tokens": 2,
        "content_sha256": "sha256:" + hashlib.sha256(b"grounded fact").hexdigest(),
        "derived": True,
        "source_complete": True,
        "rank": 1,
    }
    message = SourceEvidenceV2Ref(
        source_type="message", source_id="message-1", session_id="session-1"
    )
    document = SourceEvidenceV2Ref(source_type="document", source_id="document-1")
    with pytest.raises(ValidationError):
        SourceEvidenceV2Item(
            **common,
            layer="recall",
            source_refs=[message, document],
        )
    with pytest.raises(ValidationError):
        SourceEvidenceV2Item(
            **common,
            layer="archival",
            source_refs=[message],
        )


def test_v2_builder_omits_non_public_and_mixed_source_refs() -> None:
    internal = ContextLayerItem(
        layer="recall",
        item_id="internal",
        text="internal source",
        estimated_tokens=2,
        source_refs=[SourceRef(source_type=SourceType.PASSAGE, source_id="passage-1")],
        metadata={"score": 0.5},
    )
    mixed = ContextLayerItem(
        layer="recall",
        item_id="mixed",
        text="mixed source",
        estimated_tokens=2,
        source_refs=[
            SourceRef(
                source_type=SourceType.MESSAGE,
                source_id="message-1",
                session_id="session-1",
            ),
            SourceRef(source_type=SourceType.DOCUMENT, source_id="document-1"),
        ],
        metadata={"score": 0.5},
    )
    envelope = build_source_evidence(_package(internal, mixed), schema_version="v2")
    assert envelope["items"] == []
    assert envelope["omitted_count"] == 2
