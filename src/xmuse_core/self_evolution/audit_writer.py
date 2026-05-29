"""Self-evolution audit read-model writer for the dashboard_auditability track.

Materialises a joined, human-readable audit snapshot into
``read_models/self_evolution_audit.json`` so the dashboard can serve a
structured view without reading raw store files.

The snapshot is a list of *audit entries*, one per lineage record.  Each entry
joins:

- the lineage record (source run, spawned graph, target tracks, timestamps)
- the matching evolution conversation (system-authored, visible in chat)
- the matching evolution proposal (scope, why_now, review status)
- the matching run-terminal aggregation (lane counts, blocked objects)
- the matching guardrail decision (action, rationale, reason codes)
- a human-readable ``status_label`` derived from the proposal status

The writer is intentionally read-only with respect to the store; it only
writes to ``read_models/``.

Schema version 1 entry shape (``SelfEvolutionAuditEntry``):

    lineage_id, source_run_id, spawned_graph_id, spawned_resolution_id,
    spawned_conversation_id, blueprint_set_id, target_track_ids, created_at,
    proposal?  { proposal_id, scope_summary, target_track_ids, status,
                  review_status, candidate_lane_count, feature_groups,
                  status_label, author_session_id },
    aggregation? { aggregation_id, status, reason, terminal, lane_counts,
                   blocked_object_count, final_action_hold_count },
    conversation? { conversation_id, created_by, created_at },
    guardrail_decision? { decision_id, action, rationale, reason_codes }
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xmuse_core.self_evolution.store import SelfEvolutionStore


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


_PROPOSAL_STATUS_LABELS: dict[str, str] = {
    "drafting": "drafting",
    "awaiting_review": "awaiting review",
    "narrowed_for_redraft": "narrowed – redraft required",
    "approved": "approved",
    "rejected": "rejected",
    "guardrail_blocked": "blocked by guardrail",
    "landed": "landed",
}


def _status_label(proposal_status: str) -> str:
    return _PROPOSAL_STATUS_LABELS.get(proposal_status, proposal_status)


class SelfEvolutionAuditWriter:
    """Materialises a self-evolution audit snapshot into the read-models dir.

    Parameters
    ----------
    store_root:
        Path to the ``self_evolution/`` directory (same root used by
        :class:`~xmuse_core.self_evolution.store.SelfEvolutionStore`).
    read_models_root:
        Path to the ``read_models/`` directory where the snapshot is written.
        Defaults to ``<store_root>/../read_models``.
    """

    AUDIT_FILE = "self_evolution_audit.json"
    CONVERSATIONS_FILE = "self_evolution_conversations.json"
    CLARIFICATION_FILE = "self_evolution_clarifications.json"

    def __init__(
        self,
        store_root: Path | str,
        read_models_root: Path | str | None = None,
    ) -> None:
        self._store = SelfEvolutionStore(store_root)
        store_path = Path(store_root)
        self._read_models_root = (
            Path(read_models_root)
            if read_models_root is not None
            else store_path.parent / "read_models"
        )

    @property
    def audit_path(self) -> Path:
        return self._read_models_root / self.AUDIT_FILE

    @property
    def conversations_path(self) -> Path:
        return self._read_models_root / self.CONVERSATIONS_FILE

    @property
    def clarification_path(self) -> Path:
        return self._read_models_root / self.CLARIFICATION_FILE

    def write(self) -> dict[str, Any]:
        """Build and persist the audit snapshot.

        Returns the written payload so callers can inspect it without a
        second read.
        """
        audit_entries = self._build_audit_entries()
        conversations_entries = self._build_conversations_entries()
        clarification_entries = self._build_clarification_entries()

        audit_payload: dict[str, Any] = {
            "schema_version": "1",
            "generated_at": _utc_now(),
            "entries": audit_entries,
        }
        conversations_payload: dict[str, Any] = {
            "schema_version": "1",
            "conversations": conversations_entries,
        }
        clarification_payload: dict[str, Any] = {
            "schema_version": "1",
            "clarification_requests": clarification_entries["requests"],
            "clarification_resolutions": clarification_entries["resolutions"],
        }

        _write_atomic(self.audit_path, audit_payload)
        _write_atomic(self.conversations_path, conversations_payload)
        _write_atomic(self.clarification_path, clarification_payload)

        return audit_payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_audit_entries(self) -> list[dict[str, Any]]:
        lineage_records = self._store.list_lineage()
        proposals_by_id = {p.proposal_id: p for p in self._store.list_proposals()}
        aggregations_by_run = {
            a.run_id: a for a in self._store.list_aggregations()
        }
        conversations_by_id = {
            c.conversation_id: c for c in self._store.list_conversations()
        }
        # Index guardrail decisions by proposal_id for O(1) join
        guardrails_by_proposal: dict[str, Any] = {
            g.proposal_id: g for g in self._store.list_guardrail_decisions()
        }

        entries: list[dict[str, Any]] = []
        for record in lineage_records:
            proposal = proposals_by_id.get(record.evolution_proposal_id)
            aggregation = aggregations_by_run.get(record.source_run_id)
            conversation = conversations_by_id.get(record.spawned_conversation_id)

            entry: dict[str, Any] = {
                "lineage_id": record.lineage_id,
                "source_run_id": record.source_run_id,
                "spawned_graph_id": record.spawned_graph_id,
                "spawned_resolution_id": record.spawned_resolution_id,
                "spawned_conversation_id": record.spawned_conversation_id,
                "blueprint_set_id": record.blueprint_set_id,
                "target_track_ids": list(record.target_track_ids),
                "created_at": record.created_at,
            }

            if proposal is not None:
                candidate_lanes: list[dict[str, Any]] = proposal.candidate_graph.get(
                    "lanes", []
                )
                feature_groups: list[str] = sorted(
                    {
                        lane["feature_group"]
                        for lane in candidate_lanes
                        if isinstance(lane, dict) and lane.get("feature_group")
                    }
                )
                entry["proposal"] = {
                    "proposal_id": proposal.proposal_id,
                    "scope_summary": proposal.scope_summary,
                    "target_track_ids": list(proposal.target_track_ids),
                    "status": proposal.status.value,
                    "review_status": proposal.review_status,
                    "candidate_lane_count": len(candidate_lanes),
                    "feature_groups": feature_groups,
                    # Extra fields useful for the dashboard but not in the
                    # minimal contract — kept for backward compatibility.
                    "status_label": _status_label(proposal.status.value),
                    "author_session_id": proposal.author_session_id,
                }
            else:
                entry["proposal"] = {
                    "proposal_id": record.evolution_proposal_id,
                    "scope_summary": "",
                    "target_track_ids": list(record.target_track_ids),
                    "status": "unknown",
                    "review_status": "unknown",
                    "candidate_lane_count": 0,
                    "feature_groups": [],
                    "status_label": "unknown",
                    "author_session_id": None,
                }

            if aggregation is not None:
                entry["aggregation"] = {
                    "aggregation_id": aggregation.aggregation_id,
                    "status": aggregation.status.value,
                    "reason": aggregation.reason,
                    "terminal": aggregation.terminal,
                    "lane_counts": dict(aggregation.lane_counts),
                    "blocked_object_count": len(aggregation.blocked_objects),
                    "final_action_hold_count": len(aggregation.final_action_holds),
                }

            if conversation is not None:
                entry["conversation"] = {
                    "conversation_id": conversation.conversation_id,
                    "created_by": conversation.created_by,
                    "created_at": conversation.created_at,
                }

            # Join guardrail decision via the proposal_id on the lineage record
            guardrail = guardrails_by_proposal.get(record.evolution_proposal_id)
            if guardrail is not None:
                entry["guardrail_decision"] = {
                    "decision_id": guardrail.decision_id,
                    "action": guardrail.action.value,
                    "rationale": guardrail.rationale,
                    "reason_codes": list(guardrail.reason_codes),
                }

            entries.append(entry)

        # Most-recent first
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return entries

    def _build_conversations_entries(self) -> list[dict[str, Any]]:
        conversations = self._store.list_conversations()
        proposals_by_id = {p.proposal_id: p for p in self._store.list_proposals()}

        result: list[dict[str, Any]] = []
        for conv in conversations:
            proposal = proposals_by_id.get(conv.proposal_id)
            entry: dict[str, Any] = {
                "conversation_id": conv.conversation_id,
                "proposal_id": conv.proposal_id,
                "source_run_id": conv.source_run_id,
                "created_by": conv.created_by,
                "created_at": conv.created_at,
            }
            if proposal is not None:
                entry["target_track_ids"] = list(proposal.target_track_ids)
                entry["scope_summary"] = proposal.scope_summary
                entry["proposal_status"] = proposal.status.value
                entry["status_label"] = _status_label(proposal.status.value)
                # spawned_resolution_id is set on the proposal once the
                # approved resolution is created during landing.
                entry["spawned_resolution_id"] = proposal.spawned_resolution_id
            else:
                entry["spawned_resolution_id"] = None
            result.append(entry)

        result.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return result

    def _build_clarification_entries(self) -> dict[str, list[dict[str, Any]]]:
        """Build clarification request and resolution entries for the read model.

        Each request entry is joined with its resolution (if one exists) so the
        dashboard can show the full lifecycle of a blocked run in one place.
        """
        requests = self._store.list_clarification_requests()
        resolutions = self._store.list_clarification_resolutions()
        resolutions_by_request = {r.request_id: r for r in resolutions}

        request_entries: list[dict[str, Any]] = []
        for req in requests:
            entry: dict[str, Any] = {
                "request_id": req.request_id,
                "source_run_id": req.source_run_id,
                "aggregation_id": req.aggregation_id,
                "missing_input_summary": req.missing_input_summary,
                "owner": req.owner,
                "resume_path": req.resume_path,
                "status": req.status.value,
                "created_at": req.created_at,
            }
            if req.resolved_at is not None:
                entry["resolved_at"] = req.resolved_at
            if req.blocked_objects:
                entry["blocked_objects"] = list(req.blocked_objects)
            resolution = resolutions_by_request.get(req.request_id)
            if resolution is not None:
                entry["resolution_id"] = resolution.resolution_id
                entry["provided_by"] = resolution.provided_by
                entry["spawned_graph_id"] = resolution.spawned_graph_id
            request_entries.append(entry)

        request_entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)

        resolution_entries: list[dict[str, Any]] = []
        for res in resolutions:
            resolution_entries.append(
                {
                    "resolution_id": res.resolution_id,
                    "request_id": res.request_id,
                    "source_run_id": res.source_run_id,
                    "provided_information": res.provided_information,
                    "provided_by": res.provided_by,
                    "spawned_conversation_id": res.spawned_conversation_id,
                    "spawned_resolution_id": res.spawned_resolution_id,
                    "spawned_graph_id": res.spawned_graph_id,
                    "created_at": res.created_at,
                }
            )

        resolution_entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return {"requests": request_entries, "resolutions": resolution_entries}
