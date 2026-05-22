# phase: phase-4

# Context Bundle: Phase 4 Archive And Passage Scope

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Target chain component: retrieval, store, context composer, public eval diagnostics.

Phase 4 must replace the current unscoped archival passage behavior with a Letta-style archive/passage eligibility contract. The real MemoryOS v3 composer and public benchmark path must be able to explain whether an archival passage was selected, eligible-but-not-selected, excluded by scope, or absent from retrieval.

This phase exists now because phase-3 made core memory structured and budgetable, but the latest smoke still shows weak benchmark behavior, especially LoCoMo. The live tree already contains archival documents, chunks, passages, memories, attachments, and a lexical archival searcher from earlier work, but the composer currently calls `store.list_archival_passages()` globally and searches all passages. That is not enough for the active blueprint: unattached archives can pollute context, and retrieval miss vs scope exclusion is not diagnosable.

## Hypothesis

Hypothesis: a small MemoryOS-native archive eligibility layer, modeled after Letta attached archives and passage invariants, can make archival retrieval usable in the real v3/public benchmark path without a broad storage rewrite.

Evidence that would disprove it:

- v3 composer still retrieves passages from unattached archives.
- public benchmark diagnostics cannot distinguish `archival_scope_excluded` from `archival_no_match`.
- LoCoMo case-level failures remain unexplained after a mandatory full-chain run.
- v1 fallback behavior or v3 default behavior changes.
- `MEMORYOS_AGENT_KERNEL=v1` becomes default or is required for normal public eval.

## Scope

In scope:

- Attach archive scope to v3 context requests using session/agent/source/run metadata already available in MemoryOS.
- Add or refine store/search APIs so composer can request eligible archival passages instead of global top-k.
- Add diagnostics for archive attachment eligibility, scope exclusion, selected passage IDs, and passage-level source refs.
- Add RED tests before implementation for unattached archive exclusion, passage-level citation diagnostics, public benchmark append-only diagnostics, and v1 fallback isolation.
- Run focused tests, full pytest, ruff, and the mandatory phase-4 milestone public eval commands unless provider access blocks full-chain LLM judging.

Non-goals:

- Do not rewrite Hermes launcher/reporter/state infrastructure.
- Do not add Letta as a runtime dependency.
- Do not add Qdrant or a new production DB backend.
- Do not implement broad agent-authored core-memory writes in this phase.
- Do not enable the v3 kernel by default.
- Do not claim benchmark improvement from aggregate pass rate or 5/10-case smoke.
- Do not use benchmark case-id hacks or expected-answer leaks.

## Relevant State

- `state.json.current_state`: `EXECUTE`.
- `state.json.current_phase_idx`: `4`.
- `execute_lane.phase`: `phase-4`.
- `execute_lane.state`: `EXECUTE`.
- `plan_lane.phase`: `phase-5`.
- `plan_lane.state`: `PLAN_STORM`.
- `research_lane.phases`: `phase-6`.
- Phase 3 completed with commit `420c727` and usable ACK.
- Phase 4 now has regenerated `brainstorm.md`, `spec.md`, `plan.md`, `plan_final.md`, and `result.md` that cite this context bundle.
- Phase 4 `execute_review.md`, `reviews/codex-review.md`, and `ack.json` still contain older Archival Memory Store evidence and must be regenerated before ACK.

## Active Blueprint Section

Phase 4 purpose:

- Replace global archival top-k behavior with Letta-style archive/passage scope.
- Define archive identity and attachment contract.
- Define passage scope: `archive_id`, `source_id`, `file_id`, tags, metadata, `created_at`, deleted flag.
- Distinguish agent passages from source passages.
- Ensure public benchmark retrieval can explain why a passage was eligible.
- Keep SQLite authoritative; Qdrant remains optional.

Required failing tests:

- Unattached archive passages are not retrieved for an agent/session scope.
- Source passage and agent passage invariants are enforced.
- Archived passage search returns passage-level citations.
- Global top-k pollution is detected.

Mandatory milestone eval:

- LongMemEval 30 full-chain LLM judge.
- LoCoMo 30 full-chain LLM judge or local cap.

Usable ACK gate:

- Benchmark context can show archive/passage eligibility and selected source.
- Retrieval miss vs scope exclusion is diagnosable.
- No broad rewrite of storage beyond what the contract needs.

No promoted blueprint amendment is active for this phase.

## Required MemoryOS Read-First Files

- `.hermes-loop/state.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/work/current_goal.md`
- `.hermes-loop/work/phase-3/ack.json`
- `.hermes-loop/work/phase-3/result.md`
- `.hermes-loop/work/phase-3/reviews/codex-review-phase-3.md`
- `.hermes-loop/work/phase-3/reflect_phase-3.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agentic-memory-roadmap-zh.md`
- `src/memoryos_lite/config.py`
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`
- `tests/test_public_benchmarks.py`

## Required Letta Reference Files

Use these as design references only:

- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

Relevant Letta semantics already observed:

- `Archive` is an identifiable collection of passages and has metadata/provider config.
- `Passage` carries archive/source/file metadata, tags, deleted state, text, embedding config, and creation time.
- `ArchiveManager` attaches archives to agents and lists archives through that attachment join.
- `PassageManager` distinguishes agent archival passages from source passages; agent passages require `archive_id` and must not have `source_id`, while source passages require `source_id` and must not have `archive_id`.

Adopt the semantic contract, not Letta internals.

## Current Implementation Snapshot

Existing phase-4-like code is present but insufficient:

- `ArchivalDocument`, `ArchivalChunk`, `ArchivalPassage`, `ArchivalMemory`, and `ArchiveAttachment` already exist in `v3_contracts.py`.
- Store round-trip and provenance tests already exist in `tests/test_archival_store.py`.
- `ArchivalPassageSearcher` supports text/vector/hybrid modes and filters by archive/source/file/tags/date.
- `V3ContextComposer._archival_items()` currently calls `store.list_archival_passages()` with no scope and searches globally.
- Public benchmark diagnostics expose v3 layers, but do not yet explain archival eligibility/scope exclusion as required by phase 4.

## Current Benchmark Baseline And Case Findings

Phase 2 milestone baseline:

- LongMemEval 30 full-chain LLM judge: 18 pass / 12 fail; retrieval_miss=3; context_missing_evidence=12; unsupported_answer=15.
- LoCoMo 30 full-chain LLM judge: 7 pass / 23 fail; retrieval_miss=11; context_missing_evidence=10; unsupported_answer=9.

Phase 3 no-LLM v3 smoke:

- LongMemEval limit 10: 3/10 projected no-LLM smoke; retrieval_miss=`58bf7951`, `6ade9755`; context_missing_evidence=`e47becba`, `118b2229`, `58ef2f1c`; evidence_hit_answer_fail=`51a45a95`, `f8c5f88b`.
- LoCoMo limit 10: 0/10 projected no-LLM smoke; retrieval_miss=`conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`; context_missing_evidence=`conv-26_qa_009`; evidence_hit_answer_fail=`conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`.
- All movement status was `new_case_no_baseline`; do not claim fail-to-pass or pass-to-fail movement from phase-3 smoke.

## Known Pass-To-Fail Risks

- Global archival passage retrieval can introduce distractor evidence and regress source grounding.
- Archive scope filtering can accidentally exclude all archival passages if no default benchmark scope is defined.
- Core-memory source refs must not pollute retrieval/source-hit metrics.
- v1 fallback must not receive v3 archival diagnostics.
- LoCoMo temporal/session evidence can be harder than LongMemEval; do not promote a LongMemEval-only gain.
- Existing phase-4 artifacts were created before this context bundle; stale plan text may over-scope storage rewrites.

## RED Starting Points

Write failing tests before production changes:

- `tests/test_context_composer.py`: v3 composer excludes passages from archives not attached to the request/session/agent scope.
- `tests/test_context_composer.py`: v3 composer diagnostics include selected archival passage IDs and scope exclusion counts/reasons.
- `tests/test_public_benchmarks.py`: public benchmark result keeps append-only v3 archival eligibility diagnostics without changing scoring fields.
- `tests/test_engine.py`: explicit `MEMORYOS_MEMORY_ARCH=v1` context excludes v3 archival eligibility diagnostics.
- `tests/test_archival_store.py` or `tests/test_archival_searcher.py`: agent passage/source passage invariants or attachment scope helper behavior, only if existing coverage is insufficient.

Concrete benchmark cases to keep visible:

- LongMemEval retrieval misses: `58bf7951`, `6ade9755`.
- LoCoMo retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`.
- LoCoMo evidence-hit-answer-fail: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`.

## Expected Verification Commands

Focused RED/GREEN commands:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope -q
uv run pytest tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only -q
uv run pytest tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Focused suite:

```bash
uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q
```

Required baseline checks:

```bash
uv run pytest -q
uv run ruff check .
```

Mandatory milestone eval:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30
```

If LLM provider access is unavailable, record the blocker, run deterministic no-LLM fallback smokes, and do not mark the full-chain milestone as satisfied.

## Anti-Demo Completion Criteria

Phase 4 reaches usable ACK only if:

- real v3 `build_context()` uses scoped archival eligibility;
- public benchmark reports include case-level archival eligibility diagnostics;
- tests prove unattached archives cannot pollute context;
- retrieval miss vs scope exclusion is distinguishable;
- LongMemEval and LoCoMo case-level results are separated;
- no pass-to-fail case is hidden;
- v1 fallback remains explicit and unchanged;
- v3 remains default;
- kernel remains opt-in/default-off;
- review checks stale artifacts, source grounding, LoCoMo risks, and benchmark overfitting.
