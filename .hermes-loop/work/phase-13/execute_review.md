# phase: phase-13

# Phase 13 Execute Review

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-13/context_bundle.md`.

## What real chain changed?

The real core-memory lifecycle chain changed:

- `MemoryLifecycleService.apply_candidate()` now routes approved archival-to-core candidates through `CoreMemoryService` and updates an existing same-label core block in place.
- `CoreMemoryService.get_block_by_label()` detects duplicate live labels and fails closed.
- `CoreMemoryService.update_block()` can pass merged promotion provenance into durable block metadata.
- `MemoryStore.update_core_memory_block()` now requires `actor`, `reason`, and `source_refs`, rejects read-only records, and writes the update/replace history event atomically with the mutation.
- `MemoryStore.delete_core_memory_block()` now rejects read-only records.
- `V3ContextComposer` was verified against the resulting durable core block, including source refs, provenance metadata, and token accounting.

## What is still demo-only or partial?

No phase-13 core-memory lifecycle behavior remains demo-only. The phase does not solve LoCoMo answer quality, retrieval localization, or Phase 11 pass-to-fail debt, and no benchmark improvement is claimed.

The initial shared-store parallel smoke showed that public benchmark commands can interfere when both use the default `.memoryos` store. The completed evidence uses isolated `DATA_DIR` runs.

## What tests proved the behavior?

- RED evidence: `.hermes-loop/work/phase-13/red_tests.md`.
- Target GREEN: `5 passed`.
- Focused regression suite: `30 passed`.
- Preservation checks: `3 passed`.
- Full suite: `451 passed, 1 warning`.
- Ruff: `All checks passed!`.

## Which benchmark cases moved or regressed?

No same-case LLM-judge movement claim is made. Phase 13 ran v3/projected/no-judge structural smokes only:

- LongMemEval 5: `1 pass / 4 fail`; source hit `5/5`; planned evidence source hit at 5 `4/5`; kernel traces empty.
- LoCoMo 5: `0 pass / 5 fail`; source hit `2/5`; planned evidence source hit at 5 `1/5`; kernel traces empty.

The smoke failures are retained as case-level evidence and are not hidden:

- LongMemEval fail cases: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`.
- LoCoMo fail cases: `conv-26_qa_001`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

## Did v1 fallback, v3 default, and kernel opt-in remain intact?

Yes, with fresh verification:

- v3 default and kernel-off default: `tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off`;
- default public benchmark v3 diagnostics: `tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics_by_default`;
- explicit v1 fallback without v3 case context: `tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context`;
- public smoke reports used `memory_arch=v3` and had empty `kernel_trace_events`.
