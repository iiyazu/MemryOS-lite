from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar

from pydantic import BaseModel

from xmuse_core.self_evolution.models import (
    ClarificationRequest,
    ClarificationResolution,
    EvolutionBudgetWindow,
    EvolutionConversation,
    EvolutionDedupRecord,
    EvolutionGuardrailDecision,
    EvolutionLineageRecord,
    EvolutionProposal,
    EvolutionReviewDecision,
    RunTerminalAggregation,
    StructuredEvidenceBundle,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class SelfEvolutionStore:
    """Append-only JSON store for the first self-evolution bootstrap slice."""

    _FILES = {
        "aggregations": "run_aggregations.json",
        "evidence_bundles": "evidence_bundles.json",
        "proposals": "proposals.json",
        "review_decisions": "review_decisions.json",
        "guardrail_decisions": "guardrail_decisions.json",
        "conversations": "conversations.json",
        "lineage": "lineage.json",
        "budget_windows": "budget_windows.json",
        "dedup_records": "dedup_records.json",
        "clarification_requests": "clarification_requests.json",
        "clarification_resolutions": "clarification_resolutions.json",
    }

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def save_aggregation(self, item: RunTerminalAggregation) -> RunTerminalAggregation:
        self._upsert("aggregations", "aggregation_id", item)
        return item

    def save_evidence_bundle(self, item: StructuredEvidenceBundle) -> StructuredEvidenceBundle:
        self._upsert("evidence_bundles", "bundle_id", item)
        return item

    def save_proposal(self, item: EvolutionProposal) -> EvolutionProposal:
        self._upsert("proposals", "proposal_id", item)
        return item

    def save_review_decision(self, item: EvolutionReviewDecision) -> EvolutionReviewDecision:
        self._upsert("review_decisions", "decision_id", item)
        return item

    def save_guardrail_decision(
        self,
        item: EvolutionGuardrailDecision,
    ) -> EvolutionGuardrailDecision:
        self._upsert("guardrail_decisions", "decision_id", item)
        return item

    def save_conversation(self, item: EvolutionConversation) -> EvolutionConversation:
        self._upsert("conversations", "conversation_id", item)
        return item

    def save_lineage(self, item: EvolutionLineageRecord) -> EvolutionLineageRecord:
        self._upsert("lineage", "lineage_id", item)
        return item

    def save_budget_window(self, item: EvolutionBudgetWindow) -> EvolutionBudgetWindow:
        self._upsert("budget_windows", "window_id", item)
        return item

    def save_dedup_record(self, item: EvolutionDedupRecord) -> EvolutionDedupRecord:
        self._upsert("dedup_records", "dedup_key", item)
        return item

    def save_clarification_request(
        self, item: ClarificationRequest
    ) -> ClarificationRequest:
        self._upsert("clarification_requests", "request_id", item)
        return item

    def save_clarification_resolution(
        self, item: ClarificationResolution
    ) -> ClarificationResolution:
        self._upsert("clarification_resolutions", "resolution_id", item)
        return item

    def list_aggregations(self) -> list[RunTerminalAggregation]:
        return self._list("aggregations", RunTerminalAggregation)

    def list_evidence_bundles(self) -> list[StructuredEvidenceBundle]:
        return self._list("evidence_bundles", StructuredEvidenceBundle)

    def list_proposals(self) -> list[EvolutionProposal]:
        return self._list("proposals", EvolutionProposal)

    def list_review_decisions(self) -> list[EvolutionReviewDecision]:
        return self._list("review_decisions", EvolutionReviewDecision)

    def list_guardrail_decisions(self) -> list[EvolutionGuardrailDecision]:
        return self._list("guardrail_decisions", EvolutionGuardrailDecision)

    def list_lineage(self) -> list[EvolutionLineageRecord]:
        return self._list("lineage", EvolutionLineageRecord)

    def list_budget_windows(self) -> list[EvolutionBudgetWindow]:
        return self._list("budget_windows", EvolutionBudgetWindow)

    def list_conversations(self) -> list[EvolutionConversation]:
        return self._list("conversations", EvolutionConversation)

    def list_dedup_records(self) -> list[EvolutionDedupRecord]:
        return self._list("dedup_records", EvolutionDedupRecord)

    def list_clarification_requests(self) -> list[ClarificationRequest]:
        return self._list("clarification_requests", ClarificationRequest)

    def list_clarification_resolutions(self) -> list[ClarificationResolution]:
        return self._list("clarification_resolutions", ClarificationResolution)

    def path_for(self, collection: str) -> Path:
        return self._root / self._FILES[collection]

    def _upsert(self, collection: str, key: str, item: BaseModel) -> None:
        data = self._read(collection)
        rows = data.setdefault(collection, [])
        payload = item.model_dump(mode="json")
        data[collection] = [
            row for row in rows
            if isinstance(row, dict) and row.get(key) != payload[key]
        ]
        data[collection].append(payload)
        self._write(collection, data)

    def _list(self, collection: str, model: type[ModelT]) -> list[ModelT]:
        data = self._read(collection)
        rows = data.get(collection, [])
        if not isinstance(rows, list):
            return []
        return [model.model_validate(row) for row in rows if isinstance(row, dict)]

    def _read(self, collection: str) -> dict[str, Any]:
        path = self.path_for(collection)
        if not path.exists():
            return {collection: []}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {collection: []}

    def _write(self, collection: str, data: dict[str, Any]) -> None:
        path = self.path_for(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)
