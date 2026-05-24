from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from memoryos_lite.agent_tool_registry import (
    KernelToolSpec,
    executable_kernel_tool_names,
    get_kernel_tool_spec,
)
from memoryos_lite.schemas import new_id
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ToolCandidate,
    ToolExecutionRequest,
    ToolSelectionChoice,
    ToolSelectionOrigin,
)

ALLOWED_K2_TOOLS = executable_kernel_tool_names()


class ToolSelector(Protocol):
    def select(
        self,
        request: AgentStepRequest,
        candidates: list[ToolCandidate],
    ) -> ToolSelectionChoice | dict[str, Any] | None: ...


@dataclass(frozen=True)
class ToolSelectionResolution:
    candidates: list[ToolCandidate]
    rejected_inputs: list[dict[str, Any]]
    selected_request: ToolExecutionRequest | None
    selected_choice: ToolSelectionChoice | None
    selection_payload: dict[str, Any]
    denial_reason: str | None = None

    @property
    def denied(self) -> bool:
        return self.denial_reason is not None


ToolSelectionResult = ToolSelectionResolution


class ToolSelectionBoundary:
    def __init__(self, selector: ToolSelector | None = None):
        self.selector = selector

    def resolve(
        self,
        request: AgentStepRequest,
        tool_requests: list[ToolExecutionRequest],
    ) -> ToolSelectionResolution:
        candidates, rejected_inputs = self.generate_candidates(tool_requests)
        duplicate_id = self._first_duplicate_candidate_id(candidates)
        if duplicate_id is not None:
            reason = f"duplicate candidate tool_call_id: {duplicate_id}"
            return ToolSelectionResolution(
                candidates=candidates,
                rejected_inputs=rejected_inputs,
                selected_request=None,
                selected_choice=None,
                selection_payload={
                    "tool_call_id": duplicate_id,
                    "selection_origin": "fallback",
                    "reason": reason,
                    "rejected_inputs": rejected_inputs,
                },
                denial_reason=reason,
            )
        if not candidates:
            reason = (
                str(rejected_inputs[0]["reason"])
                if rejected_inputs
                else "no executable candidates"
            )
            choice = ToolSelectionChoice(
                tool_call_id=None,
                selection_origin="fallback" if rejected_inputs else "deterministic",
                reason=reason,
            )
            return ToolSelectionResolution(
                candidates=candidates,
                rejected_inputs=rejected_inputs,
                selected_request=None,
                selected_choice=choice,
                selection_payload=self._selection_payload(
                    choice,
                    reason=reason,
                    rejected_inputs=rejected_inputs,
                ),
                denial_reason=reason if rejected_inputs else None,
            )

        if self.selector is None:
            choice = ToolSelectionChoice(
                tool_call_id=candidates[0].tool_call_id,
                selection_origin="deterministic",
                reason=candidates[0].candidate_reason,
            )
        else:
            try:
                choice = self._coerce_choice(self.selector.select(request, candidates))
            except TimeoutError as exc:
                return self._fallback_denial(
                    candidates,
                    rejected_inputs,
                    f"selector timeout: {exc}",
                )
            except (TypeError, ValueError, ValidationError) as exc:
                return self._fallback_denial(
                    candidates,
                    rejected_inputs,
                    f"malformed selector output: {exc}",
                )
            except Exception as exc:
                return self._fallback_denial(
                    candidates,
                    rejected_inputs,
                    f"selector unavailable: {exc}",
                )

        if choice.tool_call_id is None:
            reason = choice.reason
            return ToolSelectionResolution(
                candidates=candidates,
                rejected_inputs=rejected_inputs,
                selected_request=None,
                selected_choice=choice,
                selection_payload=self._selection_payload(
                    choice,
                    reason=reason,
                    rejected_inputs=rejected_inputs,
                ),
                denial_reason=reason,
            )
        selected = next(
            (
                candidate
                for candidate in candidates
                if candidate.tool_call_id == choice.tool_call_id
            ),
            None,
        )
        if selected is None:
            reason = f"selected tool_call_id is not a candidate: {choice.tool_call_id}"
            return ToolSelectionResolution(
                candidates=candidates,
                rejected_inputs=rejected_inputs,
                selected_request=None,
                selected_choice=choice,
                selection_payload=self._selection_payload(
                    choice,
                    reason=reason,
                    rejected_inputs=rejected_inputs,
                ),
                denial_reason=reason,
            )

        selected_request = self._request_for_candidate(
            selected,
            selection_origin=choice.selection_origin,
        )
        return ToolSelectionResolution(
            candidates=candidates,
            rejected_inputs=rejected_inputs,
            selected_request=selected_request,
            selected_choice=choice,
            selection_payload={
                "tool_call_id": selected.tool_call_id,
                "tool_name": selected.tool_name,
                "selection_origin": choice.selection_origin,
                "candidate_reason": selected.candidate_reason,
                "reason": choice.reason,
                "constraints": dict(selected.constraints),
                "rejected_inputs": rejected_inputs,
            },
        )

    def select(
        self,
        request: AgentStepRequest,
        tool_requests: list[ToolExecutionRequest],
    ) -> ToolSelectionResolution:
        return self.resolve(request, tool_requests)

    def generate_candidates(
        self,
        tool_requests: list[ToolExecutionRequest],
    ) -> tuple[list[ToolCandidate], list[dict[str, Any]]]:
        candidates: list[ToolCandidate] = []
        rejected_inputs: list[dict[str, Any]] = []
        for request in tool_requests:
            spec = get_kernel_tool_spec(request.tool_name)
            if spec is None:
                rejected_inputs.append(
                    {
                        "tool_name": request.tool_name,
                        "reason": "unsupported tool for K2 selection",
                    }
                )
                continue
            try:
                candidate = self._candidate_for_request(request, spec)
            except ValueError as exc:
                rejected_inputs.append(
                    {
                        "tool_name": request.tool_name,
                        "reason": str(exc),
                    }
                )
                continue
            candidates.append(candidate)
        return candidates, rejected_inputs

    @staticmethod
    def _candidate_for_request(
        request: ToolExecutionRequest,
        spec: KernelToolSpec,
    ) -> ToolCandidate:
        arguments = dict(request.arguments)
        if request.tool_name == "archive_write":
            content = str(arguments.get("content") or "").strip()
            if not content:
                raise ValueError("archive_write candidate requires non-empty content")
            arguments["content"] = content
            constraints = {
                "allowed_tool": "archive_write",
                "requires_source_refs_or_approval": spec.requires_source_refs_or_approval,
                "requires_non_empty_content": True,
                "requires_policy_check": spec.requires_policy_check,
            }
        elif request.tool_name == "archive_attach":
            archive_id = str(arguments.get("archive_id") or "").strip()
            if not archive_id:
                raise ValueError("archive_attach candidate requires archive_id")
            scope_type = str(arguments.get("scope_type") or "session")
            scope_id = str(arguments.get("scope_id") or request.session_id)
            if scope_type != "session" or scope_id != request.session_id:
                raise ValueError("archive_attach candidate requires current session scope")
            arguments.update(
                {
                    "archive_id": archive_id,
                    "scope_type": "session",
                    "scope_id": request.session_id,
                }
            )
            constraints = {
                "allowed_tool": "archive_attach",
                "requires_source_refs_or_approval": spec.requires_source_refs_or_approval,
                "requires_existing_archive": True,
                "requires_session_scope": True,
                "requires_policy_check": spec.requires_policy_check,
            }
        elif request.tool_name == "core_promotion_request":
            content = str(arguments.get("content") or "").strip()
            if not content:
                raise ValueError(
                    "core_promotion_request candidate requires non-empty content"
                )
            arguments["content"] = content
            arguments.setdefault("target_layer", "core")
            arguments.setdefault("operation", "promote")
            arguments.setdefault("write_source", "explicit_instruction")
            constraints = {
                "allowed_tool": "core_promotion_request",
                "requires_source_refs_or_approval": spec.requires_source_refs_or_approval,
                "applies_core_memory": False,
                "requires_policy_check": spec.requires_policy_check,
            }
        else:
            raise ValueError(
                f"unsupported tool for kernel maintenance selection: {request.tool_name}"
            )
        return ToolCandidate(
            tool_call_id=request.tool_call_id or new_id("toolcall"),
            session_id=request.session_id,
            tool_name=request.tool_name,
            arguments=arguments,
            source_refs=list(request.source_refs),
            approval_id=request.approval_id,
            candidate_reason=(
                f"{request.tool_name} candidate requiring policy and provenance"
            ),
            constraints=constraints,
        )

    @staticmethod
    def _coerce_choice(output: ToolSelectionChoice | dict[str, Any] | None) -> ToolSelectionChoice:
        if output is None:
            return ToolSelectionChoice(
                tool_call_id=None,
                selection_origin="fallback",
                reason="selector returned no choice",
            )
        if isinstance(output, ToolSelectionChoice):
            return output
        if isinstance(output, dict):
            if "reason" not in output:
                raise ValueError("selector choice missing provenance reason")
            return ToolSelectionChoice.model_validate(output)
        raise TypeError("selector output must be a ToolSelectionChoice, mapping, or None")

    @staticmethod
    def _request_for_candidate(
        candidate: ToolCandidate,
        *,
        selection_origin: ToolSelectionOrigin,
    ) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            session_id=candidate.session_id,
            tool_name=candidate.tool_name,
            arguments=dict(candidate.arguments),
            source_refs=list(candidate.source_refs),
            approval_id=candidate.approval_id,
            tool_call_id=candidate.tool_call_id,
            selection_origin=selection_origin,
            candidate_reason=candidate.candidate_reason,
        )

    @staticmethod
    def _fallback_denial(
        candidates: list[ToolCandidate],
        rejected_inputs: list[dict[str, Any]],
        reason: str,
    ) -> ToolSelectionResolution:
        choice = ToolSelectionChoice(
            tool_call_id=None,
            selection_origin="fallback",
            reason=reason,
        )
        return ToolSelectionResolution(
            candidates=candidates,
            rejected_inputs=rejected_inputs,
            selected_request=None,
            selected_choice=choice,
            selection_payload=ToolSelectionBoundary._selection_payload(
                choice,
                reason=reason,
                rejected_inputs=rejected_inputs,
            ),
            denial_reason=reason,
        )

    @staticmethod
    def _selection_payload(
        choice: ToolSelectionChoice,
        *,
        reason: str,
        rejected_inputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "tool_call_id": choice.tool_call_id,
            "selection_origin": choice.selection_origin,
            "reason": reason,
            "rejected_inputs": rejected_inputs,
        }

    @staticmethod
    def _first_duplicate_candidate_id(candidates: list[ToolCandidate]) -> str | None:
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.tool_call_id in seen:
                return candidate.tool_call_id
            seen.add(candidate.tool_call_id)
        return None


__all__ = [
    "ALLOWED_K2_TOOLS",
    "ToolSelectionBoundary",
    "ToolSelectionResolution",
    "ToolSelectionResult",
    "ToolSelector",
]
