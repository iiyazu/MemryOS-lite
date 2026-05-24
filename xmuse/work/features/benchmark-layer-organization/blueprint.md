# feature: benchmark-layer-organization

## Goal / User-Visible Value

Make MemoryOS Lite's message, episode, recall, core, and recent layers more
usable as benchmark engineering signals on LongMemEval and LoCoMo.

The first iteration is LoCoMo-first layer organization with LongMemEval as a
regression guard. It should improve evidence ordering, same-session neighbor
policy, and context/budget diagnostics so failures can be localized to retrieval,
selected context, rendered context, answer evidence, citation, or judge result.

This feature must not describe MemoryOS Lite as production-ready MemoryOS.

## Status

Planned feature lane. This feature is registered in
`xmuse/master_state.json` and must remain in planning until Master
dispatches a Slave.

Current live Master state, as of this blueprint draft:

- `archive-rag`: blocked.
- `v1-quarantine`: held.
- `xmuse-console`: planning queue.
- `benchmark-layer-organization`: planning queue.

Master must create/confirm the worktree before dispatching a Slave.

## Baseline Evidence

Fresh full-chain public evals were run before drafting this blueprint:

```bash
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge \
  --run-id routeb_lme50_llm_20260524
```

Report:
`.memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json`

Observed LongMemEval 50 result:

- Verdict: `48 pass / 2 fail`.
- Failure class: `supported_cited_answer=48`, `retrieval_miss=2`.
- `source_hit`: `48/50`.
- `episode_source_hit_at_10`: `44/50`.
- `planned_evidence_source_hit_at_5`: `43/50`.
- `budget_dropped_relevant_sum`: `74`.
- Movement: `new_case_no_baseline=50` because no comparison report was supplied.

```bash
uv run memoryos eval public --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge \
  --run-id routeb_locomo50_llm_20260524
```

Report:
`.memoryos/evals/routeb_locomo50_llm_20260524_locomo.json`

Observed LoCoMo 50 result:

- Verdict: `34 pass / 16 fail`.
- Failure class: `supported_cited_answer=27`, `retrieval_miss=16`,
  `evidence_hit_answer_fail=7`.
- `source_hit`: `34/48`.
- `episode_source_hit_at_10`: `29/48`.
- `planned_evidence_source_hit_at_5`: `26/48`.
- `source_not_indexed_sum`: `1`.
- `budget_dropped_relevant_sum`: `0`.
- Movement: `new_case_no_baseline=50` because no comparison report was supplied.

Interpretation:

- LoCoMo is the primary target for this iteration.
- Retrieval and evidence handoff failures are the dominant actionable boundary.
- Answer-quality failures exist but are not the first implementation target.
- Some LoCoMo cases can pass judge while still showing retrieval diagnostics
  miss, so final pass rate must not be used as proof of retrieval localization.

## Scope

In:

- Improve recall evidence ordering for benchmark-style temporal and
  multi-session questions.
- Make same-session neighbor / packet policy explicit, testable, and visible in
  diagnostics.
- Improve v3 component accounting and final context trace for recall/core/recent
  layer evidence.
- Strengthen case diagnostics so retrieval, selected context, rendered context,
  answer evidence, citation, and judge result remain separate.
- Track fixed-slice case movement with fail-to-pass, pass-to-fail,
  unchanged-pass, and unchanged-fail counts.

## Non-Goals

- Archive RAG, archival vector retrieval, Qdrant archive indexing, and
  archive-rag lane implementation details.
- Redis, A2A, AutoGen, or other new required infrastructure.
- New production database backend.
- Generic answer prompt rewrite as the primary work item.
- Dataset-specific hacks, case-id rules, benchmark-string overfitting, or
  hand-coded answers.
- Making `MEMORYOS_RECALL_PIPELINE=v2` the default.
- Changing `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Enabling `MEMORYOS_AGENT_KERNEL=v1` by default.
- Merge. Master owns integrated tests, approval artifacts, and final merge
  decision.

## Allowed Files

Product code:

- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_case_movement.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/evals.py`

Tests:

- `tests/test_episode_retrieval.py`
- `tests/test_recall_pipeline.py`
- `tests/test_context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_diagnostic_report.py`
- narrowly scoped eval tests if a report field changes.

Docs/artifacts:

- `docs/public-benchmark-diagnosis.md` if metric meaning or current baseline is
  updated.
- `xmuse/work/features/benchmark-layer-organization/*` feature-local
  artifacts.

Not allowed:

- `xmuse/work/features/archive-rag/*`
- archive-rag product implementation files except incidental read-only conflict
  checks by Master.
- `xmuse/history/`
- `xmuse/legacy/root-loop/`
- deleted historical phase paths or deleted baseline/superpowers docs.

## Invariants

- MemoryOS Lite remains an eval-driven, source-attributed Agent/RAG memory
  prototype.
- SQLite remains the authoritative store.
- Filesystem pages/traces remain debug mirrors only.
- v3 layered composer remains default.
- v1 ContextBuilder remains available with `MEMORYOS_MEMORY_ARCH=v1`.
- Episode-first recall remains opt-in with `MEMORYOS_RECALL_PIPELINE=v2`.
- Agent kernel remains opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- Source refs must survive recall search, v3 context items, component
  accounting, final context trace, and public case diagnostics.
- Retrieval diagnostics and answer-quality diagnostics must stay separate.
- Public benchmark `source_hit` must not be treated as pure retrieval
  localization.
- Budget-dropped candidates must not be reported as selected/rendered evidence.

## Implementation Tasks

This feature should execute in phase gates. Each phase must leave a reviewable
artifact trail in `result.md`; later phases may refine earlier work but must not
skip the evidence gates. The phase labels below are feature-local planning
sections, not references to legacy `xmuse/work/phase-*` directories.

### Phase 0: Baseline Replay And RED Tests

Goal:

- Reproduce or cite the two baseline reports listed above.
- Add focused failing tests that expose the current LoCoMo layer-organization
  weakness before changing retrieval behavior.

Allowed work:

- Add tests for same-session packet selection, neighbor boundary preservation,
  budget drop visibility, and final context source-ref traceability.
- Add tests showing that judge pass does not imply retrieval localization.

Verification:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
uv run pytest tests/test_context_composer.py -q
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Exit criteria:

- At least one RED test fails for the intended Route B gap.
- Existing unrelated tests are not modified to hide the gap.
- `result.md` records the failing test names and expected failure reason.

### Phase 1: Recall Packet And Neighbor Policy

Goal:

- Make LoCoMo-style same-session recall packets explicit and stable.
- Improve recall evidence ordering without dataset-specific hacks.

Allowed work:

- Refine `RecallMemorySearcher` and `RecallPipeline` around lexical overlap,
  role, temporal markers, benchmark session metadata already present in
  messages, packet membership, neighbor distance, budget fit, and source refs.
- A direct hit may bring same-session neighbors needed to answer multi-turn
  LoCoMo questions.
- Neighbor rows must not cross benchmark session boundaries.

Forbidden work:

- Case id rules.
- Benchmark-specific answer strings.
- Hard-coded LoCoMo conversation ids.
- Expected-source-id shortcuts.

Verification:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

Exit criteria:

- Phase 0 recall RED tests pass.
- Recall diagnostics include packet id, anchor message id, member message ids,
  benchmark session id, neighbor offsets, and source refs.
- v2 recall remains opt-in; this phase must not make
  `MEMORYOS_RECALL_PIPELINE=v2` default.

### Phase 2: V3 Composer Accounting And Context Handoff

Goal:

- Preserve packet/neighbor evidence through v3 context construction and final
  context trace.
- Make selected, rendered, and dropped evidence auditable per component.

Allowed work:

- Strengthen v3 component accounting for recall/core/recent layers.
- Final context trace must identify included and dropped recall evidence.
- Drop counts and token totals must stay component-scoped.
- Budget-dropped candidates must not be counted as selected or rendered.

Verification:

```bash
uv run pytest tests/test_context_composer.py -q
```

Exit criteria:

- Phase 0 composer RED tests pass.
- Final context trace includes source refs and packet/neighbor metadata for
  selected recall evidence.
- Budget-dropped evidence remains visible as dropped and absent from selected /
  rendered source ids.

### Phase 3: Public Diagnostics And Movement Accounting

Goal:

- Make public benchmark reports explain where each case failed without relying
  on aggregate pass rate.

Allowed work:

- Keep separate stage statuses for retrieval, selected context, rendered
  context, answer evidence, citation, and judge result.
- Preserve cases where judge passes but retrieval diagnostics miss.
- Report failure boundary independently from final verdict.
- Add movement reporting expectations for fixed slices.

Verification:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Exit criteria:

- Phase 0 public diagnostics RED tests pass.
- Movement fields include fail-to-pass, pass-to-fail, unchanged-pass,
  unchanged-fail, and new-case-no-baseline.
- Reports can distinguish retrieval improvement from answer-quality movement.

### Phase 4: Full Verification, Fixed-Slice Movement, And Handoff

Goal:

- Run full project gates and public full-chain evals with baseline comparison.
- Produce Slave handoff artifacts with phase-by-phase evidence.

Required work:

- Run focused tests, regression gates, and the public full-chain gates listed in
  `Required Tests / Evals`.
- Compare against the baseline reports named in this blueprint.
- Record case-level fail-to-pass and pass-to-fail movement for both benchmarks.
- Record any LongMemEval pass-to-fail with case-level explanation or roll back
  the responsible strategy.

Exit criteria:

- All required verification commands have fresh results in `result.md`.
- `ack.json` states whether the feature is usable, partially usable, blocked,
  or non-usable.
- `review_verdict.json` self-audits every review failure criterion.

## Required Tests / Evals

Focused tests:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

```bash
uv run pytest tests/test_context_composer.py -q
```

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Regression gates:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Public full-chain gates:

```bash
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge \
  --run-id routeb_lme50_after_benchmark_layer_organization \
  --comparison-report .memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json
```

```bash
uv run memoryos eval public --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge \
  --run-id routeb_locomo50_after_benchmark_layer_organization \
  --comparison-report .memoryos/evals/routeb_locomo50_llm_20260524_locomo.json
```

The exact `--run-id` values must be recorded in the result artifact.

## Completion Criteria

- LoCoMo case diagnostics explicitly separate retrieval miss, selected drop,
  render drop, answer evidence drop, citation drop, unsupported answer, and
  judge fail.
- LoCoMo result reports case-level movement against the baseline report, not
  only aggregate pass rate.
- At least one fixed LoCoMo failure cluster has either:
  - specific fail-to-pass movement, or
  - explicit diagnostic movement that narrows the failure boundary.
- Any LoCoMo improvement claim is limited to diagnostic improvement, specific
  cluster movement, or case-level movement unless a fixed-slice fail-to-pass /
  pass-to-fail list supports a broader claim.
- LongMemEval 50 is used as a regression guard. No LongMemEval pass-to-fail is
  acceptable without a case-level explanation and an explicit decision to keep
  or roll back the responsible strategy.
- LongMemEval does not need to improve for this feature to complete.
- v1 fallback, v2 recall opt-in, agent kernel opt-in, SQLite authority, and
  source attribution are preserved.
- Result artifact records exact commands, report paths, summary metrics,
  case-level movement, residual failures, and skipped checks if any.

## Review Failure Criteria

Master review must reject or return the feature if any of these are true:

- The implementation touches archive-rag scope or relies on archive-rag
  artifacts as current Route B implementation input.
- `MEMORYOS_RECALL_PIPELINE=v2` is made default.
- v1 fallback or agent kernel opt-in boundaries change.
- A benchmark improvement claim is aggregate-only.
- A LoCoMo improvement claim lacks fail-to-pass / pass-to-fail case lists or
  explicit diagnostic movement.
- A LongMemEval pass-to-fail lacks case-level explanation or rollback decision.
- Retrieval miss is hidden behind judge pass.
- Answer-quality diagnostics are mixed into retrieval diagnostics.
- Source refs are missing from selected recall evidence or v3 final context
  trace.
- Budget-dropped evidence is counted as selected/rendered.
- New required Redis, Qdrant, A2A, AutoGen, or production DB dependency is
  introduced.
- The feature describes MemoryOS Lite as production-ready.
- Required tests/evals are missing, stale, or not run fresh in the feature
  worktree.

## Handoff Artifacts

Slave handoff artifacts:

- `xmuse/work/features/benchmark-layer-organization/ack.json`
- `xmuse/work/features/benchmark-layer-organization/result.md`
- `xmuse/work/features/benchmark-layer-organization/review_verdict.json`

The result artifact must include:

- Baseline report paths used for movement comparison.
- New report paths.
- LongMemEval 50 summary.
- LoCoMo 50 summary.
- Case-level fail-to-pass and pass-to-fail lists.
- Failure boundary movement summary.
- Explicit statement that any claim is diagnostic/case-level unless broader
  evidence is present.

Master-owned artifacts after dispatch:

- `xmuse/master/features/benchmark-layer-organization/master_review.json`
- `xmuse/master/features/benchmark-layer-organization/integrated_tests.json`
- `xmuse/approvals/benchmark-layer-organization/merge_approval_request.json`
- `xmuse/approvals/benchmark-layer-organization/merge_approval.json`
- `xmuse/approvals/benchmark-layer-organization/merge_decision.json`
- `xmuse/approvals/benchmark-layer-organization/post_merge_verification.json`

## Merge / Approval Gate

- Master must add the feature to `xmuse/master_state.json` before Slave
  dispatch.
- Slave may work only inside this blueprint scope.
- Master must run fresh integrated tests after Slave artifacts exist.
- Merge requires explicit approval artifacts and fresh target validation.
- No agent in this blueprint may merge directly.
