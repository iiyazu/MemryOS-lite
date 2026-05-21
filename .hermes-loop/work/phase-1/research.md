# phase: phase-1

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Files Actually Read

Phase and baseline artifacts:

- `.hermes-loop/work/phase-1/context_bundle.md`
- `.hermes-loop/work/phase-1/god_dispatch.json`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/state.json`
- `.hermes-loop/work/phase-0/baseline_case_matrix.md`
- `.hermes-loop/work/phase-0/reflect_phase-0.md`

Letta reference files:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/archive.py`
- `/home/iiyatu/projects/python/letta/letta/schemas/passage.py`
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/archive_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/passage_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/tool_execution_manager.py`
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`

MemoryOS current files:

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/schemas.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/memory_lifecycle.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/tools.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/config.py`

Tests and docs:

- `tests/test_v3_contracts.py`
- `tests/test_core_memory_service.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`
- `tests/test_context_composer.py`
- `tests/test_public_benchmarks.py`
- `tests/test_agent_kernel.py`
- `docs/memory-v3-architecture.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

Prior-memory guardrails consulted:

- `/home/iiyatu/.codex/memories/MEMORY.md`

## Letta Semantic Observations

- Letta `Block` is a bounded, labeled, metadata-bearing core-memory unit. Relevant fields include `label`, `value`, `limit`, `description`, `read_only`, tags, template/project metadata, and hidden state. `Memory.compile()` renders blocks with description, character counts, limits, read-only metadata, and structured tags, so core memory is not just arbitrary text.
- Letta block mutation is manager/tool mediated. `BlockManager` owns CRUD and agent/block relationships; core memory tools check read-only state, require exact/unique replacement for string edits, reject rendered line-number artifacts, update persisted memory, and rebuild the system prompt after changes.
- Letta `Archive` is an identity and provider boundary. It has name, description, organization, vector DB provider, embedding config, metadata, and attachment operations. `ArchiveManager` attaches/detaches agents, creates or retrieves a default archive for an agent, and uses the archive relationship to scope passage visibility.
- Letta `Passage` is a precise retrieval/citation unit. It carries text, embedding metadata, archive/source/file identity, tags, metadata, deletion state, and created time. `PassageManager` explicitly separates agent archival passages from source passages and rejects mixed `archive_id`/`source_id` modes.
- Letta archival tools expose both search and write semantics. `archival_memory_search` searches through agent archival memory with query, tag, and time filters; `archival_memory_insert` writes through `PassageManager.insert_passage()` and rebuilds the system prompt.
- Letta tool execution is routed through a typed executor factory keyed by tool type. `ToolExecutionManager` centralizes async execution, state-changing executors, return truncation, execution counters, and error packaging. Core memory and archival memory are not ad hoc LangChain helper functions.
- LettaAgentV3 is a real loop, not only a trace shim. It builds requests, handles approval-required tools, executes allowed tools, supports client-side tool returns, persists tool messages, decides continuation from tool rules, retries compaction on context-window overflow, and stores stop reasons.
- Letta context-window accounting extracts named system components (`system_prompt`, `core_memory`, `memory_filesystem`, `tool_usage_rules`, `directories`, `external_memory_summary`, `summary_memory`, messages, and function definitions) and counts each component separately. This provides a budget/audit surface beyond aggregate item counts.

## MemoryOS Current Behavior Observations

- MemoryOS already defines v3 contracts for `CoreMemoryBlock`, `ArchivalDocument`, `ArchivalChunk`, `ArchivalPassage`, `ArchivalMemory`, `ArchiveAttachment`, `ContextPackageV3`, diagnostics, tool policy, approvals, and kernel traces in `v3_contracts.py`.
- `CoreMemoryService` enforces source-backed or approved writes, actor/reason presence, token limits, append/replace/update/delete operations, and history events. It does not currently model Letta's `read_only` block flag or exact rendered XML-style metadata; rendering is compact `[Core Memory]` text.
- SQLite store has first-class tables/records for core blocks/history, archival documents/chunks/passages/memories/history, and archive attachments. Writes for archival documents/chunks/passages/memories require source refs. Attachment records can be created and listed by scope, but the v3 composer currently does not appear to use attachments to constrain archival search.
- `ArchivalPassageSearcher` returns passage-level hits with `citation`, `source_refs`, archive/source/file/tags metadata, and lexical BM25 ranking. Vector and hybrid modes currently report `vector_unavailable` lexical fallback.
- `V3ContextComposer` assembles layers in order: task, core, recall, archival, recent. It records layer budget decisions and diagnostics. Its archival layer currently calls `store.list_archival_passages()` without an archive/scope filter, then searches top-k globally.
- `RecallPipeline` builds raw-message evidence from episodes, query analysis, BM25/overlap ranking, neighbor expansion, planned evidence IDs, and budget-drop diagnostics. This maps well to Phase 0's retrieval/evidence taxonomy.
- Public benchmark reports separate several diagnostics: final/projected `source_hit`, message-level `episode_source_hit_at_10`, `planned_evidence_source_hit_at_5`, v3 layer counts, v3 budget decisions, v3 diagnostics, and opt-in kernel trace events.
- `PublicAnswerer` answers with retrieved context only and can refuse insufficient context, but current deterministic no-LLM smoke still uses substring projection. There is no strict answer-citation contract that forces selected evidence IDs into the answer output.
- `SimpleAgentStepRunner` persists trace events and supports a minimal approval-pause/resume path for `archive_write`. The implemented tool manager only supports `archive_write`; no real LLM request/response, multi-tool loop, continuation controller, compaction, or core-memory mutation tool is wired here.
- `tools.py` still exposes older page/item LangChain tools (`write_page`, `patch_page`, `memorize_item`, etc.). These do not share the v3 kernel's source-backed approval/tool trace contract.
- Potential implementation-contract mismatch to check: `Settings.resolved_memory_arch` defaults to `v3`, but `MemoryOSService._should_route_to_v3_context()` also requires `"memoryos_memory_arch" in settings.model_fields_set`. Existing tests cover explicit `memoryos_memory_arch="v3"` service routing and default setting resolution separately. Execute lane should verify whether the real CLI/settings path always sets the field before treating v3 routing as default.

## Benchmark-Impact Notes - LongMemEval

Phase 0 taxonomy:

- Pass: `1e043500`.
- Retrieval miss: `58bf7951`.
- Evidence hit but answer fail: `e47becba`, `118b2229`, `51a45a95`.

Impact observations:

- The visible LongMemEval weakness is mostly not first-hop evidence discovery in the 5-case smoke. Three failing cases had episode/planned evidence hits but still missed expected answer facts.
- Letta's strongest directly relevant semantics for these cases are selected-evidence survival, passage/source citation granularity, answer projection constraints, and component-level context accounting. A broad kernel loop is less directly justified by the Phase 0 LongMemEval taxonomy.
- MemoryOS already records `planned_evidence_message_ids`, `v3_context`, and `v3_diagnostics`; the gap is that answer generation/projection is not contractually tied to selected evidence IDs, citations, or unsupported-answer behavior.
- Candidate future RED cases should include `e47becba`, `118b2229`, and `51a45a95` as evidence-hit-answer-fail guards: evidence reached planned/v3 context, but the projected answer missed `Business Administration`, `45 minutes each way`, or `Target`.
- `58bf7951` should remain a separate retrieval-miss guard and should not be hidden inside answer-projection work.

## Benchmark-Impact Notes - LoCoMo

Phase 0 taxonomy:

- Evidence hit but answer fail: `conv-26_qa_001`.
- Retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

Impact observations:

- The visible LoCoMo weakness is mostly retrieval/evidence discovery in the 5-case smoke. Four failures did not recover expected evidence through episode/planned paths.
- Letta's strongest directly relevant semantics are archive attachment/scope, passage-level source/file metadata, temporal filters, source-vs-agent passage separation, and diagnostics that explain whether an expected source was unindexed, filtered out, globally polluted, or budget-dropped.
- MemoryOS has `ArchiveAttachment` and passage filters, but current v3 composer archival search does not appear to derive candidate archive IDs from session/agent/project attachments. This risks global top-k pollution once archival passages are populated.
- `conv-26_qa_001` should be handled like the LongMemEval evidence-hit-answer-fail cases: evidence/source overlap exists, but answer projection missed `7 May 2023`.
- `conv-26_qa_002` through `conv-26_qa_005` should drive retrieval/scope contracts first: expected source absent from episode/planned evidence, so answer-only changes would not address the sampled failure mode.

## Candidate High-Priority Gaps

1. Archive attachment not enforced in v3 archival retrieval.
   - Evidence: MemoryOS stores `ArchiveAttachment` and `ArchivalPassage.archive_id`, and `ArchivalPassageSearcher.search()` accepts `archive_id`; `V3ContextComposer._archival_items()` currently lists all passages and searches without attachment-derived scope.
   - Benchmark risk: LoCoMo retrieval misses can remain or worsen due to global top-k pollution.
   - Future RED anchor: `conv-26_qa_002` through `conv-26_qa_005`; add a synthetic test with two archives where only an attached archive may contribute evidence.

2. Passage/source role separation is weaker than Letta's agent-vs-source passage invariant.
   - Evidence: MemoryOS `ArchivalPassage` can carry both `archive_id` and `source_id`; Letta's `PassageManager` rejects agent passages with `source_id` and source passages with `archive_id`.
   - Benchmark risk: source evidence and agent-generated memory can blur, making `source_hit` and citation claims harder to audit.
   - Future RED anchor: require passage eligibility diagnostics to distinguish source-grounded passages from agent-written archival memories.

3. Answer projection is not contractually citation-bound.
   - Evidence: `PublicAnswerer` receives `[source_id]` context, but there is no schema-level answer object requiring cited selected evidence IDs, no unsupported-answer flag, and deterministic smoke still reports substring projection.
   - Benchmark risk: LongMemEval evidence-hit-answer-fail cases remain hidden behind "retrieval succeeded" diagnostics.
   - Future RED anchor: `e47becba`, `118b2229`, `51a45a95`, and `conv-26_qa_001`.

4. Component-level context accounting is present as layer decisions, but not Letta-style token accounting for rendered components.
   - Evidence: MemoryOS records layer item counts and budget decisions; Letta calculates token usage for system prompt, core memory, directories, summaries, messages, and tool definitions separately.
   - Benchmark risk: evidence may be present in `v3_context` but not visible in the actual answer prompt, or core/archival/recent layers may crowd each other without enough component audit.
   - Future RED anchor: tests that compare selected evidence IDs against the answer prompt/source map, not only `v3_context.items`.

5. Kernel/tool mutation is traceable but still minimal.
   - Evidence: MemoryOS kernel trace supports approval and `archive_write`; Letta supports richer tool routing, core-memory writes, client-tool approvals/returns, continuation, and compaction.
   - Benchmark risk: not a primary Phase 0 public-smoke bottleneck, but any future memory mutation should not bypass source refs, approval, and trace events.
   - Future RED anchor: tests for core-memory mutation through the kernel remaining opt-in and requiring source refs or approved approval state.

6. v3 default routing should be verified against the actual CLI/public benchmark path.
   - Evidence: docs and `Settings` say v3 default; `MemoryOSService._should_route_to_v3_context()` appears to require the field to be explicitly set.
   - Benchmark risk: later phases may believe they are testing default v3 while only explicit env/config paths route to v3.
   - Future RED anchor: a service/public benchmark test that constructs default settings the same way as the CLI and asserts v3 diagnostics appear without explicitly setting `memoryos_memory_arch`.

## Explicit Non-Recommendations

- Do not add Letta as a runtime dependency. The useful work is contract mapping and selective semantics, not importing Letta managers or agent runtime.
- Do not port Letta's full AgentV3 loop wholesale. MemoryOS currently needs benchmark-usable retrieval, evidence, answer, and diagnostics contracts before a full production-like loop.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default. Phase 0 kernel evidence is trace-presence only and does not prove answer-quality improvement.
- Do not treat `source_hit` as pure evidence localization. Prefer episode/planned evidence metrics and v3 diagnostics when classifying retrieval vs answer failures.
- Do not collapse LongMemEval and LoCoMo into one aggregate priority. LongMemEval sampled failures mostly pressure answer/evidence-use contracts; LoCoMo sampled failures mostly pressure retrieval/scope contracts.
- Do not use benchmark case IDs, expected-answer leaks, or dataset-specific string rules to repair failures.
- Do not make prompt-only answer changes look like architecture progress unless the contract records selected evidence IDs, unsupported-answer behavior, and case-level pass/fail movement.
- Do not make archival retrieval global by default once archives/passages are populated; attached scope should be explicit or diagnosably absent.

## Open Questions For Execute Lane

- Should `letta_gap_matrix.md` treat archive attachment enforcement as the top LoCoMo retrieval/scope contract, given current `V3ContextComposer._archival_items()` does not use attachment scope?
- Should Phase 1 define a strict invariant that `ArchivalPassage` is either source passage or agent/archive passage, but not both, or is MemoryOS intentionally using a unified passage model with explicit `producer`/metadata instead?
- What exact answer-citation contract should later RED tests require: cited selected evidence IDs in the answer object, source IDs in public reports, refusal when selected evidence is empty, or all three?
- Should context accounting stay layer-based for Phase 2, or should it add Letta-style rendered-component accounting before answer-projection work?
- Should kernel contracts remain limited to `archive_write` for now, or should Phase 1 reserve future RED tests for source-backed `core_memory_append` / `core_memory_replace` through the opt-in kernel?
- Does the CLI/public benchmark default path actually set `memoryos_memory_arch` explicitly, or does `_should_route_to_v3_context()` make default-v3 dependent on caller construction?
- For LoCoMo, should temporal/session query tags from `QueryAnalyzer` be part of the archive/passage scope contract, or remain recall-only until a later retrieval phase?
