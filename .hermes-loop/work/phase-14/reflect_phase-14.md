# phase: phase-14

# Phase 14 Reflection

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent
memory system for LongMemEval and LoCoMo, without demo-only phase completion,
without hiding case-level regressions, and without enabling the v3 kernel by
default.

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

## Reflection Decision

Phase 14 should advance.

The phase delivered a real but deliberately narrow opt-in kernel improvement:
the existing `archive_write` bridge now behaves like an audited memory action
instead of a trace-only demo step. It still does not make a LongMemEval or
LoCoMo quality claim, and it does not justify enabling the v3 kernel by default.

## What Changed

Runtime changes were limited to the opt-in kernel path:

- approved `archive_write` now emits `tool_executed` followed by durable
  `tool_verified`;
- `tool_verified` has positive and negative semantics;
- verification checks real archival memory history, passage existence,
  same-session archive attachment, and same-session v3 archival eligibility;
- failed verification is durable and prevents a successful tool-result message;
- approval replay now binds to the original request fingerprint;
- unsupported memory tools such as `core_memory_append` and
  `core_memory_replace` deny closed without execution or verification;
- public benchmark opt-in kernel trace expectations now include
  `tool_verified`;
- default public benchmark kernel traces remain empty because the kernel remains
  off unless `MEMORYOS_AGENT_KERNEL=v1` is explicitly enabled.

The relevant implementation diff is in:

- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/v3_contracts.py`;
- `tests/test_agent_kernel.py`;
- `tests/test_public_benchmarks.py`.

The broader current git diff also contains Hermes/controller hardening and
blueprint changes. Those are not additional Phase 14 runtime benchmark claims.

## Evidence

Phase artifacts agree on the same result:

- `result.md` reports Phase 14 as structural kernel-loop evidence only;
- `execute_review.md` gives `PASS`;
- `reviews/codex-review-phase-14.md` gives `PASS` with no blocking findings;
- `review_verdict.json` gives `verdict=PASS`, `decision=advance`, and
  `review_eval_decision.scope=smoke`;
- `ack.json` gives `ack_level=usable` and `decision=advance`.

RED coverage was recorded before the fix for:

- missing `tool_verified` after successful approved `archive_write`;
- replay without original request-binding verification;
- execution-only archive writes without durable negative verification;
- opt-in public benchmark kernel trace missing `tool_verified`.

Verification evidence recorded in the phase artifacts:

- `uv run pytest tests/test_agent_kernel.py -q` -> `11 passed`;
- focused public kernel trace tests -> `2 passed`;
- full suite -> `470 passed, 1 warning`;
- `uv run ruff check .` -> `All checks passed!`;
- review reruns with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider` also
  passed for kernel, public trace, default settings, v1 fallback, and focused
  ruff checks.

Benchmark case-level movement:

- LongMemEval: not applicable; no default retrieval, answer, judge, or scoring
  path changed;
- LoCoMo: not applicable for the same reason;
- pass-to-fail: none claimed;
- fail-to-pass: none claimed;
- source-grounding movement: none claimed.

This satisfies the phase goal because the changed chain is real and tested, but
it avoids hiding benchmark regressions by making no benchmark-quality claim.

## Blueprint Adjustment Decision

No new blueprint amendment is needed after Phase 14.

The already-present Phase 14 blueprint amendments should stand:

- the eval/gold-field boundary belongs in the root blueprint;
- the Letta-style approval, execution, verification, replay, and tool-return
  contract belongs in the root blueprint;
- the K0-K5 kernel graduation roadmap belongs in the root blueprint;
- Phase 15 should remain adjusted to do K2 hybrid tool selection before any
  executable diagnostic maintenance planner work.

Phase 14 evidence supports the K0/K1 slice of that roadmap. It does not support
further broadening Phase 15-17, enabling the kernel by default, or claiming
benchmark promotion readiness.

If the controller treats the current root blueprint diff as not yet formally
promoted, promote the existing Phase 14 kernel/eval-boundary amendments during
the reviewed ACK transition. Do not create a new amendment from this reflection.

## New Risks

- Verification proves store/history/attachment/same-session eligibility for one
  `archive_write` path, but it is still not evidence that arbitrary later
  benchmark questions will rank or select the new memory correctly.
- The kernel still writes directly through the narrow `archive_write` bridge.
  Later phases should route broader memory tools through named domain services
  before counting them as graduated Letta-style tools.
- `tool_executed` can exist with `tool_verified(ok=False)`. Future diagnostics
  must not count execution alone as a successful memory mutation.
- The public opt-in benchmark kernel smoke writes a structural trace after
  context construction. It must remain smoke evidence only, not benchmark
  improvement evidence.
- The worktree contains broad Hermes/controller and blueprint diffs alongside
  the kernel changes. Future phase handoffs should be explicit about which
  changes are phase runtime work and which are loop governance hardening.

## Next Phase Recommendation

Advance to Phase 15 with the K2-first scope from the active blueprint:

1. implement deterministic candidate routing for kernel tool selection;
2. constrain any LLM selector to the declared candidate set or no-op;
3. fail closed on invalid output, unavailable LLM, missing provenance, timeout,
   or policy denial;
4. trace `selection_origin` and `candidate_reason`;
5. prove selector inputs exclude expected answers, expected source ids, judge
   labels, gold-derived failure classes, and case-specific repair ids;
6. only after K2 is tested, allow diagnostic planner proposals, with executable
   payloads separated from eval-only sidecars and `gold_fields_used=false`.

Do not run milestone LongMemEval/LoCoMo gates for Phase 14 retroactively. Use
Phase 15 focused tests and structural smokes first; reserve full-chain
milestone evals for phases that change default public benchmark behavior or
make a promotion claim.
