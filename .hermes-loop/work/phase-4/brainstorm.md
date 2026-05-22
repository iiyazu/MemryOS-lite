# phase: phase-4

# Brainstorm: Archive And Passage Scope

Context bundle citation: `.hermes-loop/work/phase-4/context_bundle.md` (`god_dispatch.json` path `work/phase-4/context_bundle.md`, sha256 `c12ced67fcb4a1980a01659372e676570a9c0d199299c31a6afcdcd5cd674037`).

Active goal: "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default."

## Current Read

- `V3ContextComposer._archival_items()` currently calls `store.list_archival_passages()` with no scope, then searches globally. This is the failure point for unattached archive pollution.
- `v3_contracts.py` already has `ArchivalPassage` and `ArchiveAttachment`; `store.py` can persist/list passages and attachments; `ArchivalPassageSearcher` already returns passage metadata and source refs.
- Letta semantics to adopt, not import: archives are attached to agents; passages are either agent/archive passages or source/file passages; agent passages require `archive_id` and no `source_id`; source passages require `source_id` and no `archive_id`.
- Public benchmark output already carries append-only `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`; phase 4 should extend diagnostics, not scoring fields.

## Options

### Option A: composer-local filtering only

Filter global `list_archival_passages()` results inside `_archival_items()` using attachments and request/session metadata.

Tradeoff: smallest patch, but diagnostics would be weak and store/search callers could still accidentally use global top-k. It risks satisfying tests while leaving a demo-level helper path.

### Option B: MemoryOS-native eligibility contract

Add a narrow eligibility helper/API around existing SQLite store data: resolve eligible archive IDs from request scope, list eligible passages, search only that set, and emit archival diagnostics for `selected`, `eligible_no_match`, `scope_excluded`, and `no_attached_archive`.

Tradeoff: moderate change, but it uses current contracts and tables, keeps SQLite authoritative, avoids a Letta dependency, and gives public eval case-level visibility into retrieval miss vs scope exclusion.

### Option C: full Letta-style archive manager layer

Introduce richer archive identity/manager services, default archive creation, detach/delete lifecycle, and broader tool/kernel integration.

Tradeoff: closer to Letta but too broad for this phase. It would pull work toward kernel/tool behavior and storage rewrite risks before the benchmark diagnostics are stable.

## Chosen Route

Choose Option B.

Implementation shape:

- Extend `ContextComposerRequest` or v3 composer request derivation with archival scope inputs already available from MemoryOS: `session_id`, optional `identity_scope`, and metadata-compatible IDs such as `agent`, `run`, `source`, or benchmark session/source IDs when present.
- Add store/search-facing helpers that resolve attached archive IDs for a scope and return only eligible passages. Keep global `list_archival_passages()` available for tests/admin use, but the v3 composer must not call it unscoped.
- Keep passage invariants explicit in contract/store tests: agent passage means `archive_id` and no `source_id`; source passage means `source_id` and no `archive_id`. Do not add Letta runtime imports.
- In `V3ContextComposer`, compute eligibility before lexical search, search only eligible passages, and append diagnostics that show selected passage IDs, eligible archive IDs, selected source refs, and counts/reasons for excluded or unmatched passages.
- In public benchmark reports, expose archival eligibility through existing append-only v3 diagnostic/report fields. Do not alter verdict, score, `source_hit`, or movement semantics.
- Preserve explicit `MEMORYOS_MEMORY_ARCH=v1` isolation and keep `MEMORYOS_AGENT_KERNEL` default `off`.

## RED Tests To Start

- `tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope`: attached archive passage is selected; unattached distractor with better lexical match is excluded.
- `tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility`: diagnostics include eligible archive IDs, selected passage IDs, `archival_scope_excluded`, and `archival_no_match` counts/reasons.
- `tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only`: report includes archival eligibility diagnostics while scoring fields and failure-class schema remain stable.
- `tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics`: explicit v1 has no v3 archival eligibility metadata or passage text.
- `tests/test_archival_store.py` or `tests/test_archival_searcher.py`: enforce agent/source passage invariants and passage-level citation/source-ref preservation if existing coverage is insufficient.

## Risks

- Scope too strict can exclude all archives in benchmark runs if no default benchmark/session attachment is created or inferred.
- Scope too loose preserves global top-k pollution and can regress source grounding through distractor passages.
- Source passage vs agent passage semantics can blur `source_id` and `archive_id`, making diagnostics look precise while eligibility is wrong.
- Core/archival source refs can pollute retrieval candidate metrics if not kept separate from final answer projection.
- LoCoMo may still fail after scoping; the phase must record case-level misses rather than claim LongMemEval-only movement.

## Anti-Demo Failure Modes

- Passing a helper test while real `MemoryOSService.build_context()` still searches global passages.
- Emitting only selected passages, without showing eligible-but-not-selected and scope-excluded counts.
- Hiding pass-to-fail cases behind aggregate pass rate or a 5/10 smoke.
- Adding archive code unused by public benchmark diagnostics.
- Making the kernel required for archive search or changing `MEMORYOS_AGENT_KERNEL` default.
- Adding benchmark case-id rules, expected-answer leaks, Letta runtime dependency, Qdrant dependency, or a storage rewrite beyond the eligibility contract.

## Why This Advances The Goal

The chosen route turns existing archive/passages from global demo retrieval into scoped, diagnosable v3 evidence in the real context and public benchmark path. That directly supports LongMemEval/LoCoMo case analysis by separating `archival_scope_excluded` from `archival_no_match`, while preserving v3 as the default memory architecture, keeping v1 explicit and isolated, and leaving `MEMORYOS_AGENT_KERNEL=v1` opt-in/default-off.
