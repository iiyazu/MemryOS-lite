from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from memoryos_lite.observability import log_event
from xmuse_core.platform.agent_spawner import GodConfig
from xmuse_core.platform.execution.review import (
    is_spawn_transient,
    spawn_result_transient,
)
from xmuse_core.platform.execution.transport import Transport
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.self_evolution.recovery import (
    CircuitOpenError,
    RecoveryEvent,
    RecoveryManager,
)

logger = logging.getLogger(__name__)

_COMPONENT = "orchestrator.execution_god"


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
                    error=result.stderr or result.stdout or "execution spawn failed",
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
                error=result.stderr or result.stdout or "execution spawn failed",
                circuit_state=recovery.circuit(_COMPONENT).state.value,
            )
        )
    else:
        recovery.circuit(_COMPONENT).record_success()


async def run_execution_god(
    *,
    lane_id: str,
    god: GodConfig,
    prompt: str,
    worktree: Path,
    sm: LaneStateMachine,
    recovery: RecoveryManager,
    transport: Transport,
    observer: Callable[[RecoveryEvent], None],
    on_executed: Callable[[str], Awaitable[None]],
) -> None:
    log_event(
        logger,
        logging.INFO,
        "execution_god_started",
        lane_id=lane_id,
        god=god.name,
        god_runtime=god.runtime,
    )
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
            "exec_failed",
            metadata={
                "failure_reason": "execution_circuit_open",
                "retry_after_s": exc.retry_after_s,
                "degraded_component": "execution_god",
            },
        )
        return
    except Exception as exc:
        sm.transition(
            lane_id,
            "exec_failed",
            metadata={
                "failure_reason": "execution_infra_unavailable"
                if is_spawn_transient(exc)
                else "execution_spawn_failed",
                "failure_error": str(exc),
            },
        )
        return

    _record_spawn_outcome(lane_id, result, recovery, observer)

    if result.timed_out:
        sm.transition(lane_id, "exec_failed", metadata={"failure_reason": "timeout"})
        return

    current = sm.get_lane(lane_id)
    if current["status"] == "dispatched":
        if result.exit_code == 0:
            log_event(logger, logging.INFO, "execution_god_completed", lane_id=lane_id)
            sm.transition(lane_id, "executed")
            await on_executed(lane_id)
        else:
            sm.transition(
                lane_id, "exec_failed", metadata={"failure_reason": "non_zero_exit"}
            )
    elif current["status"] == "executed" and result.exit_code == 0:
        await on_executed(lane_id)
