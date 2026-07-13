from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONTRACT_DIGEST = "sha256:03ed21bdc04bed3db221f755e2920700a74730d1615d853bc91c2b52a89eb0dc"
DIAGNOSTICS_DIGEST = "sha256:662ce085d09e8c6889926d698abb2ac35bcb97b06e2fac62b7491d7b4282acd0"
TOP_LEVEL_KEYS = {
    "schema",
    "items",
    "omitted_count",
    "estimated_tokens",
    "truncated",
    "diagnostics_digest",
}
ITEM_KEYS = {
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
FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
GOLDEN = FIXTURES / "memoryos_source_evidence_v1.json"
DIGEST = FIXTURES / "memoryos_source_evidence_v1.sha256"


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_source_evidence_golden_is_canonical_utf8_and_digest_frozen() -> None:
    raw = GOLDEN.read_bytes()
    payload = json.loads(raw)

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not raw.endswith(b"\n")
    assert raw == _canonical(payload)
    assert _sha256(raw) == CONTRACT_DIGEST
    assert DIGEST.read_bytes() == CONTRACT_DIGEST.encode("ascii")


def test_source_evidence_golden_freezes_exact_wire_and_proofs() -> None:
    payload = json.loads(GOLDEN.read_bytes())

    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema"] == "memoryos_source_evidence/v1"
    assert payload["estimated_tokens"] == 20
    assert payload["omitted_count"] == 1
    assert payload["truncated"] is True
    items = payload["items"]
    assert len(items) == 2
    assert [item["rank"] for item in items] == [1, 2]
    assert all(set(item) == ITEM_KEYS for item in items)
    assert items[0]["source_refs"] == [{"source_id": "activity-001", "source_type": "document"}]
    assert items[1]["source_refs"] == [
        {"source_id": "activity-002", "source_type": "document"},
        {"source_id": "activity-003", "source_type": "document"},
    ]
    assert items[1]["text"] == "项目偏好：默认使用只读沙箱 🧠"
    for item in items:
        assert item["content_sha256"] == _sha256(item["text"].encode("utf-8"))
        assert item["truncated"] is False
    diagnostic_payload = {
        key: value for key, value in payload.items() if key != "diagnostics_digest"
    }
    assert payload["diagnostics_digest"] == DIAGNOSTICS_DIGEST
    assert payload["diagnostics_digest"] == _sha256(_canonical(diagnostic_payload))
