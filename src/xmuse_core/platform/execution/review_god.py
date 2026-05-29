from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from memoryos_lite.observability import log_event
from xmuse_core.platform.agent_spawner import GodConfig
from xmuse_core.platform.execution.review import (
    infer_review_fallback,
    is_spawn_transient,
    review_infra_failure_reason,
    review_infra_reason_from_exception,
    spawn_result_transient,
)
from xmuse_core.platform.execution.transport import Transport
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.self_evolution.recovery import (
    CircuitOpenError,
    RecoveryEvent,
    RecoveryManager,
)
from xmuse_core.structuring.models import ReviewDecision

logger = logging.getLogger(__name__)

_COMPONENT = "orchestrator.review_god"
REVIEW_INFRA_RETRY_DELAY_S = 15 * 60


def _record_spawn_outcome(
    lane_id: str,
    result: Any,
    recovery: RecoveryManager,
    observer: Callable[[RecoveryEvent], None],
) -> None:
    if result.timed_out or spawn_result_transient(result):
        recovery.circuit(_COMPONENT).record_failure()
        if recovery.circuit(_COMPONENT).state.value == "open":
            observer(
                RecoveryEvent(
                    component=_COMPONENT,
                    operation="spawn",
                    kind="circuit_opened",
                    attempt=1,
                    max_attempts=recovery.config.max_attempts,
                    error_type="SpawnResult",
                    error=result.stderr or result.stdout or "review spawn failed",
                    circuit_state="open",
                )
            )
        observer(
            RecoveryEvent(
                component=_COMPONENT,
                operation="spawn",
                kind="operation_failed",
                attempt=1,
                max_attempts=recovery.config.max_attempts,
                error_type="SpawnResult",
                error=result.stderr or result.stdout or "review spawn failed",
                circuit_state=recovery.circuit(_COMPONENT).state.value,
            )
        )
    else:
        recovery.circuit(_COMPONENT).record_success()


async def run_review_god(
    *,
    lane_id: str,
    lane: dict[str, Any],
    god: GodConfig,
    prompt: str,
    worktree: Path,
    sm: LaneStateMachine,
    recovery: RecoveryManager,
    transport: Transport,
    observer: Callable[[RecoveryEvent], None],
    open_review_task: Callable[[str], Any],
    stable_verdict_id: Callable[[str], str],
    ingest_merge_verdict: Callable[[str, str], None],
    ingest_rework_verdict: Callable[[str, str], None],
    on_reviewed: Callable[[str], Awaitable[None]],
    on_rejected: Callable[[str], Awaitable[None]],
) -> None:
    log_event(
        logger,
        logging.INFO,
        "review_god_started",
        lane_id=lane_id,
        god=god.name,
        god_runtime=god.runtime,
    )

    metadata = {
        "god": god.name,
        "review_started_at": time.time(),
    }
    if lane.get("status") != "gated":
        sm.transition(lane_id, "gated", metadata=metadata)
    else:
        sm.update_metadata(lane_id, metadata)

    open_review_task(lane_id)

    try:
        result = await recovery.execute_async(
            _COMPONENT,
            "spawn",
            lambda: transport.spawn_god(
                god=god,
                lane_id=lane_id,
                prompt=prompt,
                worktree=worktree,
            ),
            is_transient=is_spawn_transient,
            observer=observer,
        )
    except CircuitOpenError as exc:
        sm.transition(
            lane_id,
            "gate_failed",
            metadata={
                "failure_reason": "review_infra_unavailable",
                "review_infra_reason": "circuit_open",
                "review_retry_after_at": time.time() + exc.retry_after_s,
                "degraded_component": "review_god",
            },
        )
        return
    except Exception as exc:
        sm.transition(
            lane_id,
            "gate_failed",
            metadata={
                "failure_reason": "review_infra_unavailable"
                if is_spawn_transient(exc)
                else "review_spawn_failed",
                "review_infra_reason": review_infra_reason_from_exception(exc),
                "review_retry_after_at": time.time() + REVIEW_INFRA_RETRY_DELAY_S,
                "failure_error": str(exc),
            },
        )
        return

    _record_spawn_outcome(lane_id, result, recovery, observer)

    if result.timed_out:
        sm.transition(
            lane_id, "gate_failed", metadata={"failure_reason": "review_timeout"}
        )
        return

    if result.exit_code != 0:
        infra_reason = review_infra_failure_reason(result)
        if infra_reason is not None:
            sm.transition(
                lane_id,
                "gate_failed",
                metadata={
                    "failure_reason": "review_infra_unavailable",
                    "review_infra_reason": infra_reason,
                    "review_retry_after_at": time.time() + REVIEW_INFRA_RETRY_DELAY_S,
                },
            )
            return
        sm.transition(
            lane_id,
            "gate_failed",
            metadata={"failure_reason": "review_non_zero_exit"},
        )
        return

    current = sm.get_lane(lane_id)
    if current.get("status") == "gated" and not result.stdout.strip():
        sm.transition(
            lane_id,
            "gate_failed",
            metadata={"failure_reason": "review_no_verdict"},
        )
        return

    if current.get("status") == "gated" and result.stdout.strip():
        decision, summary, reason = infer_review_fallback(result.stdout)
        if decision == "reviewed":
            verdict_id = stable_verdict_id(lane_id)
            sm.transition(
                lane_id,
                "reviewed",
                metadata={
                    "review_decision": ReviewDecision.MERGE.value,
                    "review_summary": summary,
                    "review_fallback": "stdout",
                    "review_fallback_reason": reason,
                    "review_verdict_id": verdict_id,
                },
            )
            ingest_merge_verdict(lane_id, summary)
            await on_reviewed(lane_id)
        else:
            sm.transition(
                lane_id,
                "rejected",
                metadata={
                    "review_decision": ReviewDecision.REWORK.value,
                    "review_summary": summary,
                    "review_fallback": "stdout",
                    "review_fallback_reason": reason,
                },
            )
            ingest_rework_verdict(lane_id, summary)
            await on_rejected(lane_id)
