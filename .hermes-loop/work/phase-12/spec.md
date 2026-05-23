# phase: phase-12

# Phase 12 Spec: Scoped Tool-Written Archival Memory

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.
Brainstorm: `.hermes-loop/work/phase-12/brainstorm.md`.
Dispatch: `.hermes-loop/work/phase-12/god_dispatch.json`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope Decision

Use Route B from the brainstorm: make tool-written archival memory a real scoped archival/RAG write, not a recent-message demo.

The target chain is:

```text
approved archive_write
-> ArchivalMemory
-> apsg_{memory_id} ArchivalPassage
-> explicit session-scoped archive eligibility
-> V3ContextComposer archival item
-> v3 final trace and legacy ContextPackage.retrieved_evidence source refs
```

The expected implementation is a bounded, source-grounded session archive attachment created by the tool write path. This borrows Letta's explicit archive attachment semantics without adding Letta as a dependency and without making archival passages globally searchable.

## Required Behavior

1. `SimpleToolExecutionManager._archive_write()` must continue to reject sourceless writes. A write is valid only with `source_refs` or an approval-derived manual source ref.
2. An approved `archive_write` must persist an `ArchivalMemory` and bridged `ArchivalPassage` exactly as the current store contract already does.
3. The same write must make the written archive eligible for the same session through an explicit session attachment or equivalent exact-scope mechanism.
4. A later same-session `V3ContextComposer.build()` for a matching task must select the bridged passage as an `archival` item and expose:
   - `item.text` equal to the written content;
   - message source refs from the tool request;
   - `metadata["archival_memory_id"]` or equivalent memory id provenance;
   - `metadata["archive_id"]`;
   - `package.metadata["archival_eligibility"]["selected_passage_ids"] == ["apsg_{memory_id}"]`.
5. The legacy v3 compatibility path must continue to expose archival source refs in `ContextPackage.retrieved_evidence`, using the source message id when available and `metadata["origin"] == "archival"`.
6. Existing update/delete behavior must remain intact: `update_archival_memory()` refreshes `apsg_{memory_id}`, and `delete_archival_memory()` prevents stale passage selection.
7. Existing scope boundaries must remain intact: session-attached archive passages must not leak into unrelated sessions or unattached archive scopes.

## Non-Goals

- Do not mark Phase 11 complete or write `work/phase-11/ack.json`.
- Do not tune LongMemEval or LoCoMo answer behavior in this phase.
- Do not change public benchmark scoring, judge behavior, expected answers, or case ids.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not add Letta as a runtime dependency.
- Do not treat a structural archival test as benchmark improvement evidence.

## RED Evidence

The required RED test is a focused kernel-to-context test in `tests/test_agent_kernel.py`.

Expected current failure before implementation: approved `archive_write` creates an archival memory, but same-session v3 context has no selected archival item because the written archive is not in `archival_eligibility.eligible_archive_ids`.

Record the failing command and output in `.hermes-loop/work/phase-12/red_result.md` before any production change.

## Verification

Focused verification after GREEN:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_archival_store.py tests/test_memory_lifecycle.py tests/test_context_composer.py -q
uv run ruff check .
```

Baseline verification before review:

```bash
uv run pytest -q
uv run ruff check .
```

Milestone full-chain LongMemEval/LoCoMo eval is not required if the implementation stays on the kernel/store/composer structural path and does not alter public benchmark context/reporting code. In that case Phase 12 must record `case_level_eval.limit = 0` with a not-applicable rationale and keep Phase 11 LoCoMo debt visible.

If `src/memoryos_lite/engine.py`, `src/memoryos_lite/public_benchmarks.py`, or public diagnostic projection code is changed, run the structural no-LLM public smoke from the context bundle before review.

## Completion Standard

Phase 12 is usable only if the real tool/store/passage/retrieval/context chain is exercised, at least one RED test failed before the fix, focused and baseline checks pass, and review confirms v1 fallback, v3 default, kernel opt-in, source grounding, and Phase 11 debt visibility.
