# phase: phase-4

# Spec: Archive Eligibility And Passage Scope

Context bundle: `.hermes-loop/work/phase-4/context_bundle.md` (`god_dispatch.json` sha256 `c12ced67fcb4a1980a01659372e676570a9c0d199299c31a6afcdcd5cd674037`).

Active goal: "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default."

Chosen route from `.hermes-loop/work/phase-4/brainstorm.md`: Option B, a narrow MemoryOS-native eligibility contract. The phase replaces global archival top-k behavior in the real v3 composer and public benchmark diagnostics. It does not introduce a Letta runtime dependency, does not change the kernel default, and does not rewrite storage beyond the eligibility contract.

## Problem

The current v3 composer calls `store.list_archival_passages()` without request scope and searches all passages. This allows unattached archive passages to pollute context and makes benchmark reports unable to distinguish:

- selected archival evidence;
- eligible archival evidence with no lexical match;
- passages excluded by archive/source/session scope;
- no archival passage retrieved at all.

Phase 4 must make that distinction in the real `MemoryOSService.build_context()` v3 path and in append-only public benchmark diagnostics.

## Contracts

### Archive Attachment Scope

`ArchiveAttachment` remains the durable binding between an archive and an eligibility boundary.

Required supported attachment boundaries:

- `session`
- `agent`
- `run`
- `source`
- `project`
- `user`

Eligibility is resolved from request metadata already available to MemoryOS:

- `ContextComposerRequest.session_id`
- `ContextComposerRequest.identity_scope`
- optional request metadata added narrowly for archive scope, such as agent/run/source IDs when public benchmark or service code can provide them

The composer must resolve eligible archive IDs before searching archival passages. An archive is eligible only if at least one active attachment matches the request scope. Global `list_archival_passages()` may remain for admin/tests, but v3 context composition must not use it as an unscoped retrieval source.

### Passage Scope

`ArchivalPassage` is the retrieval evidence unit. The eligibility contract covers:

- `id`
- `archive_id`
- `source_id`
- `file_id`
- `tags`
- `metadata`
- `created_at`
- `updated_at`
- deletion state if present in the model/store
- `source_refs`
- `citation`

Letta semantics are adopted as MemoryOS-native invariants, not by importing Letta:

- Agent/archive passage: requires `archive_id` and must not set `source_id`.
- Source/file passage: requires `source_id` and must not set `archive_id`.
- A passage with both `archive_id` and `source_id` is invalid for new writes.
- A passage with neither `archive_id` nor `source_id` is invalid for new writes.
- Deleted passages are ineligible for retrieval.

If existing fixtures rely on both `archive_id` and `source_id`, update tests and data setup to use `source_refs` for provenance and keep `source_id` only on source/file passages.

### Store/Search API

Add narrow store-facing helpers rather than a broad manager layer:

- resolve archive eligibility from request scope and `ArchiveAttachment` rows;
- list eligible archival passages for the resolved archive IDs;
- count scope-excluded passages without exposing them as candidates;
- preserve global `list_archival_passages()` only for explicit store/admin/test callers;
- keep `ArchivalPassageSearcher.search()` operating over the already eligible candidate list.

The searcher must return passage-level hits with:

- `passage.id`;
- score and reason;
- citation span;
- `source_refs`;
- `archive_id` or `source_id`/`file_id` metadata;
- tags and timestamps.

### Composer Metadata

`ContextPackageV3.metadata` must include an append-only archival eligibility summary when v3 is active. Required shape:

```python
{
    "archival_eligibility": {
        "scope": {
            "session_id": "ses_1",
            "identity_scope": None,
            "source_ids": [],
            "file_ids": []
        },
        "eligible_archive_ids": ["archive_1"],
        "selected_passage_ids": ["apsg_1"],
        "selected_source_refs": [{"source_type": "message", "source_id": "msg_1"}],
        "eligible_passage_count": 1,
        "selected_passage_count": 1,
        "archival_scope_excluded": 1,
        "archival_no_match": 0,
        "reason_codes": ["attached_scope_match", "archival_scope_excluded"]
    }
}
```

Exact serialization may follow existing Pydantic `model_dump(mode="json")` conventions, but the named keys above must be stable in tests and public reports.

### Diagnostic Events

`ContextPackageV3.diagnostics` must include archival diagnostic events that preserve existing selected-item diagnostics and add scope visibility:

- selected passage: `layer="archival"`, `event_type="select"`, `reason_code` from search hit, `included=True`;
- scope excluded: `layer="archival"`, `event_type="eligibility"`, `reason_code="archival_scope_excluded"`, `included=False`;
- eligible no match: `layer="archival"`, `event_type="eligibility"`, `reason_code="archival_no_match"`, `included=False`;
- no attached archive: `layer="archival"`, `event_type="eligibility"`, `reason_code="archival_no_attached_archive"`, `included=False`.

Diagnostics must include selected passage IDs, eligible archive IDs, excluded counts, selected source refs, and passage-level metadata sufficient to explain retrieval miss vs scope exclusion.

### Public Benchmark Reports

Public benchmark output must expose archival eligibility append-only through existing v3 fields:

- `v3_context`
- `v3_layer_counts`
- `v3_budget_decisions`
- `v3_diagnostics`
- `case_diagnostics`

Scoring and movement fields must remain unchanged:

- `verdict`
- `source_hit`
- `source_hit_at_k`
- `planned_evidence_source_hit_at_5`
- `failure_class`
- `movement_status`

Public diagnostics must not treat core-memory source refs or scope-excluded archival refs as retrieval candidates.

## Data Flow

```text
MemoryOSService.build_context(session_id, task, budget, retrieval_query)
  -> settings.resolved_memory_arch == "v3"
  -> ContextComposerRequest(session_id, task, budget, retrieval_query, identity_scope, archival scope metadata)
  -> V3ContextComposer.build()
  -> _archival_items(request, query)
       -> resolve archive eligibility from ArchiveAttachment rows
       -> list only eligible archival passages
       -> search eligible passages only
       -> record selected / eligible_no_match / scope_excluded / no_attached_archive diagnostics
  -> _context_package_from_v3()
       -> append v3 metadata and diagnostics without changing v1 fields
  -> public_benchmarks._to_public_result()
       -> copies v3 diagnostics into report and case diagnostics append-only
```

## Non-Goals

- Do not add Letta as a runtime dependency.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default or require it for archive retrieval.
- Do not change `MEMORYOS_MEMORY_ARCH=v3` default or remove explicit `MEMORYOS_MEMORY_ARCH=v1`.
- Do not route v1 `ContextBuilder` through v3 archival eligibility.
- Do not add Qdrant or a new production database backend.
- Do not rewrite archival storage broadly; add only helpers/fields required for the scope contract.
- Do not implement broad agent-authored core-memory writes.
- Do not claim benchmark improvement from 5/10 or aggregate-only smoke results.
- Do not use benchmark case IDs, expected answers, or dataset-specific hacks for retrieval.

## Acceptance Criteria

- Real v3 `MemoryOSService.build_context()` searches only eligible archival passages.
- Unattached archive passages cannot appear in selected v3 archival context, even when their lexical score is higher.
- Store/search tests enforce agent/archive vs source/file passage invariants.
- Composer diagnostics expose eligible archive IDs, selected passage IDs, selected source refs, `archival_scope_excluded`, and `archival_no_match`.
- Public benchmark reports include archival eligibility diagnostics append-only and preserve scoring/movement schema.
- Explicit v1 context excludes v3 archival eligibility diagnostics and scoped archival passage text.
- LongMemEval and LoCoMo case-level milestone reports are kept separate.
- Full-chain LLM milestone commands are run, or provider/local-data blockers are recorded and deterministic no-LLM fallback smokes are clearly labeled as non-milestone evidence.
- `uv run pytest -q` and `uv run ruff check .` pass before usable ACK.
- Review confirms no Letta runtime dependency, no kernel default change, no broad storage rewrite, no hidden pass-to-fail cases, and no benchmark leakage.
