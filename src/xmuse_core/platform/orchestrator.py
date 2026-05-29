from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from memoryos_lite.observability import (
    current_observability_context,
    log_event,
    observability_context,
    timed_core_operation,
)
from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig
from xmuse_core.platform.event_bus import EventBus
from xmuse_core.platform.execution import gate as execution_gate
from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.projection.dependents import reproject_dependents_if_needed
from xmuse_core.platform.prompts.builders import (
    build_execution_prompt,
    build_review_prompt,
    build_review_verdict,
)
from xmuse_core.platform.review_plane import ReviewPlaneController
from xmuse_core.platform.selection.god_picker import GodPicker
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.platform.verdict_adapter import adapt_review_verdict
from xmuse_core.platform.verdicts.writer import (
    gate_report_ref_for_lane,
    ingest_merge_verdict,
    ingest_rework_verdict,
    stable_verdict_id_for_lane,
)
from xmuse_core.self_evolution.recovery import (
    CircuitOpenError,
    RecoveryConfig,
    RecoveryEvent,
    RecoveryManager,
    TransientRecoveryError,
)
from xmuse_core.structuring.graph_store import LaneGraphStore
from xmuse_core.structuring.models import (
    ReviewDecision,
    ReviewVerdict,
    RunTerminalAggregation,
    StructuredEvidenceBundle,
)
from xmuse_core.structuring.verdict_store import EvidenceBundleStore

logger = logging.getLogger(__name__)
DEFAULT_MCP_PORT = 8100
REVIEW_INFRA_RETRY_DELAY_S = 15 * 60
SUPPORTED_GOD_RUNTIMES = ("codex", "claude", "mixed")


def _lane_graph_id(lane: dict[str, Any] | None) -> str | None:
    graph_id = lane.get("graph_id") if isinstance(lane, dict) else None
    return str(graph_id) if graph_id else None


def _orchestrator_recovery_config() -> RecoveryConfig:
    return RecoveryConfig.from_env("XMUSE_RECOVERY")


def _resolve_god_runtime(explicit: str | None) -> str:
    runtime = explicit or os.environ.get("XMUSE_GOD_RUNTIME") or "codex"
    if runtime not in SUPPORTED_GOD_RUNTIMES:
        raise ValueError(
            f"unsupported god runtime: {runtime!r}; expected one of {SUPPORTED_GOD_RUNTIMES}"
        )
    return runtime


def _execution_god(runtime: str) -> GodConfig:
    return GodConfig(
        name="execution-god",
        runtime=runtime,
        timeout_s=3600,
        skill_prompt_path="xmuse/god_prompts/execution_god.md",
    )


def _review_god(runtime: str) -> GodConfig:
    return GodConfig(
        name="review-god",
        runtime=runtime,
        timeout_s=900,
        skill_prompt_path="xmuse/god_prompts/review_god.md",
    )


EXECUTION_GOD = _execution_god("codex")
REVIEW_GOD = _review_god("codex")


class PlatformOrchestrator:
    def __init__(
        self,
        *,
        lanes_path: Path,
        xmuse_root: Path,
        mcp_port: int = DEFAULT_MCP_PORT,
        require_final_action_approval: bool = False,
        god_runtime: str | None = None,
    ) -> None:
        self._lanes_path = lanes_path
        self._sm = LaneStateMachine(lanes_path)
        self._bus = EventBus()
        self._spawner = AgentSpawner(repo_root=xmuse_root, mcp_port=mcp_port)
        self._root = xmuse_root
        self._graph_store = LaneGraphStore(self._root / "lane_graphs")
        self._require_final_action_approval = require_final_action_approval
        self._final_action_store = FinalActionGateStore(self._root / "final_actions.json")
        self._recovery = RecoveryManager(
            _orchestrator_recovery_config(),
            observer=self._observe_recovery_event,
            async_sleep=asyncio.sleep,
        )
        self._review_plane = ReviewPlaneController(
            lanes_path=lanes_path,
            store_path=self._root / "review_plane.json",
            final_actions_path=self._root / "final_actions.json",
            require_final_action_approval=require_final_action_approval,
        )
        runtime = _resolve_god_runtime(god_runtime)
        self._runtime_mode = runtime
        if runtime == "mixed":
            self._execution_gods = [_execution_god("codex"), _execution_god("claude")]
            self._review_gods = [_review_god("codex"), _review_god("claude")]
            self._execution_god = self._execution_gods[0]
            self._review_god = self._review_gods[0]
        else:
            self._execution_god = _execution_god(runtime)
            self._review_god = _review_god(runtime)
            self._execution_gods = [self._execution_god]
            self._review_gods = [self._review_god]
        self._mixed_cursor = 0
        self._god_picker = GodPicker(
            runtime_mode=runtime,
            execution_gods=self._execution_gods,
            review_gods=self._review_gods,
            lane_reader=self._sm.get_lane,
        )
        self._tools = McpToolHandler(
            state_machine=self._sm,
            xmuse_root=xmuse_root,
            on_status_change=self._on_mcp_status_change,
        )
        self._bus.subscribe("lane_reviewed", self._handle_lane_reviewed)
        self._bus.subscribe("lane_rejected", self._handle_lane_rejected)
        self._bus.subscribe("lane_executed", self._handle_lane_executed)

    def _observe_recovery_event(self, event: RecoveryEvent) -> None:
        log_event(
            logger,
            logging.INFO,
            "orchestrator_recovery_event",
            recovery_event=event.to_payload(),
        )

    def _lane_recovery_observer(self, lane_id: str):
        def _observe(event: RecoveryEvent) -> None:
            try:
                lane = self._sm.get_lane(lane_id)
            except KeyError:
                log_event(
                    logger,
                    logging.INFO,
                    "lane_recovery_event_missing_lane",
                    lane_id=lane_id,
                    recovery_event=event.to_payload(),
                )
                return
            history = lane.get("recovery_events", [])
            if not isinstance(history, list):
                history = []
            history = [*history[-19:], event.to_payload()]
            self._sm.update_metadata(
                lane_id,
                {
                    "recovery_events": history,
                    "last_recovery_event": event.to_payload(),
                },
            )

        return _observe

    def _on_mcp_status_change(self, lane_id: str, new_status: str) -> None:
        event_map = {
            "executed": "lane_executed",
            "exec_failed": "lane_exec_failed",
            "reviewed": "lane_reviewed",
            "rejected": "lane_rejected",
            "gate_failed": "lane_gate_failed",
        }
        event = event_map.get(new_status)
        if event:
            with observability_context(lane_id=lane_id):
                log_event(
                    logger,
                    logging.INFO,
                    "mcp_status_change",
                    lane_id=lane_id,
                    status=new_status,
                    event_name=event,
                )
                asyncio.get_event_loop().create_task(
                    self._bus.publish(
                        event,
                        {
                            "lane_id": lane_id,
                            "observability": current_observability_context(),
                        },
                    )
                )

    async def _handle_lane_reviewed(self, payload: dict[str, Any]) -> None:
        context = payload.get("observability")
        with observability_context(
            trace_id=context.get("trace_id") if isinstance(context, dict) else None,
            lane_id=str(payload["lane_id"]),
        ):
            await self.on_lane_reviewed(str(payload["lane_id"]))

    async def _handle_lane_rejected(self, payload: dict[str, Any]) -> None:
        context = payload.get("observability")
        with observability_context(
            trace_id=context.get("trace_id") if isinstance(context, dict) else None,
            lane_id=str(payload["lane_id"]),
        ):
            await self.on_lane_rejected(str(payload["lane_id"]))

    async def _handle_lane_executed(self, payload: dict[str, Any]) -> None:
        context = payload.get("observability")
        with observability_context(
            trace_id=context.get("trace_id") if isinstance(context, dict) else None,
            lane_id=str(payload["lane_id"]),
        ):
            await self._on_lane_executed(str(payload["lane_id"]))

    def _should_retry_review(self, lane: dict[str, Any]) -> bool:
        if lane.get("gate_passed") is not True:
            return False

        failure_reason = lane.get("failure_reason")
        retry_count = int(lane.get("review_retry_count", 0))
        if failure_reason in {"review_timeout", "review_no_verdict"}:
            return retry_count < 2
        if failure_reason == "review_infra_unavailable":
            retry_after = lane.get("review_retry_after_at")
            if isinstance(retry_after, int | float) and time.time() < float(retry_after):
                return False
            return retry_count < 40
        return False

    async def reconcile_status_changes(self) -> None:
        with timed_core_operation(
            component="orchestrator",
            operation="reconcile_status_changes",
            logger=logger,
        ):
            stranded_gated_lanes = [
                lane for lane in list(self._sm.get_lanes(status="gated"))
                if not lane.get("review_started_at")
            ]
            for lane in list(self._sm.get_lanes(status="executed")):
                await self._on_lane_executed(str(lane["feature_id"]))
            for lane in stranded_gated_lanes:
                if self._sm.get_lane(str(lane["feature_id"])).get("status") == "gated":
                    await self._run_review_god(str(lane["feature_id"]))
            for lane in list(self._sm.get_lanes(status="reviewed")):
                await self.on_lane_reviewed(str(lane["feature_id"]))
            for lane in list(self._sm.get_lanes(status="rejected")):
                await self.on_lane_rejected(str(lane["feature_id"]))
            for lane in list(self._sm.get_lanes(status="gate_failed")):
                if self._should_retry_review(lane):
                    lane_id = str(lane["feature_id"])
                    failure_reason = str(lane.get("failure_reason", "review_failed"))
                    review_retries = int(lane.get("review_retry_count", 0)) + 1
                    self._sm.transition(
                        lane_id,
                        "gated",
                        metadata={
                            "review_retry_count": review_retries,
                            "review_recovered_from": failure_reason,
                        },
                    )
                    await self._run_review_god(lane_id)
            for lane in list(self._sm.get_lanes(status="merged")):
                await self._reproject_dependents_if_needed(str(lane["feature_id"]))
            for lane in list(self._sm.get_lanes(status="failed")):
                await self._reproject_dependents_if_needed(str(lane["feature_id"]))

    async def dispatch_lane(self, lane_id: str) -> None:
        try:
            lane = self._sm.get_lane(lane_id)
        except KeyError:
            lane = None
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="dispatch_lane",
            logger=logger,
            lane_id=lane_id,
        ):
            self._sm.transition(
                lane_id,
                "dispatched",
                metadata={
                    "dispatched_at": time.time(),
                    "god": self._execution_god.name,
                    "god_runtime": self._pick_execution_god(lane_id).runtime,
                },
            )
            log_event(logger, logging.INFO, "lane_dispatched", lane_id=lane_id)
            await self._run_execution_god(lane_id)

    def _pick_execution_god(self, lane_id: str) -> GodConfig:
        """Choose the execute-god runtime for this lane."""
        return self._god_picker.pick_execution(lane_id)

    def _pick_review_god(self, lane_id: str) -> GodConfig:
        """Choose the review-god runtime — match the execute-god so logs align."""
        return self._god_picker.pick_review(lane_id)

    async def _run_execution_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="run_execution_god",
            logger=logger,
            lane_id=lane_id,
        ):
            return await self._run_execution_god_inner(lane_id, lane)

    async def _run_execution_god_inner(self, lane_id: str, lane: dict[str, Any]) -> None:
        prompt = self._build_execution_prompt(lane)
        worktree = Path(lane.get("worktree", "."))
        god = self._pick_execution_god(lane_id)
        log_event(
            logger,
            logging.INFO,
            "execution_god_started",
            lane_id=lane_id,
            god=god.name,
            god_runtime=god.runtime,
        )
        try:
            result = await self._recovery.execute_async(
                "orchestrator.execution_god",
                "spawn",
                lambda: self._spawn_god_with_result_recovery(
                    god=god,
                    lane_id=lane_id,
                    prompt=prompt,
                    worktree=worktree,
                ),
                is_transient=lambda exc: self._is_spawn_transient(exc),
                observer=self._lane_recovery_observer(lane_id),
            )
        except CircuitOpenError as exc:
            self._sm.transition(
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
            self._sm.transition(
                lane_id,
                "exec_failed",
                metadata={
                    "failure_reason": "execution_infra_unavailable"
                    if self._is_spawn_transient(exc)
                    else "execution_spawn_failed",
                    "failure_error": str(exc),
                },
            )
            return

        if result.timed_out or self._spawn_result_transient(result):
            self._recovery.circuit("orchestrator.execution_god").record_failure()
            if self._recovery.circuit("orchestrator.execution_god").state.value == "open":
                self._lane_recovery_observer(lane_id)(
                    RecoveryEvent(
                        component="orchestrator.execution_god",
                        operation="spawn",
                        kind="circuit_opened",
                        attempt=1,
                        max_attempts=self._recovery.config.max_attempts,
                        error_type="SpawnResult",
                        error=result.stderr or result.stdout or "execution spawn failed",
                        circuit_state="open",
                    )
                )
            self._lane_recovery_observer(lane_id)(
                RecoveryEvent(
                    component="orchestrator.execution_god",
                    operation="spawn",
                    kind="operation_failed",
                    attempt=1,
                    max_attempts=self._recovery.config.max_attempts,
                    error_type="SpawnResult",
                    error=result.stderr or result.stdout or "execution spawn failed",
                    circuit_state=self._recovery.circuit(
                        "orchestrator.execution_god"
                    ).state.value,
                )
            )
        else:
            self._recovery.circuit("orchestrator.execution_god").record_success()

        if result.timed_out:
            self._sm.transition(lane_id, "exec_failed",
                                metadata={"failure_reason": "timeout"})
            return

        current = self._sm.get_lane(lane_id)
        if current["status"] == "dispatched":
            if result.exit_code == 0:
                log_event(logger, logging.INFO, "execution_god_completed", lane_id=lane_id)
                self._sm.transition(lane_id, "executed")
                await self._on_lane_executed(lane_id)
            else:
                self._sm.transition(lane_id, "exec_failed",
                                    metadata={"failure_reason": "non_zero_exit"})
        elif current["status"] == "executed" and result.exit_code == 0:
            await self._on_lane_executed(lane_id)

    async def _on_lane_executed(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="on_lane_executed",
            logger=logger,
            lane_id=lane_id,
        ):
            if lane.get("status") != "executed":
                return
            try:
                passed = await self._recovery.execute_async(
                    "orchestrator.gate_runner",
                    "run",
                    lambda: self._run_gate(lane_id),
                    fallback=lambda _exc: False,
                    critical=False,
                    observer=self._lane_recovery_observer(lane_id),
                )
            except Exception:
                passed = False
            if self._sm.get_lane(lane_id).get("status") != "executed":
                return
            if passed:
                self._sm.transition(lane_id, "gated", metadata={"gate_passed": True})
                await self._run_review_god(lane_id)
            else:
                self._sm.transition(
                    lane_id,
                    "gate_failed",
                    metadata={"gate_passed": False, "failure_reason": "gate_failed"},
                )

    async def _run_review_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="run_review_god",
            logger=logger,
            lane_id=lane_id,
        ):
            return await self._run_review_god_inner(lane_id, lane)

    async def _run_review_god_inner(self, lane_id: str, lane: dict[str, Any]) -> None:
        prompt = self._build_review_prompt(lane)
        worktree = Path(lane.get("worktree", "."))
        god = self._pick_review_god(lane_id)
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
            self._sm.transition(
                lane_id,
                "gated",
                metadata=metadata,
            )
        else:
            self._sm.update_metadata(lane_id, metadata)

        # Open a ReviewTask so the review plane has a persistent audit record.
        gate_report_ref = self._gate_report_ref_for_lane(lane_id)
        try:
            review_task = self._review_plane.open_review_task(
                lane_id, gate_report_ref=gate_report_ref
            )
            self._sm.update_metadata(lane_id, {"review_task_id": review_task.task_id})
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "review_plane_open_task_failed",
                lane_id=lane_id,
            )
            review_task = None

        try:
            result = await self._recovery.execute_async(
                "orchestrator.review_god",
                "spawn",
                lambda: self._spawn_god_with_result_recovery(
                    god=god,
                    lane_id=lane_id,
                    prompt=prompt,
                    worktree=worktree,
                ),
                is_transient=lambda exc: self._is_spawn_transient(exc),
                observer=self._lane_recovery_observer(lane_id),
            )
        except CircuitOpenError as exc:
            self._sm.transition(
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
            self._sm.transition(
                lane_id,
                "gate_failed",
                metadata={
                    "failure_reason": "review_infra_unavailable"
                    if self._is_spawn_transient(exc)
                    else "review_spawn_failed",
                    "review_infra_reason": self._review_infra_reason_from_exception(exc),
                    "review_retry_after_at": time.time() + REVIEW_INFRA_RETRY_DELAY_S,
                    "failure_error": str(exc),
                },
            )
            return

        if result.timed_out or self._spawn_result_transient(result):
            self._recovery.circuit("orchestrator.review_god").record_failure()
            if self._recovery.circuit("orchestrator.review_god").state.value == "open":
                self._lane_recovery_observer(lane_id)(
                    RecoveryEvent(
                        component="orchestrator.review_god",
                        operation="spawn",
                        kind="circuit_opened",
                        attempt=1,
                        max_attempts=self._recovery.config.max_attempts,
                        error_type="SpawnResult",
                        error=result.stderr or result.stdout or "review spawn failed",
                        circuit_state="open",
                    )
                )
            self._lane_recovery_observer(lane_id)(
                RecoveryEvent(
                    component="orchestrator.review_god",
                    operation="spawn",
                    kind="operation_failed",
                    attempt=1,
                    max_attempts=self._recovery.config.max_attempts,
                    error_type="SpawnResult",
                    error=result.stderr or result.stdout or "review spawn failed",
                    circuit_state=self._recovery.circuit("orchestrator.review_god").state.value,
                )
            )
        else:
            self._recovery.circuit("orchestrator.review_god").record_success()

        if result.timed_out:
            self._sm.transition(lane_id, "gate_failed",
                                metadata={"failure_reason": "review_timeout"})
            return

        if result.exit_code != 0:
            infra_reason = self._review_infra_failure_reason(result)
            if infra_reason is not None:
                self._sm.transition(
                    lane_id,
                    "gate_failed",
                    metadata={
                        "failure_reason": "review_infra_unavailable",
                        "review_infra_reason": infra_reason,
                        "review_retry_after_at": time.time() + REVIEW_INFRA_RETRY_DELAY_S,
                    },
                )
                return
            self._sm.transition(
                lane_id,
                "gate_failed",
                metadata={"failure_reason": "review_non_zero_exit"},
            )
            return

        current = self._sm.get_lane(lane_id)
        if current.get("status") == "gated" and not result.stdout.strip():
            self._sm.transition(
                lane_id,
                "gate_failed",
                metadata={"failure_reason": "review_no_verdict"},
            )
            return

        if current.get("status") == "gated" and result.stdout.strip():
            decision, summary, reason = self._infer_review_fallback(result.stdout)
            if decision == "reviewed":
                # Stamp a stable review_verdict_id on the lane before
                # transitioning so that on_lane_reviewed → _build_review_verdict
                # picks up the same ID that we persist in the review plane store.
                # Without this, the verdict gets a synthetic ID that cannot be
                # traced back to the stored verdict, breaking the merged-lane
                # verdict lineage acceptance signal.
                verdict_id = self._stable_verdict_id_for_lane(lane_id)
                self._sm.transition(
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
                # Ingest the merge verdict through the review plane so the
                # task→verdict lineage is preserved for the stdout-fallback
                # merge path (symmetric to the rework path below).
                self._ingest_merge_verdict_for_lane(lane_id, summary)
                await self.on_lane_reviewed(lane_id)
            else:
                self._sm.transition(
                    lane_id,
                    "rejected",
                    metadata={
                        "review_decision": ReviewDecision.REWORK.value,
                        "review_summary": summary,
                        "review_fallback": "stdout",
                        "review_fallback_reason": reason,
                    },
                )
                # Ingest the rework verdict through the review plane so the
                # task→verdict lineage is preserved even when the lane is
                # rejected via the stdout-fallback path (not through
                # on_lane_reviewed).
                self._ingest_rework_verdict_for_lane(lane_id, summary)
                await self.on_lane_rejected(lane_id)

    def _infer_review_fallback(self, stdout: str) -> tuple[str, str, str]:
        summary = stdout.strip()[-4000:] or "review completed without MCP status update"
        normalized = stdout.lower()
        approval_markers = (
            "approved",
            "approve",
        )
        negative_markers = (
            "high:",
            "medium:",
            "must fix",
            "still reproduces",
            "does not fix",
            "does not resolve",
        )
        rework_reason = self._review_fallback_rework_reason(stdout)
        if rework_reason:
            return "rejected", summary, rework_reason
        positive_reason = self._review_fallback_positive_reason(stdout)
        if positive_reason:
            return "reviewed", summary, positive_reason
        if any(marker in normalized for marker in approval_markers):
            return "reviewed", summary, "approval_marker"
        if any(marker in normalized for marker in negative_markers):
            return "rejected", summary, "negative_marker"
        # Fail-safe: unknown review text cannot be trusted as an approval.
        # Defaulting to merge on unrecognised output is a High-severity risk —
        # the review god may have produced a finding we cannot parse.
        return "rejected", summary, "unknown_review_text"

    def _review_infra_failure_reason(self, result: Any) -> str | None:
        output = f"{getattr(result, 'stderr', '')}\n{getattr(result, 'stdout', '')}".lower()
        infra_markers = {
            "usage_limit": (
                "usage limit",
                "try again later",
            ),
            "rate_limit": (
                "429 too many requests",
                "too many requests",
                "rate limit",
                "exceeded retry limit",
            ),
            "temporary_unavailable": (
                "temporarily unavailable",
                "service unavailable",
                "internal server error",
            ),
        }
        for reason, markers in infra_markers.items():
            if any(marker in output for marker in markers):
                return reason
        return None

    async def _spawn_god_with_result_recovery(
        self,
        *,
        god: GodConfig,
        lane_id: str,
        prompt: str,
        worktree: Path,
    ) -> Any:
        result = await self._spawner.spawn(
            god_config=god,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )
        infra_reason = self._review_infra_failure_reason(result)
        if infra_reason is not None:
            output = getattr(result, "stderr", "") or getattr(result, "stdout", "")
            raise TransientRecoveryError(
                f"{infra_reason}: {output or 'spawn infrastructure failure'}"
            )
        return result

    def _review_infra_reason_from_exception(self, exc: BaseException) -> str:
        if isinstance(exc, TransientRecoveryError):
            reason = str(exc).split(":", 1)[0]
            if reason in {"usage_limit", "rate_limit", "temporary_unavailable"}:
                return reason
        return type(exc).__name__

    def _spawn_result_transient(self, result: Any) -> bool:
        if getattr(result, "timed_out", False):
            return True
        return self._review_infra_failure_reason(result) is not None

    def _is_spawn_transient(self, exc: BaseException) -> bool:
        return isinstance(exc, (TimeoutError, ConnectionError, OSError, TransientRecoveryError))

    def _review_fallback_rework_reason(self, stdout: str) -> str | None:
        normalized = stdout.lower()
        reproduced_patterns = (
            r"\bstill\s+reproduc(?:e|es|ed|ible|ing)\b",
            r"\breproduc(?:ed|es|ing)\s+(?:finding|bug|issue|failure)\b",
            r"\b(?:finding|bug|issue|failure)\s+still\s+reproduc",
        )
        if any(re.search(pattern, normalized) for pattern in reproduced_patterns):
            return "reproduced_finding"
        if re.search(
            r"\b(?:not|cannot|can't|do\s+not|does\s+not|unable\s+to)\s+approve(?:d)?\b",
            normalized,
        ):
            return "explicit_rejection"
        if re.search(
            r"\b(?:do\s+not|don't|cannot|can't|must\s+not)\s+merge\b",
            normalized,
        ):
            return "explicit_rejection"
        if re.search(r"\b(?:would\s+not|should\s+not)\s+merge\b", normalized):
            return "explicit_rejection"
        if re.search(r"\bnot\s+ready\s+to\s+merge\b", normalized):
            return "explicit_rejection"
        if re.search(r"\bnot\s+acceptable\s+for\s+merge\b", normalized):
            return "explicit_rejection"
        if re.search(r"\bneeds?\s+rework\b", normalized):
            return "needs_rework"
        if re.search(r"\btests?\s+(?:are\s+)?absent\b", normalized):
            return "missing_tests"
        if re.search(r"\bvalidation\s+is\s+incomplete\b", normalized):
            return "incomplete_validation"
        if re.search(r"(?m)^\s*(?:[-*]\s+)?reject(?:ed|ion)?\b\s*:?", normalized):
            return "explicit_rejection"
        if re.search(r"\bdoes\s+not\s+(?:fix|resolve|address)\b", normalized):
            return "unresolved_finding"
        if re.search(
            r"\b(?:missing\s+)?(?:coverage|test|tests|failure|bug|issue|finding|regression)"
            r"\s+remains?\b",
            normalized,
        ):
            return "unresolved_finding"
        if re.search(r"\bmissing\s+(?:coverage|test|tests)\b", normalized):
            return "missing_coverage"
        if re.search(r"\bmust\s+fix\b", normalized):
            return "must_fix"
        negated_blocking_pattern = re.compile(
            r"\b(?:did\s+not|do\s+not|does\s+not|no|not)\s+"
            r"(?:find|see|identify|detect|have|found)?\s*"
            r"(?:a\s+)?blocking\s+(?:finding|issue|bug|failure|regression)\b"
        )
        in_findings_section = False
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            stripped = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", line).strip()
            stripped = re.sub(r"^#{1,6}\s+", "", stripped).strip()
            stripped = stripped.replace("**", "").replace("__", "")
            lowered = stripped.lower()
            section_name = lowered.rstrip(":")
            if section_name in {"findings", "finding"}:
                in_findings_section = True
                continue
            if self._review_fallback_section_heading(section_name):
                in_findings_section = False
                continue
            if self._review_fallback_positive_text(lowered):
                continue
            if re.match(r"(?i)^(critical|high|medium|low)\b[: -]", stripped):
                return "severity_finding"
            if re.search(r"(?i)\bblocking\s+(?:finding|issue|bug|failure|regression)\b", stripped):
                if negated_blocking_pattern.search(lowered):
                    continue
                return "blocking_finding"
            if in_findings_section:
                return "findings_section"
        return None

    def _review_fallback_section_heading(self, value: str) -> bool:
        return value in {
            "assumptions",
            "change summary",
            "open questions",
            "questions",
            "summary",
            "verification",
            "verification run",
        }

    def _review_fallback_positive_line(self, value: str) -> bool:
        return bool(
            re.fullmatch(
                r"(?:none|no findings|no blocking findings|no issues)"
                r"(?:\s+(?:found|detected|identified))?\s*[.!:]?",
                value,
            )
        )

    def _review_fallback_positive_text(self, value: str) -> bool:
        if self._review_fallback_positive_line(value):
            return True
        positive_patterns = (
            r"^none[.!:]\s+i\s+did\s+not\s+find\s+"
            r"(?:(?:any\s+)?(?:findings|issues|bugs|failures)|a\s+blocking\s+issue)"
            r"(?:\s+in\s+the\s+current\s+lane\s+state)?[.!:]?",
            r"^none[.!:]\s+i\s+found\s+no\s+(?:findings|issues|bugs|failures)[.!:]?",
            r"^no\s+(?:findings|issues|bugs|failures)\s+(?:were\s+)?"
            r"(?:found|detected|identified)[.!:]?",
        )
        return any(re.fullmatch(pattern, value) for pattern in positive_patterns)

    def _review_fallback_positive_reason(self, stdout: str) -> str | None:
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            stripped = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", line).strip()
            stripped = re.sub(r"^#{1,6}\s+", "", stripped).strip()
            stripped = stripped.replace("**", "").replace("__", "")
            lowered = stripped.lower()
            if self._review_fallback_positive_line(lowered):
                token = lowered.split()[0].rstrip(".!:")
                if token == "no":
                    return "positive_" + "_".join(lowered.rstrip(".!:").split()[:2])
                return f"positive_{token}"
            if not self._review_fallback_positive_text(lowered):
                continue
            token = lowered.split()[0].rstrip(".!:")
            if token == "no":
                return "positive_" + "_".join(lowered.rstrip(".!:").split()[:2])
            return f"positive_{token}"
        return None

    async def on_lane_reviewed(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="on_lane_reviewed",
            logger=logger,
            lane_id=lane_id,
        ):
            return await self._on_lane_reviewed_inner(lane_id, lane)

    async def _on_lane_reviewed_inner(self, lane_id: str, lane: dict[str, Any]) -> None:
        verdict = self._build_review_verdict(lane)

        # Persist the verdict through the review plane for auditable lineage.
        task_id = lane.get("review_task_id")
        if task_id:
            try:
                self._review_plane.ingest_verdict(task_id, verdict)
            except Exception:
                log_event(
                    logger,
                    logging.WARNING,
                    "review_plane_verdict_ingest_failed",
                    lane_id=lane_id,
                    task_id=task_id,
                )

        adapted = adapt_review_verdict(
            verdict,
            lane=lane,
            require_final_action_approval=self._require_final_action_approval,
        )

        if adapted.patch_lane is not None:
            self._append_lane(adapted.patch_lane)
            self._sm.transition(
                lane_id,
                "failed",
                metadata=adapted.metadata | {
                    "failure_reason": "patch_forward_requested",
                    "patch_lane_id": adapted.patch_lane["feature_id"],
                },
            )
            log_event(
                logger,
                logging.INFO,
                "patch_forward_lane_created",
                lane_id=lane_id,
                patch_lane_id=adapted.patch_lane["feature_id"],
            )
            return

        if adapted.final_action is not None:
            hold = self._final_action_store.create_hold(
                lane_id=adapted.final_action.lane_id,
                verdict_id=adapted.final_action.verdict_id,
                action=adapted.final_action.action,
                target_status=adapted.final_action.target_status,
                summary=adapted.final_action.summary,
            )
            self._sm.transition(
                lane_id,
                "awaiting_final_action",
                metadata=adapted.metadata | {"final_action_hold_id": hold.id},
            )
            log_event(
                logger,
                logging.INFO,
                "lane_awaiting_final_action",
                lane_id=lane_id,
                action=hold.action,
            )
            return

        if adapted.transition_status == "rejected":
            self._sm.transition(lane_id, "rejected", metadata=adapted.metadata)
            await self.on_lane_rejected(lane_id)
            return

        if adapted.transition_status == "failed":
            self._sm.transition(lane_id, "failed", metadata=adapted.metadata)
            log_event(logger, logging.INFO, "lane_terminated_by_review", lane_id=lane_id)
            return

        worktree = Path(lane.get("worktree", "."))
        merged = await self._auto_merge(lane_id, worktree)
        if merged:
            self._sm.transition(lane_id, "merged")
            await self._reproject_dependents_if_needed(lane_id)
            log_event(logger, logging.INFO, "lane_merged", lane_id=lane_id)
        else:
            self._sm.transition(lane_id, "failed",
                                metadata={"failure_reason": "merge_failed"})
            await self._reproject_dependents_if_needed(lane_id)
            log_event(logger, logging.WARNING, "lane_merge_failed", lane_id=lane_id)

    async def _auto_merge(self, lane_id: str, worktree: Path) -> bool:
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="orchestrator",
            operation="auto_merge",
            logger=logger,
            lane_id=lane_id,
        ):
            return await self._auto_merge_inner(lane_id, worktree)

    async def _auto_merge_inner(self, lane_id: str, worktree: Path) -> bool:
        try:
            lane = self._sm.get_lane(lane_id)
            if not lane.get("branch"):
                log_event(
                    logger,
                    logging.INFO,
                    "lane_no_branch_treated_as_applied",
                    lane_id=lane_id,
                )
                return True

            diff_check = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=10,
            )
            insertions = 0
            for line in diff_check.stdout.splitlines():
                if "insertion" in line or "deletion" in line:
                    parts = line.split(",")
                    for part in parts:
                        if "insertion" in part:
                            insertions += int(part.strip().split()[0])
            if insertions > 1000:
                log_event(
                    logger,
                    logging.WARNING,
                    "lane_diff_too_large",
                    lane_id=lane_id,
                    insertions=insertions,
                )
                return False

            result = subprocess.run(
                ["git", "checkout", "main"],
                cwd=worktree, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                log_event(
                    logger,
                    logging.WARNING,
                    "checkout_main_failed",
                    lane_id=lane_id,
                    stderr=result.stderr,
                )
                return False

            merge_branch = lane_id

            result = subprocess.run(
                ["git", "merge", "--no-ff", merge_branch, "-m",
                 f"feat(xmuse): merge lane {lane_id}"],
                cwd=worktree, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                log_event(
                    logger,
                    logging.WARNING,
                    "git_merge_failed",
                    lane_id=lane_id,
                    stderr=result.stderr,
                )
                subprocess.run(["git", "merge", "--abort"],
                               cwd=worktree, capture_output=True, timeout=5)
                return False
            return True
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "auto_merge_error",
                lane_id=lane_id,
                error=str(exc),
                exc_info=True,
            )
            return False

    async def on_lane_rejected(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="on_lane_rejected",
            logger=logger,
            lane_id=lane_id,
        ):
            retries = lane.get("retry_count", 0)
            if retries >= 2:
                self._sm.transition(lane_id, "failed")
                log_event(logger, logging.INFO, "lane_failed_after_max_retries", lane_id=lane_id)
                return
            self._sm.transition(lane_id, "reworking")
            await self.dispatch_lane(lane_id)

    async def _reproject_dependents_if_needed(self, lane_id: str) -> None:
        await reproject_dependents_if_needed(
            lane_id,
            sm=self._sm,
            graph_store=self._graph_store,
        )

    async def _run_gate(self, lane_id: str) -> bool:
        lane = self._sm.get_lane(lane_id)
        with observability_context(
            lane_id=lane_id,
            graph_id=_lane_graph_id(lane),
        ), timed_core_operation(
            component="orchestrator",
            operation="run_gate",
            logger=logger,
            lane_id=lane_id,
        ):
            return await self._run_gate_inner(lane_id, lane)

    async def _run_gate_inner(self, lane_id: str, lane: dict[str, Any]) -> bool:
        return await execution_gate.run_gate(lane_id=lane_id, lane=lane, root=self._root)

    def _get_changed_paths(self, worktree: Path) -> list[str]:
        return execution_gate.get_changed_paths(worktree)

    def _build_execution_prompt(self, lane: dict[str, Any]) -> str:
        return build_execution_prompt(
            lane,
            xmuse_root=self._root,
            skill_prompt_path=self._execution_god.skill_prompt_path,
        )

    def _build_review_prompt(self, lane: dict[str, Any]) -> str:
        return build_review_prompt(
            lane,
            xmuse_root=self._root,
            skill_prompt_path=self._review_god.skill_prompt_path,
        )

    def _build_review_verdict(self, lane: dict[str, Any]) -> ReviewVerdict:
        return build_review_verdict(lane)

    def _append_lane(self, lane: dict[str, Any]) -> None:
        self._sm.append_lane(lane)

    def _stable_verdict_id_for_lane(self, lane_id: str) -> str:
        """Return a stable verdict ID for *lane_id* based on the current review task."""
        lane = self._sm.get_lane(lane_id)
        return stable_verdict_id_for_lane(lane_id, lane=lane)

    def _ingest_merge_verdict_for_lane(self, lane_id: str, summary: str) -> None:
        """Ingest a merge verdict through the review plane for the stdout-fallback path."""
        lane = self._sm.get_lane(lane_id)
        ingest_merge_verdict(
            lane_id, summary, lane=lane, review_plane=self._review_plane,
        )

    def _ingest_rework_verdict_for_lane(self, lane_id: str, summary: str) -> None:
        """Ingest a rework verdict through the review plane for the stdout-fallback path."""
        lane = self._sm.get_lane(lane_id)
        ingest_rework_verdict(
            lane_id, summary, lane=lane, review_plane=self._review_plane,
        )

    def verdict_lineage_for_lane(self, lane_id: str) -> list[dict[str, Any]]:
        """Return the full task→verdict lineage for *lane_id* from the review plane."""
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="orchestrator",
            operation="verdict_lineage_for_lane",
            logger=logger,
            lane_id=lane_id,
        ):
            return self._review_plane.verdict_lineage_for_lane(lane_id)

    def verdict_lineage_for_run(self, graph_id: str) -> list[dict[str, Any]]:
        """Return the full task→verdict lineage for every lane in *graph_id*.

        Delegates to :meth:`ReviewPlaneController.verdict_lineage_for_run` so
        callers can audit the complete review history for a run without
        accessing the review plane directly.
        """
        with observability_context(graph_id=graph_id), timed_core_operation(
            component="orchestrator",
            operation="verdict_lineage_for_run",
            logger=logger,
            graph_id=graph_id,
        ):
            return self._review_plane.verdict_lineage_for_run(graph_id)

    def aggregate_run_terminal_status(self, graph_id: str) -> RunTerminalAggregation:
        """Compute the run-level terminal status for *graph_id*.

        Delegates to :meth:`ReviewPlaneController.aggregate_run_terminal_status`
        with the orchestrator's final-action store so that pending holds are
        included in the aggregation.

        Returns a :class:`RunTerminalAggregation` with the computed status
        (``merged | terminated | blocked_for_input | in_progress``) and the
        full set of inputs used to reach that decision.
        """
        with observability_context(graph_id=graph_id), timed_core_operation(
            component="orchestrator",
            operation="aggregate_run_terminal_status",
            logger=logger,
            graph_id=graph_id,
        ):
            return self._review_plane.aggregate_run_terminal_status(
                graph_id,
                final_action_store=self._final_action_store,
            )

    def assemble_evidence_bundle(
        self,
        graph_id: str,
        *,
        evidence_store: EvidenceBundleStore | None = None,
        selection_policy_id: str = "default-v1",
        selection_policy_version: str = "1",
    ) -> StructuredEvidenceBundle:
        """Assemble a StructuredEvidenceBundle from a terminal run.

        Delegates to :meth:`ReviewPlaneController.assemble_evidence_bundle`
        with the orchestrator's final-action store so that pending holds are
        included in the aggregation.

        The bundle is persisted in *evidence_store* when provided.

        Returns a :class:`StructuredEvidenceBundle` containing the curated
        summary view and full primary references for every cited item.
        """
        with observability_context(graph_id=graph_id), timed_core_operation(
            component="orchestrator",
            operation="assemble_evidence_bundle",
            logger=logger,
            graph_id=graph_id,
        ):
            return self._review_plane.assemble_evidence_bundle(
                graph_id,
                final_action_store=self._final_action_store,
                evidence_store=evidence_store,
                selection_policy_id=selection_policy_id,
                selection_policy_version=selection_policy_version,
            )

    def has_verdict_lineage(self, lane_id: str) -> bool:
        """Return True if *lane_id* has at least one finalized verdict in the review plane."""
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="orchestrator",
            operation="has_verdict_lineage",
            logger=logger,
            lane_id=lane_id,
        ):
            return self._review_plane.has_verdict_lineage(lane_id)

    def _gate_report_ref_for_lane(self, lane_id: str) -> str | None:
        """Return the relative gate report path for *lane_id* if it exists."""
        return gate_report_ref_for_lane(lane_id, xmuse_root=self._root)
