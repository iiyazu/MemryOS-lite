# phase: phase-12

# Phase 12 Brainstorm: Archival/RAG Memory Unification

## Inputs Used

- Required phase context: `work/phase-12/context_bundle.md`.
- Dispatch contract: `work/phase-12/god_dispatch.json`.
- Phase 11 debt context: `work/phase-11/result.md` and `work/phase-11/case_matrix.md`.
- Implementation anchors inspected: `agent_kernel.py`, `store.py`, `context_composer.py`, `engine.py`, `retrieval/archival_searcher.py`, and existing archival/kernel tests.
- Letta reference inspected design-only from local source: archive, passage, archive manager, passage manager, tool execution manager, agent v3, and context window calculator files. This brainstorm borrows semantics only; it does not propose adding Letta as a dependency.

## Current Hypothesis

Phase 12 should prove the real chain:

```text
archive_write / lifecycle write
-> ArchivalMemory
-> bridged ArchivalPassage
-> explicit scoped eligibility
-> V3ContextComposer archival item
-> source refs in final trace and legacy retrieved_evidence
-> history / stale-passage protection
```

The likely gap is not raw storage. Current code already has archival memory records, bridged `apsg_{memory_id}` passages, source-ref requirements, update/delete passage sync, scoped passage eligibility, and v3 archival item selection. The unproven path is tool-mediated write usability: `archive_write` defaults `archive_id` to the session id, but same-session composer eligibility appears to depend on explicit `archive_ids`, `identity_scope.archive_id`, or archive attachments. The existing kernel test proves only that the tool-result message appears in the recent layer, not that the written archival memory becomes a retrievable archival item.

## Letta Semantics To Borrow

Use Letta only as a design reference:

- Archive identity: an archive is a named collection of passages that can be attached to an agent/scope. MemoryOS should keep archive visibility explicit rather than treating all archives as globally searchable.
- Passage invariants: Letta separates agent/archive passages from source passages. Agent/archive passages require `archive_id`; source-origin passages use source/file identity. MemoryOS should preserve the same conceptual split: archival passages are selected by archive scope, while source refs carry provenance.
- Tool-mediated writes: Letta routes tools through execution managers and passage managers rather than letting arbitrary context edits mutate memory. MemoryOS should keep `archive_write` behind policy/approval and reject sourceless archival mutations.
- Passage provenance: Letta passages carry metadata/tags and archive/source associations. MemoryOS should keep `source_refs`, `memory_id`, `archive_id`, `memory_type`, and update history visible enough for diagnostics.
- Context accounting: Letta accounts separate context components such as core memory, memory filesystem, tool rules, directories, and memory metadata. MemoryOS should expose analogous v3 accounting for archival eligibility, selected passage ids, source refs, budget drops, and final trace rows.

## Routes Compared

| Route | Shape | Tradeoffs |
|---|---|---|
| Route A: Minimal Same-Session Bridge | Add one RED kernel test proving `archive_write -> V3ContextComposer.build()` returns an archival item in the same session. If RED fails, minimally make the written session archive eligible, likely through an idempotent session attachment or an exact same-session archive scope rule. | Smallest change and directly targets the suspected gap. Risk: too narrow unless it also proves source refs, selected passage ids, update/delete sync, and no unrelated-session leakage. It may encode `archive_id == session_id` as a hidden convention if not bounded carefully. |
| Route B: Explicit Scoped Archive Bridge | Treat tool-written memory as a real scoped archive write. On approved `archive_write`, preserve source/approval refs, create/update `ArchivalMemory`, bridge to `ArchivalPassage`, and ensure explicit eligibility through a source-grounded scope attachment or equivalent exact-scope mechanism. Add RED tests for same-session retrieval, stale update/delete protection, source projection, and scope non-leakage. | Recommended. It proves the end-to-end path without changing benchmark scoring or enabling the kernel by default. Larger than Route A, but the added surface is the actual contract Phase 12 needs. Main risk is over-attaching explicit archives too broadly; implementation should remain exact-scope and idempotent. |
| Route C: Public Benchmark / Report First | Focus on surfacing archival eligibility and final trace fields in public eval rows, then use no-LLM smoke to show structural visibility. | Useful only if default public v3 context/reporting is touched. Dangerous as the primary route because it can make reports look better without proving tool-write retrieval, and it can blur structural diagnostics with benchmark improvement. Should be deferred unless Route B exposes missing projection/report fields. |

## Recommended Route

Use Route B.

The phase should start with RED evidence in the real path, then make the smallest production change that connects tool writes to scoped archival eligibility. The expected implementation direction is:

1. Add a failing `tests/test_agent_kernel.py` case: after approved `archive_write`, reopen the store, build v3 context for the same session, and assert an `archival` item exists with the written content, `source_refs`, `memory_id` or `archival_memory_id` metadata, and `archival_eligibility.selected_passage_ids == [apsg_{memory_id}]`.
2. If RED confirms missing eligibility, make tool-written archives explicitly eligible for the same session without global leakage. Prefer an idempotent, source-grounded session attachment or exact-scope equivalent over broad implicit archive search.
3. Keep or strengthen update/delete tests so `update_archival_memory()` refreshes `apsg_{memory_id}` and `delete_archival_memory()` removes it from later archival selection.
4. Verify composer/accounting projection: selected archival items must carry source refs into `ContextLayerItem`, `component_accounting` / final trace, and legacy `ContextPackage.retrieved_evidence`.
5. Touch public benchmark reporting only if this work changes the default v3 public context path. If not touched, record `case_level_eval.limit = 0` with a structural-phase rationale.

This preserves:

- `MEMORYOS_MEMORY_ARCH=v3` as the default.
- `MEMORYOS_MEMORY_ARCH=v1` as explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` as opt-in.
- SQLite as the authoritative store.
- Letta as design reference only, not a runtime dependency.

## Required RED Evidence

At least one RED test must fail before production changes, and the output should be recorded in `work/phase-12/red_result.md`.

Required RED set:

- Tool-to-archival-context RED: `archive_write` with approval creates memory, but later same-session `V3ContextComposer.build()` must retrieve the written content as an `archival` item with source refs and selected passage ids. Expected current failure: only the recent tool-result message is visible, or no eligible archive is resolved.
- Stale-passage RED or verification: update/delete through the same archival memory path must update or remove `apsg_{memory_id}` so stale content cannot be selected.
- Scope-leak RED or verification: archive passages attached to one session/source/archive must not appear in unrelated sessions or unattached archives.
- Projection RED only if needed: if `_context_package_from_v3()` or public benchmark context is touched, archival source refs must remain visible in retrieved evidence and diagnostics without changing scoring semantics.

## Risks

- Auto-attaching every explicit archive to the current session could leak shared memory into unrelated contexts.
- Treating `archive_id == session_id` as globally eligible could hide scope bugs.
- Passing tests through recent tool messages would be demo-only and would not prove archival/RAG retrieval.
- Updating context projection could regress final source ids, `retrieved_evidence`, or case diagnostics.
- Budget accounting could report selected passages that were later dropped.
- Structural archive success could be misreported as LongMemEval/LoCoMo improvement.
- Any change that makes the kernel default-on violates the active goal.

## Demo-Only Traps

Do not accept these as Phase 12 completion:

- The tool-result message appears in the recent layer.
- Store helper tests round-trip archival memory without using the real tool/store/passage/retrieval/context chain.
- Kernel traces exist only under `MEMORYOS_AGENT_KERNEL=v1`.
- A no-LLM structural smoke emits archival diagnostics but no case-level answer evidence.
- Final `source_hit` improves without showing retrieved/planned evidence and per-case movement.
- LongMemEval looks clean while LoCoMo regressions or source-miss risks are hidden.

## Phase 11 Debt To Keep Visible

Phase 12 must not claim Phase 11 completion.

Latest Phase 11 gate:

- LongMemEval 30: `30 pass / 0 fail`.
- LoCoMo 30: `20 pass / 10 fail`.
- LoCoMo `pass_to_fail`: `conv-26_qa_028`.
- LoCoMo judged-pass source-miss risk: `conv-26_qa_005`.
- Remaining LoCoMo failures: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`.

Any Phase 12 result/review should state that structural archival tests are not benchmark-quality improvement evidence. If default public benchmark context is untouched, full-chain LongMemEval/LoCoMo eval is not required for Phase 12 promotion and should be marked not applicable rather than inflated into progress.

## What Would Disprove The Hypothesis

The Phase 12 hypothesis is disproven if a focused RED test shows that tool-mediated `archive_write` already produces:

- an `ArchivalMemory`;
- a bridged `ArchivalPassage`;
- same-session scoped eligibility;
- an archival v3 context item;
- source refs in final trace and legacy retrieved evidence;
- stale update/delete protection;

without extra setup or default-kernel changes.

It is also disproven if the missing behavior is only report formatting, or if the necessary fix would require enabling `MEMORYOS_AGENT_KERNEL=v1` by default, adding Letta as a dependency, changing benchmark scoring, or using benchmark case ids / expected answers.

In that case, Phase 12 should switch from implementation to documenting verified capability plus the real remaining blocker, without claiming benchmark improvement.

## Decision

Proceed with Route B: explicit scoped archive bridge, TDD-first, narrow production changes only after RED, and conservative reporting. Treat public benchmark work as conditional, keep Phase 11 LoCoMo debt visible, and preserve v1 fallback, v3 default, and kernel opt-in throughout.
