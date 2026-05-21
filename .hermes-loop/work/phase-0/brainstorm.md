# phase: phase-0

## Active Goal

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Bundle And Assumptions

Read `.hermes-loop/work/phase-0/context_bundle.md` before any other phase-local artifact, then read `.hermes-loop/work/phase-0/god_dispatch.json`.

Bundle assumptions relied on:

- Phase 0 is a baseline freeze and case-harness phase, not a retrieval, context, prompt, or kernel optimization phase.
- Current weak smoke must stay visible: LongMemEval v3 projected `1/5`, LoCoMo v3 projected `0/5`, kernel opt-in LLM judge `1/5` on both listed 5-case runs.
- The active path is public benchmark -> `MemoryOSService.ingest/build_context` -> v3 `ContextComposer` -> `PublicBenchmarkResult` diagnostics.
- `MEMORYOS_MEMORY_ARCH=v3` remains the default architecture, `MEMORYOS_MEMORY_ARCH=v1` remains fallback, and `MEMORYOS_AGENT_KERNEL=v1` remains opt-in only.
- A usable ACK needs stable per-case rows, separated LongMemEval and LoCoMo results, v3 diagnostic fields, kernel trace presence/absence, focused test status, and explicit non-advance if evidence is missing.

Additional evidence checked:

- `src/memoryos_lite/config.py` keeps `memoryos_memory_arch = "v3"`, `memoryos_agent_kernel = "off"`, and `memoryos_recall_pipeline = "v1"`.
- `src/memoryos_lite/engine.py` only routes into the v3 composer when resolved arch is `v3` and `memoryos_memory_arch` is explicitly set; kernel runner is constructed only when `resolved_agent_kernel == "v1"`.
- `src/memoryos_lite/evals.py` and `src/memoryos_lite/public_benchmarks.py` carry `memory_arch`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, and `kernel_trace_events`.
- `tests/test_public_benchmarks.py` asserts v3 diagnostic reporting and the opt-in kernel trace sequence.
- `docs/public-benchmark-diagnosis.md` warns that final `source_hit` is not pure retrieval localization.

## Approaches

### A. Artifact-only freeze from existing reports

Use the recent `.memoryos/evals` reports cited by the bundle, transcribe the listed 5-case failures into `baseline_case_matrix.md`, and run only focused tests.

Pros: fastest; minimal cost; avoids changing runtime behavior.  
Cons: risks stale report metadata; may not prove current code still emits the same diagnostic fields; weak if later phases need fresh run IDs.

### B. Fresh deterministic freeze with focused tests

Run focused tests, then refresh 5-case LongMemEval and LoCoMo with `MEMORYOS_MEMORY_ARCH=v3`, `--no-llm-answer`, and `--no-llm-judge`; run one kernel smoke only with `MEMORYOS_AGENT_KERNEL=v1`; build `baseline_case_matrix.md` from the new reports and record any blockers.

Pros: best fit for Phase 0; freezes current code, stable case IDs, diagnostic fields, and kernel opt-in behavior without optimizing; keeps LongMemEval and LoCoMo separate.  
Cons: still smoke-level evidence; no full-chain judge gate unless provider access is available; deterministic projection may classify answer failures conservatively.

### C. Diagnostics-first implementation

Add or adjust diagnostics before refreshing the baseline, with failing tests first if current reports cannot classify cases.

Pros: useful if required fields are actually absent or impossible to classify.  
Cons: high risk of turning Phase 0 into behavior or instrumentation work; violates the intended freeze unless missing diagnostics are proven; can mask whether current baseline was ever usable.

## Recommendation

Use Approach B as the default route.

Execution should be: confirm defaults and active dispatch, run the focused tests, refresh deterministic 5-case reports for both benchmarks, run the opt-in one-case kernel smoke, then write the baseline matrix with explicit case IDs and taxonomy. Only fall back to Approach C if a real report lacks required v3 diagnostics or stable case identifiers; if that happens, add a failing test before touching production code. Approach A is acceptable only as a temporary fallback if local benchmark execution is blocked, and it should not satisfy usable ACK by itself.

## Risks

- Conflating final `source_hit` with evidence localization; matrix rows should prefer episode/planned evidence, selected context, and v3 diagnostics when available.
- Hiding LoCoMo regressions behind LongMemEval rows or aggregate pass rate.
- Treating 5-case smoke as benchmark improvement evidence instead of baseline inspection.
- Accidentally running kernel smoke without explicit `MEMORYOS_AGENT_KERNEL=v1`, or interpreting kernel traces as default behavior.
- Losing the `MEMORYOS_MEMORY_ARCH=v1` fallback while asserting v3 behavior.
- Letting optional 30-case LLM judge absence pass as a milestone gate instead of recording a provider/cost blocker.

## Demo-only Or Partial Completion

Counts as demo-only or partial:

- A matrix without stable case IDs or without separate LongMemEval and LoCoMo sections.
- Aggregate pass-rate notes without per-case failure classification.
- Reports that omit `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`, or kernel trace presence/absence.
- Kernel evidence collected without explicit opt-in, or any claim that the v3 kernel is now default.
- Prompt/report-only language claiming architecture progress without case-level evidence.
- Any `advance` decision when focused tests fail, required reports are missing, or diagnostic gaps remain unexplained.
- Any source, test, docs, `state.json`, or `blueprint.md` change performed as part of this brainstorm task.
