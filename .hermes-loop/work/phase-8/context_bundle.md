# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 8 is the promotion gate and next-blueprint decision for the active
Letta-style benchmark-usability loop. It must decide whether the current
MemoryOS Lite v3 chain is ready to expand eval, should continue targeted work,
must hold because source grounding regressed, or needs a promoted blueprint
adjustment.

Target chain component: public benchmark decision layer over the already wired
v3 chain. The phase may write phase artifacts and active docs only if evidence
requires a documented decision or amendment. It should not implement a new
memory architecture slice unless review finds that Phase 8 cannot make a valid
decision without a small, test-first diagnostic fix.

## Why This Phase Exists Now

`state.json` currently has:

- `current_state = "EXECUTE"`.
- `current_phase_idx = 8`.
- `execute_lane.phase = "phase-8"`.
- `execute_lane.state = "EXECUTE"`.
- `plan_lane.phase = null`.
- `research_lane.phases = []`.
- `review_lane.active = false`.

Phases 0 through 7 have usable ACK history. Phase 7 intentionally proved only
opt-in kernel trace/control-plane usability. It did not claim answer-quality
improvement. Phase 8 must run larger full-chain evidence and decide the next
controller action.

## Current Hypothesis

Hypothesis:

MemoryOS Lite v3 may be ready for `expand_eval` only if a 50-case LongMemEval
run and a 50-case LoCoMo run, or the local LoCoMo cap, show stable answer
behavior with no hidden pass-to-fail regressions, no source-grounding
regression, and no kernel default change.

Disconfirming evidence:

- LoCoMo remains weak or unexplained at case level.
- LongMemEval improves but LoCoMo regresses or remains opaque.
- Evidence grounding regresses even when aggregate pass rate improves.
- Full-chain LLM judge is unavailable; deterministic smoke can then support
  diagnostics only, not promotion.
- Kernel traces are present only when explicitly opted in, but a phase result
  treats trace presence as answer-quality evidence.

## Scope

In scope:

- Refresh phase-8 planning artifacts from this bundle.
- Run `uv run pytest -q` and `uv run ruff check .`.
- Run LongMemEval and LoCoMo milestone evals in parallel with
  `MEMORYOS_MEMORY_ARCH=v3` and unique run ids.
- Produce case-level analysis for both benchmarks:
  pass/fail, fail-to-pass, pass-to-fail, unchanged fail, retrieval miss,
  evidence hit but context missing, evidence hit but answer fail,
  unsupported answer, judge questionable, and source-grounding movement.
- Produce `work/phase-8/promotion_decision.md`.
- Produce `result.md`, `execute_review.md`, review artifacts, and `ack.json`
  only if the usable gate is satisfied. Otherwise produce `review_verdict.json`
  and an adjustment path.

Non-goals:

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not run the promotion eval through the opt-in kernel unless a separate
  kernel-specific diagnostic is explicitly marked as such.
- Do not use benchmark case-id hacks or expected-answer leaks.
- Do not rewrite `.hermes-loop` infrastructure.
- Do not hide pass-to-fail cases behind aggregate pass rate.
- Do not claim production readiness.

## Active Blueprint Section

Relevant active blueprint section: `.hermes-loop/blueprint.md`, "Phase 8 -
Promotion Gate And Next Blueprint Decision".

Required work:

- Run full tests and lint.
- Run LongMemEval 50 full-chain LLM judge.
- Run LoCoMo 50 full-chain LLM judge or all available local cases.
- Compare against Phase 0 baseline case by case.
- Produce `work/phase-8/promotion_decision.md`.

Decision options:

- `continue_targeted`: specific bottleneck remains and needs a new blueprint.
- `expand_eval`: 50-case evidence is stable enough for larger sample.
- `hold`: pass rate moved but evidence quality regressed.
- `promote_blueprint`: update active blueprint/state for the next loop.

Usable ACK gate:

- LongMemEval and LoCoMo are both analyzed.
- Pass-to-fail cases are explicit.
- Source grounding did not regress silently.
- Kernel default remains unchanged unless human approval exists.
- No full-eval recommendation is made from aggregate score alone.

No promoted amendment is currently active for phase 8.

## Required MemoryOS Files To Read First

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-6/ack.json`
- `.hermes-loop/work/phase-7/ack.json`
- `.hermes-loop/work/phase-7/result.md`
- `.hermes-loop/work/phase-7/execute_review.md`
- `.hermes-loop/work/phase-7/reflect_phase-7.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agentic-memory-roadmap-zh.md`
- `src/memoryos_lite/config.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/diagnostic_report.py`
- `src/memoryos_lite/agent_kernel.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_kernel.py`
- `tests/test_context_composer.py`
- `tests/test_evals.py`

## Required Letta Reference Files

Letta is a design reference only. Do not add it as a runtime dependency.

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

For Phase 8, use these files to frame gaps and next-blueprint targets, not to
port internals.

## Relevant Prior Evidence

Phase 6 usable ACK:

- LongMemEval 30 full-chain LLM judge: `29/30`.
- LongMemEval fail-to-pass: `e47becba`, `118b2229`, `58bf7951`,
  `6ade9755`, `58ef2f1c`, `5d3d2817`, `94f70d80`, `66f24dbb`,
  `c8c3f81d`, `75499fd8`, `0862e8bf`.
- LongMemEval pass-to-fail: none reported.
- LongMemEval retrieval miss: none reported.
- LongMemEval evidence-hit-answer-fail: `51a45a95`.
- LoCoMo 30 full-chain LLM judge: `18/30`.
- LoCoMo fail-to-pass: `conv-26_qa_002`, `conv-26_qa_005`,
  `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_014`,
  `conv-26_qa_015`, `conv-26_qa_021`, `conv-26_qa_023`,
  `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- LoCoMo pass-to-fail: none reported.
- LoCoMo retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`,
  `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`.
- LoCoMo evidence-hit-answer-fail: `conv-26_qa_006`,
  `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_024`,
  `conv-26_qa_027`.

Phase 7 usable ACK:

- Kernel path remained opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- Public benchmark preserved structured `kernel_trace_events` only when
  explicitly opted in.
- LongMemEval 5-case no-LLM opt-in kernel smoke: `1/5`;
  structured traces in `5/5`; evidence-hit-answer-fail:
  `e47becba`, `118b2229`, `51a45a95`, `58bf7951`.
- LoCoMo 5-case no-LLM opt-in kernel smoke: `0/5`;
  structured traces in `5/5`; retrieval misses:
  `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`,
  `conv-26_qa_005`; evidence-hit-answer-fail: `conv-26_qa_001`.
- Phase 7 reflection says the kernel trace probe is not answer-quality
  evidence and LoCoMo remains the main benchmark risk.

Existing phase-8 `research.md` and `reviews/codex-review.md` predate this
bundle and refer to a legacy default/deprecation decision. Treat them as stale
unless overwritten by a lane result that cites this bundle.

## Current Benchmark Baseline

Project docs still record this older baseline:

- Full pytest: `352 passed, 1 warning`.
- Hard eval: `1.00/1.00`.
- v2 LongMemEval limit 10 no-LLM smoke:
  `episode_source_hit_at_10 = 8/10`,
  `planned_evidence_source_hit_at_5 = 8/10`.
- v2 LoCoMo limit 10 no-LLM smoke:
  `episode_source_hit_at_10 = 5/10`,
  `planned_evidence_source_hit_at_5 = 5/10`.

More recent phase artifacts report:

- Phase 5 full tests: `388 passed`.
- Phase 6 full tests: `396 passed`.
- Phase 7 full tests: `400 passed`.

Treat these as historical evidence until rerun in Phase 8.

## Fresh Phase 8 Evidence

Current complete milestone evidence:

- LongMemEval final run: `phase8_lme50_20260522T151605Z`, report
  `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`, command
  used `MEMORYOS_MEMORY_ARCH=v3`, `--llm-answer`, `--llm-judge`, and did not
  set `MEMORYOS_AGENT_KERNEL=v1`.
- LoCoMo final run: `phase8_locomo50_20260522T151605Z`, report
  `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`, command used
  `MEMORYOS_MEMORY_ARCH=v3`, `--llm-answer`, `--llm-judge`, and did not set
  `MEMORYOS_AGENT_KERNEL=v1`.
- Focused guard: `3 passed` in `.hermes-loop/work/phase-8/logs/focused_guard.log`.
- Full pytest before the hardening diagnostic fix: `400 passed, 1 warning` in
  `.hermes-loop/work/phase-8/logs/full_pytest.log`.
- Fresh full pytest after the hardening diagnostic fix: `410 passed, 1 warning`.
- Ruff: `All checks passed!` in `.hermes-loop/work/phase-8/logs/ruff.log`.

The later heartbeat retry run ids
`phase8_lme50_hb_20260522T160637Z` and
`phase8_locomo50_hb_20260522T160637Z` ended with status `143` and only partial
projected/no-judge artifacts. They are not promotion evidence.

## Pass-To-Fail Risks

- Parallel evals can collide if they share the default timestamp run id.
  Always pass unique run ids.
- LoCoMo can show retrieval misses even when answer projection improves.
- Source hit can be true while answer support or context grounding is still
  wrong; do not collapse these into one metric.
- Structured `kernel_trace_events` may affect downstream consumers, but default
  kernel-off reports should still have empty kernel traces.
- Existing worktree is dirty with `.hermes-loop` and AGENTS/CLAUDE changes.
  Preserve user changes and avoid unrelated cleanup.

## RED Evidence For Phase 8

No new production code should be written before a failing test unless the lane
marks Phase 8 as decision-only. For the decision-only path, the RED evidence is
the lack of current 50-case full-chain phase-8 promotion evidence and stale
phase-8 artifacts that do not cite this context bundle.

If a code change becomes necessary, add a focused failing test first and record
the failing command in `result.md`.

## Expected Verification Commands

Focused guard:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q
```

Full checks:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone evals must be run in parallel, with unique run ids and without
`MEMORYOS_AGENT_KERNEL=v1`:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 50 \
  --run-id phase8_lme50_<timestamp>
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 50 \
  --run-id phase8_locomo50_<timestamp>
```

If LLM provider access is unavailable, record the exact failure, run
deterministic/no-LLM fallback only as diagnostic evidence, and do not issue an
`expand_eval` or `promote_blueprint` decision.

## Anti-Demo Completion Criteria

Phase 8 reaches usable only if:

- `promotion_decision.md` uses fresh Phase 8 verification and case-level eval
  evidence.
- Both LongMemEval and LoCoMo are separated in the analysis.
- Pass-to-fail and fail-to-pass are explicit, or the lack of a same-subset
  baseline is explicitly stated.
- Retrieval/source misses are separated from answer projection and judge
  instability.
- Kernel default remains unchanged.
- `ack.json` contains the active goal and the full ACK contract fields.

Plan-only, stale-artifact-only, or deterministic-smoke-only output must not
advance.

## Required Default/Fallback Constraints

- `src/memoryos_lite/config.py` currently defaults
  `memoryos_memory_arch: str = "v3"`.
- `MEMORYOS_MEMORY_ARCH=v1` must remain an explicit fallback.
- `MEMORYOS_AGENT_KERNEL` must resolve to `off` unless set to `v1`.
- `MEMORYOS_AGENT_KERNEL=v1` is opt-in only and must not be used for promotion
  evals unless explicitly labeled as a kernel diagnostic.
