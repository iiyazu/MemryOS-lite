"""Auto-spawn next self-evolution run when a graph terminalizes.

The platform runner can call ``TerminalRunWatcher.tick()`` from its idle loop.
On each tick the watcher looks for graphs that just reached a terminal state and
have not yet been used as a source run, then drives the controller through
aggregate -> evidence -> proposal -> review -> guardrail -> land.

For ``blocked_for_input`` runs the watcher records a ``ClarificationRequest``
rather than silently skipping.  The request stays open until an operator or
automated process calls ``SelfEvolutionController.resolve_clarification`` with
the provided information.

Intentional non-goals: the watcher does not retry held proposals, does not
mutate budget windows, and does not surface decisions other than "spawned",
"clarification_pending", or "skipped". Anything that goes ``HOLD`` or
``REJECT`` stays put for the operator to inspect via the dashboard read models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from xmuse_core.self_evolution.controller import SelfEvolutionController
from xmuse_core.self_evolution.models import (
    ClarificationRequest,
    EvolutionGuardrailAction,
    EvolutionLineageRecord,
    RunTerminalStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchOutcome:
    source_run_id: str
    spawned: EvolutionLineageRecord | None
    skip_reason: str | None
    clarification_request: ClarificationRequest | None = field(default=None)


class TerminalRunWatcher:
    def __init__(self, controller: SelfEvolutionController) -> None:
        self._controller = controller

    def tick(self) -> list[WatchOutcome]:
        outcomes: list[WatchOutcome] = []
        for source_run_id in self._candidate_source_runs():
            outcomes.append(self._handle_source(source_run_id))
        return outcomes

    def _candidate_source_runs(self) -> list[str]:
        already_consumed = {
            record.source_run_id for record in self._controller.store.list_lineage()
        }
        # Also skip runs that already have an open clarification request
        already_clarification = {
            req.source_run_id
            for req in self._controller.store.list_clarification_requests()
        }
        candidates: list[str] = []
        for path in sorted(self._controller._graph_store._root.glob("*.json")):
            graph_id = path.stem
            if graph_id in already_consumed:
                continue
            if graph_id in already_clarification:
                continue
            candidates.append(graph_id)
        return candidates

    def _handle_source(self, source_run_id: str) -> WatchOutcome:
        try:
            aggregation = self._controller.aggregate_run_terminal(source_run_id)
        except KeyError as exc:
            logger.warning("watcher: unknown graph %s: %s", source_run_id, exc)
            return WatchOutcome(source_run_id, None, "graph_not_found")

        if not aggregation.terminal:
            return WatchOutcome(source_run_id, None, f"not_terminal:{aggregation.status.value}")

        if aggregation.status is RunTerminalStatus.BLOCKED_FOR_INPUT:
            # Record a formal ClarificationRequest rather than silently skipping.
            # The request stays open until resolve_clarification is called.
            try:
                clarification_request = self._controller.record_clarification_request(
                    aggregation
                )
                logger.info(
                    "watcher: blocked run %s recorded as clarification request %s",
                    source_run_id,
                    clarification_request.request_id,
                )
                return WatchOutcome(
                    source_run_id,
                    None,
                    "clarification_pending",
                    clarification_request=clarification_request,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "watcher: failed to record clarification request for %s: %s",
                    source_run_id,
                    exc,
                )
                return WatchOutcome(source_run_id, None, "blocked_for_input")

        evidence = self._controller.build_evidence_bundle(aggregation)
        proposal = self._controller.draft_evolution_proposal(evidence)
        review = self._controller.review_proposal(proposal)
        guardrail = self._controller.guardrail_check(proposal, review, aggregation)

        if guardrail.action is not EvolutionGuardrailAction.CONTINUE:
            logger.info(
                "watcher: source %s held: %s",
                source_run_id,
                guardrail.reason_codes,
            )
            return WatchOutcome(
                source_run_id,
                None,
                f"guardrail_{guardrail.action.value}:{','.join(guardrail.reason_codes)}",
            )

        spawned = self._controller.land_evolution_run(proposal, review, guardrail, evidence)
        logger.info(
            "watcher: spawned %s from %s targeting %s",
            spawned.spawned_graph_id,
            source_run_id,
            proposal.target_track_ids,
        )
        return WatchOutcome(source_run_id, spawned, None)
