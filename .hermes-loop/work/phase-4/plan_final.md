# phase: phase-4

# Final Plan: Archive Eligibility And Passage Scope

Context citation: `.hermes-loop/work/phase-4/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

This plan replaces stale broad Archival Memory Store work with a narrow MemoryOS-native archive eligibility contract. The implementation must wire scoped archival retrieval into the real v3 composer and public benchmark path, while preserving v1 fallback, v3 default behavior, and `MEMORYOS_AGENT_KERNEL` default-off.

## RED

Add failing tests before production changes:

1. `tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope`
   - Attached session archive passage is selected.
   - Better-matching unattached distractor passage is excluded.
   - Metadata reports eligible archive IDs and `archival_scope_excluded`.

2. `tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility`
   - Metadata includes `eligible_archive_ids`, `selected_passage_ids`, `selected_source_refs`, `eligible_passage_count`, `selected_passage_count`, `archival_scope_excluded`, and `archival_no_match`.
   - Diagnostics include archival eligibility events for selected, scope-excluded, no-match, or no-attached-archive cases.

3. `tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper`
   - Agent/archive passages require `archive_id` and must not set `source_id`.
   - Source/file passages require `source_id` and must not set `archive_id`.
   - Scoped helper returns only passages from attached archives.

4. `tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only`
   - Public report exposes archival eligibility through append-only v3/case diagnostics.
   - Scoring and movement fields remain unchanged.
   - Scope-excluded refs are not counted as retrieval candidates.

5. `tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics`
   - Explicit `MEMORYOS_MEMORY_ARCH=v1` has no v3 archival eligibility metadata and does not surface scoped v3 archival passage text.

Run each focused test and record RED output before implementation. If the v1 isolation test already passes, keep it as a guard and record that it was non-RED.

## GREEN

Implement only the scoped eligibility contract needed for this phase.

1. `src/memoryos_lite/v3_contracts.py`
   - Add narrow `ArchiveEligibilityScope` and `ArchiveEligibilityResult` models.
   - Extend `ContextComposerRequest` with optional archival scope metadata.
   - Validate new `ArchivalPassage` writes so agent/archive and source/file passage identities cannot be mixed.

2. `src/memoryos_lite/store.py`
   - Add `resolve_attached_archive_ids(...)` from session, identity scope, and explicit source IDs.
   - Add `list_archival_passages_for_scope(...)` that returns only eligible passages.
   - Keep global `list_archival_passages()` available only for explicit store/admin/test use.
   - Avoid broad migrations or storage rewrites unless strictly required by existing model fields.

3. `src/memoryos_lite/context_composer.py`
   - Replace unscoped global archival search in v3 with request-scoped eligibility resolution.
   - Search only eligible archival passages.
   - Emit append-only `metadata["archival_eligibility"]`.
   - Emit diagnostics that distinguish selected, eligible-but-no-match, scope-excluded, and no-attached-archive cases.

4. `src/memoryos_lite/engine.py`
   - Pass available session/identity/source scope into v3 composer.
   - Preserve `_should_route_to_v3_context()` behavior.
   - Keep explicit v1 isolated from v3 archival diagnostics.

5. `src/memoryos_lite/public_benchmarks.py`
   - Copy archival eligibility into existing append-only v3/case diagnostic fields.
   - Do not alter `verdict`, `source_hit`, `source_hit_at_k`, `planned_evidence_source_hit_at_5`, `failure_class`, or `movement_status`.

Do not add Letta as a runtime dependency. Adopt only the semantic contract from Letta references.

## REFACTOR

After focused tests pass, remove duplication and keep the API narrow:

- one helper for scope pair construction;
- one serialization shape for archival eligibility;
- no duplicated scope logic across store and composer;
- no benchmark case-id or expected-answer retrieval hacks;
- no kernel default change;
- no Qdrant/new production DB requirement.

Run:

```bash
uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q
uv run pytest -q
uv run ruff check .
```

## Smoke And Milestone

Run the mandatory full-chain evals separately:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30
```

Record separate LongMemEval and LoCoMo case-level reports:

- pass/fail counts;
- fail-to-pass and pass-to-fail;
- retrieval miss;
- context missing evidence;
- evidence-hit-answer-fail;
- unsupported answer;
- judge questionable;
- `archival_scope_excluded` vs `archival_no_match`;
- listed cases from `god_dispatch.json`, including `58bf7951`, `6ade9755`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, and `conv-26_qa_010`.

If LLM provider access blocks full-chain judging, record the exact blocker, run deterministic no-LLM fallback smokes, and label them non-milestone evidence.

## Review Gates

Reject usable ACK if any gate fails:

- real v3 `build_context()` still retrieves archival passages globally;
- unattached archive passages can pollute selected context;
- public benchmark diagnostics omit archival eligibility;
- retrieval miss vs archive scope exclusion is not diagnosable per case;
- LongMemEval or LoCoMo regressions are hidden by aggregate-only reporting;
- explicit v1 includes v3 archival metadata;
- v3 is no longer the default memory architecture;
- `MEMORYOS_AGENT_KERNEL=v1` becomes default or required;
- Letta runtime dependency, broad storage rewrite, Qdrant/new production DB, benchmark case hacks, or expected-answer leaks are introduced.
