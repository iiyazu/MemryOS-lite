# phase: phase-12

# Phase 12 Context Bundle

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase: `phase-12`.

Name: Archival/RAG Memory Unification.

Target state: `archival-rag-usable`.

Target chain components:

- ingest: not applicable unless a RED test proves message-source archival promotion needs ingest metadata;
- store: changed or verified for archival memory, passage bridge, attachment scope, history, and stale-passage deletion;
- retrieval: changed or verified for scoped archival passage eligibility and lexical/vector-fallback selection;
- context composer: changed or verified for archival layer inclusion, source refs, final trace, and component accounting;
- answer projection: verified if archival items enter public report answer evidence;
- kernel loop: changed or verified only through opt-in `MEMORYOS_AGENT_KERNEL=v1` structural tests;
- public eval: verified by structural no-LLM smoke unless code changes affect default v3 public benchmark context.

## Why This Phase Exists Now

`state.json` now points to `phase-12` in `GOD_DISPATCH` after an orphan EXECUTE guard. Phase 11 remains unfinished debt and must not be ACKed retroactively. The latest Phase 11 full-chain gate made LongMemEval clean, but LoCoMo still carries source-grounding and answer-use blockers, especially:

- `conv-26_qa_028`: LoCoMo `pass_to_fail`, `evidence_hit_answer_fail`;
- `conv-26_qa_005`: judge pass with `source_hit=false`;
- unchanged LoCoMo failures: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`.

Phase 12 must not hide that debt. Its own narrow target is the archival/RAG loop from write to passage retrieval. Current code already has pieces of that loop, but the controller should prove the complete default-safe path instead of treating independent store helpers or demo kernel traces as usable completion.

## Current Hypothesis

Archival memory has enough schema and storage support to become a usable long-term RAG layer, but the end-to-end contract is not yet proven for tool-mediated writes:

```text
agent/tool/user source
-> ArchivalMemory
-> ArchivalPassage bridge
-> scoped retrieval eligibility
-> v3 archival context item
-> source-attributed answer evidence
-> history/provenance
```

The likely first RED is that `archive_write` creates an `ArchivalMemory` and bridged passage, but a later same-session `V3ContextComposer.build()` does not retrieve it as an archival item unless an attachment or explicit archive scope exists. The existing kernel test only proves that the tool-result message is visible in the recent layer; that is not the archival/RAG loop.

Disconfirming evidence:

- a focused RED test shows direct `archive_write -> archival passage -> same-session v3 archival item` already works with source refs and no extra setup;
- archival updates/deletes are already fully covered for the exact tool-write path, including stale passage removal;
- the only missing behavior is phase-local reporting, not real store/retrieval/context wiring;
- any proposed fix requires enabling the v3 kernel by default, adding Letta as a dependency, or changing benchmark scoring semantics.

## Scope

Allowed:

- add focused RED tests for direct tool-mediated archival writes becoming retrievable v3 archival evidence;
- verify or change `SimpleToolExecutionManager._archive_write`, `MemoryStore.add_archival_memory`, `_upsert_archival_passage_for_memory`, `list_archival_passages_for_scope`, `V3ContextComposer._archival_items`, and `_context_package_from_v3`;
- add append-only diagnostics for archival eligibility, selected passage ids, source refs, memory id, and stale update/delete history if tests prove gaps;
- add or verify a no-LLM structural smoke that uses the real service/composer path rather than a sidecar analyzer;
- keep Phase 11 LoCoMo debt visible in result/review artifacts.

Non-goals:

- do not mark Phase 11 complete or write `work/phase-11/ack.json`;
- do not retune broad recall or answer prompting for LoCoMo;
- do not change judge or benchmark scoring semantics;
- do not add case-id, expected-answer, or expected-source hacks;
- do not enable `MEMORYOS_AGENT_KERNEL=v1` by default;
- do not add Letta as a runtime dependency;
- do not claim benchmark improvement from structural archive tests.

## State Snapshot

From `.hermes-loop/state.json` at startup:

- `current_state`: `GOD_DISPATCH`;
- `current_phase_idx`: `12`;
- `execute_lane.phase`: `phase-12`;
- `execute_lane.state`: `GOD_DISPATCH`;
- `plan_lane.phase`: `phase-13`;
- `plan_lane.state`: `PLAN_STORM`;
- `phase-11.status`: `in_progress`;
- `phase-12.status`: `in_progress`;
- `last_updated`: `2026-05-23T11:40:06Z`.

Because `current_state` is `GOD_DISPATCH`, God may generate or refresh only phase-local context and dispatch artifacts in this startup pass. Do not run tests, evals, `uv`, `pytest`, `ruff`, or implementation commands until dispatch and plan artifacts exist.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` as the active blueprint. Relevant sections:

- `Current Baseline And Phase 8 Evidence`;
- `Hard Constraints`;
- `Context Bundle Requirement`;
- `Full-Chain LLM Judge Gates`;
- `Phase 11 - Evidence Handoff And Context Selection`;
- `Phase 12 - Archival/RAG Memory Unification`;
- `Phase 13 - Core Memory Lifecycle`.

Promoted amendment source:

- `.hermes-loop/work/phase-8/blueprint_amendment.md`;
- `.hermes-loop/work/phase-8/blueprint_promotion.md`.

The Phase 8 amendment is already promoted into the root blueprint. It remains useful as the rationale for the targeted LoCoMo reliability loop and the rule that LoCoMo debt must not be hidden by LongMemEval.

## Required Read-First Files

MemoryOS control and evidence:

- `.hermes-loop/work/phase-12/context_bundle.md`;
- `.hermes-loop/work/phase-12/god_dispatch.json`;
- `.hermes-loop/work/phase-12/interrupted_orphan_execute.md`;
- `.hermes-loop/work/phase-11/result.md`;
- `.hermes-loop/work/phase-11/case_matrix.md`;
- `.hermes-loop/work/phase-11/execute_review.md`;
- `.hermes-loop/work/phase-11/review_verdict.json`;
- `.hermes-loop/work/phase-10/ack.json`;
- `.hermes-loop/work/phase-10/case_matrix.md`;
- `docs/known-issues.md`;
- `docs/public-benchmark-diagnosis.md`;
- `docs/agentic-memory-roadmap-zh.md`.

MemoryOS implementation:

- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/store.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/engine.py`;
- `src/memoryos_lite/retrieval/archival_searcher.py`;
- `src/memoryos_lite/memory_lifecycle.py`;
- `src/memoryos_lite/v3_contracts.py`;
- `src/memoryos_lite/public_benchmarks.py`;
- `src/memoryos_lite/public_case_diagnostics.py`;
- `tests/test_agent_kernel.py`;
- `tests/test_archival_store.py`;
- `tests/test_memory_lifecycle.py`;
- `tests/test_context_composer.py`;
- `tests/test_public_benchmarks.py`.

Letta reference files, design-only:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`;
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`;
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`;
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`.

Borrow only structure and semantics: archive identity, attached archive scope, source vs agent passage invariants, passage provenance, memory tool write constraints, and component accounting. Do not port Letta internals blindly.

## Current Implementation Snapshot

Observed anchors:

- `SimpleToolExecutionManager._archive_write()` writes `ArchivalMemory`, requires source refs or approval id, defaults `archive_id` to the session id, and returns `memory_id` plus `archive_id`;
- `MemoryStore.add_archival_memory()` requires source refs, appends history, and calls `_upsert_archival_passage_for_memory()`;
- `MemoryStore.update_archival_memory()` upserts the bridged passage with new content; `delete_archival_memory()` deletes the bridged passage;
- `_archival_passage_from_memory()` creates `apsg_{memory_id}` with source refs, `archival_memory_id`, `memory_type`, and `memory_updated_at`;
- `list_archival_passages_for_scope()` only selects archive passages from explicit `archive_ids`, `identity_scope.archive_id`, or attached archives for session/user/agent/run/project/source scopes;
- `V3ContextComposer._archival_items()` searches eligible passages and emits `archival_eligibility`;
- `_context_package_from_v3()` projects archival items into legacy `retrieved_evidence` using message source refs when present;
- `tests/test_memory_lifecycle.py` already covers recall-candidate archival retrieval and update/delete passage sync;
- `tests/test_agent_kernel.py` currently verifies the opt-in tool-result message appears in recent v3 context, but not that the written memory becomes an archival context item.

## Baseline And Case-Level Evidence

Accepted Phase 8 milestone baseline:

- LongMemEval 50 full-chain LLM judge: `47 pass / 3 fail`;
- LoCoMo 50 full-chain LLM judge: `30 pass / 20 fail`;
- invalid heartbeat/projected Phase 8 retry artifacts must not be used for promotion.

Accepted Phase 10 milestone baseline:

- LongMemEval 30 full-chain LLM judge: `29 pass / 1 fail`;
- LoCoMo 30 full-chain LLM judge: `20 pass / 10 fail`;
- fail-to-pass: `conv-26_qa_011`, `conv-26_qa_012`;
- pass-to-fail: none.

Latest Phase 11 gate, not ACK-grade:

- LongMemEval 30: `30 pass / 0 fail`;
- LoCoMo 30: `20 pass / 10 fail`;
- LoCoMo fail-to-pass: `conv-26_qa_027`;
- LoCoMo pass-to-fail: `conv-26_qa_028`;
- source-miss judged-pass risk: `conv-26_qa_005`;
- all 60 rows used `memory_arch=v3`;
- default kernel traces stayed empty.

Use this as regression context only. Phase 12 archival structural tests are not benchmark-quality improvement evidence by themselves.

## Pass-To-Fail Risks

- auto-attaching archives too broadly can pollute default v3 context and hide retrieval failures;
- treating `archive_id == session_id` as globally eligible can leak session-local memory into unrelated scopes if not bounded;
- changing `list_archival_passages_for_scope()` can alter public benchmark context when archive data exists;
- changing `_context_package_from_v3()` can regress source ids, final trace, or answer evidence diagnostics;
- using opt-in kernel structural success as default benchmark evidence violates the active goal.

## Required RED Evidence Before Implementation

At least one RED test must fail before production code changes. Preferred RED tests:

1. In `tests/test_agent_kernel.py`, after approved `archive_write`, a later `V3ContextComposer.build()` for the same session and task retrieves the written content as an `archival` item with `source_refs`, `memory_id`, `archival_eligibility.selected_passage_ids`, and no kernel default change. Expected current failure: only the recent tool-result message is visible, or no eligible archive is resolved.
2. In `tests/test_memory_lifecycle.py` or `tests/test_archival_store.py`, update/delete through the same tool-written memory path updates or removes `apsg_{memory_id}` so stale archival evidence cannot be selected.
3. In `tests/test_context_composer.py`, scoped retrieval proves attached archive passages remain bounded to explicit session/source/archive scopes and do not leak into unrelated sessions.
4. In `tests/test_public_benchmarks.py`, only if archival changes affect public reports, a v3 no-LLM row exposes archival eligibility/final trace without claiming answer-quality improvement.

Record RED output in `work/phase-12/red_result.md`.

## Expected Smoke And Verification Commands

Focused tests after GREEN:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_archival_store.py tests/test_memory_lifecycle.py tests/test_context_composer.py -q
uv run ruff check .
```

Baseline checks before review:

```bash
uv run pytest -q
uv run ruff check .
```

Structural no-LLM public smoke, only if the default v3 public context path is touched:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

Run LongMemEval 30 and LoCoMo 30 full-chain LLM judge in parallel only if Phase 12 changes affect default public benchmark context behavior. Otherwise record `case_level_eval.limit = 0` and explain why full-chain milestone eval is not applicable to this structural archival phase.

## Anti-Demo Completion Criteria

Phase 12 is usable only if:

- the real tool/store/passage/retrieval/context chain is exercised, not just helper methods;
- at least one RED test fails before production changes;
- archival writes require source refs or approval-derived refs;
- written archival memory becomes scoped archival evidence in v3 context when eligible;
- update/delete history prevents stale bridged passages from being selected;
- source refs survive into `ContextLayerItem`, final trace, and legacy `ContextPackage.retrieved_evidence`;
- remaining LoCoMo Phase 11 debt is still listed in result/review artifacts;
- v1 fallback, v3 default, and kernel opt-in constraints remain unchanged;
- review lane returns PASS or usable ACK before any ACK.

Completion level below `usable` must not advance.

## Constraints To Preserve

- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_MEMORY_ARCH=v1` remains explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and must not become default.
- SQLite remains the authoritative current store.
- Qdrant/vector paths remain optional experiments.
- No separate production database backend is introduced.
- Benchmark language stays conservative and case-level.

## Refresh Record

- refreshed_by: God controller startup pass;
- refreshed_at: `2026-05-23T12:21:39Z`;
- current_goal_file: `.hermes-loop/work/current_goal.md` confirmed;
- current_state: `GOD_DISPATCH`, dispatch/context refresh only.
