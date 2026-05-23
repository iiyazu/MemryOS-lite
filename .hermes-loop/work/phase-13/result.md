# phase: phase-13

# Phase 13 Result

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-13/context_bundle.md`.

## Summary

Phase 13 wired approved core-memory promotion into the real store/lifecycle/composer chain:

- approved archival-to-core candidates now update an existing same-label core block in place instead of creating duplicate live blocks;
- duplicate live labels now fail closed before promotion can overwrite an arbitrary block;
- core block updates now require audit metadata at the store boundary and record history there;
- read-only core blocks now reject direct store update and delete attempts;
- v3 context rendering now proves approved core promotion value, source refs, provenance metadata, and token accounting through the real composer path.

No benchmark improvement is claimed from this structural lifecycle work.

## Changed Chain

- `ingest`: not applicable.
- `store`: changed audited core block update/delete boundaries and read-only enforcement.
- `retrieval`: verified only through promotion inputs and archival-to-core candidate source refs.
- `context_composer`: verified approved core promotion rendering and budget accounting through v3 composer tests.
- `answer_projection`: not changed.
- `kernel_loop`: not changed; `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- `public_eval`: structurally smoked with v3/projected/no-judge runs; no full-chain milestone eval was required for this phase.

## RED Evidence

Recorded in `.hermes-loop/work/phase-13/red_tests.md`.

All five RED tests failed before production changes:

- promotion created a duplicate `human` block instead of updating in place;
- duplicate labels were not rejected;
- direct store update lacked audit metadata requirements;
- read-only direct store mutation was not guarded at the store boundary;
- v3 composer could not render approved promotion provenance because the live block was not updated.

## Verification

Focused RED/GREEN target set:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history tests/test_memory_lifecycle.py::test_archival_to_core_candidate_rejects_duplicate_label_conflict tests/test_core_memory_store.py::test_core_memory_store_update_requires_audit_metadata tests/test_core_memory_store.py::test_read_only_core_block_rejects_store_update_and_delete tests/test_context_composer.py::test_v3_composer_renders_approved_core_promotion_with_provenance -q
```

Result: `5 passed`.

Focused regression suite:

```bash
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py -q
```

Result: `30 passed`.

Default/fallback/kernel preservation:

```bash
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
```

Result: `3 passed`.

Baseline:

```bash
uv run pytest -q
uv run ruff check .
```

Results:

- full suite: `451 passed, 1 warning in 613.89s`;
- ruff: `All checks passed!`.

## Public Smoke

These are 5-case v3 no-LLM structural smokes, not milestone or promotion evidence.

LongMemEval report:

- path: `.hermes-loop/work/phase-13/smoke_longmemeval/evals/public_20260523_152027_longmemeval.json`;
- command: `DATA_DIR=.hermes-loop/work/phase-13/smoke_longmemeval MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge`;
- result: `1 pass / 4 fail`;
- answer mode: `projected`;
- judge status: `not_run`;
- memory arch: `v3`;
- kernel trace events: `0/5 cases`;
- source hit: `5/5`;
- planned evidence source hit at 5: `4/5`;
- episode source hit at 10: `4/5`;
- cases:
  - `e47becba`: fail, `evidence_hit_answer_fail`;
  - `118b2229`: fail, `evidence_hit_answer_fail`;
  - `51a45a95`: fail, `evidence_hit_answer_fail`;
  - `58bf7951`: fail, `evidence_hit_answer_fail`, planned/episode miss;
  - `1e043500`: pass, `supported_cited_answer`.

LoCoMo report:

- path: `.hermes-loop/work/phase-13/smoke_locomo/evals/public_20260523_151822_locomo.json`;
- command: `DATA_DIR=.hermes-loop/work/phase-13/smoke_locomo MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 5 --no-llm-answer --no-llm-judge`;
- result: `0 pass / 5 fail`;
- answer mode: `projected`;
- judge status: `not_run`;
- memory arch: `v3`;
- kernel trace events: `0/5 cases`;
- source hit: `2/5`;
- planned evidence source hit at 5: `1/5`;
- episode source hit at 10: `1/5`;
- cases:
  - `conv-26_qa_001`: fail, `evidence_hit_answer_fail`;
  - `conv-26_qa_002`: fail, `evidence_hit_answer_fail`, planned/episode miss;
  - `conv-26_qa_003`: fail, `retrieval_miss`;
  - `conv-26_qa_004`: fail, `retrieval_miss`;
  - `conv-26_qa_005`: fail, `retrieval_miss`.

An initial shared-store parallel smoke produced a LoCoMo `session not found` crash while LongMemEval completed. The isolated `DATA_DIR` rerun completed and is the evidence used above. This indicates the shared default `.memoryos` eval store is unsafe for parallel public smokes unless each run is isolated.

## Phase 11 Debt Visibility

Phase 13 does not resolve Phase 11 LoCoMo debt. The following known LoCoMo risks remain visible and unhidden:

- `conv-26_qa_028` pass-to-fail risk from the latest Phase 11 gate;
- `conv-26_qa_005` source-miss judged-pass risk;
- unchanged Phase 11 failures: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`.

## Notes

- v1 fallback remained explicit and verified.
- v3 remained the default memory architecture and verified.
- `MEMORYOS_AGENT_KERNEL=v1` remained opt-in; smoke reports had empty kernel traces.
- No LongMemEval-only improvement or aggregate benchmark improvement is claimed.
