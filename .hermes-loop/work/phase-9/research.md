# phase: phase-9

## Scope

Context bundle read first and cited here: `.hermes-loop/work/phase-9/context_bundle.md`.

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Compared required Letta reference files for Phase 9 evidence replay semantics only:

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

Do not add Letta as a dependency. The useful layer is field semantics and replay discipline, not runtime structure.

## Findings

### Block And Memory Rendering

Letta block semantics worth borrowing:

- `block_id`, `label`, `description`, `value`, `limit`, `read_only`, `metadata`, and `tags` as the conceptual shape of a renderable memory component (`block.py:18-40`, `block.py:67-77`).
- Render-time component metadata: rendered label, description, `chars_current`, `chars_limit`, and value wrapper (`memory.py:149-173`).
- Component-level render mode: standard blocks, line-numbered display, git/file projection, tool usage rules, and attached directories are separate render sections (`memory.py:122-203`, `memory.py:688-732`).

For MemoryOS Lite replay, borrow this as a smaller rendered-evidence schema:

- `rendered_components[]`: `{component_id, component_type, label, description, source_ids, chars_current, chars_limit, token_count, rendered, rendered_text_hash, rendered_order}`.
- `render_path[]`: source/evidence ids observed at each phase: `indexed -> retrieved -> selected -> rendered`.
- `render_notes`: explicit notes when selected evidence was truncated, dropped, merged, or absent.

Do not port:

- Letta XML prompt rendering, git memory filesystem rendering, block CRUD, template/deployment metadata, block tags junction behavior, or line-number editing semantics.
- Letta's `human`/`persona` core-memory assumptions. Phase 9 replay needs evidence component accounting, not agent identity memory.

### Archive And Passage Source Scope

Letta archive/passage semantics worth borrowing:

- Archive is a named collection with `archive_id`, organization scope, vector provider, embedding config, and metadata (`archive.py:11-28`).
- Passage separates storage identity from origin scope: `passage_id`, `archive_id`, `source_id`, `file_id`, `file_name`, `metadata`, `tags`, `text`, embedding config, and `created_at` (`passage.py:14-47`).
- Passage manager enforces separate agent archival passages and source passages. Agent passages require `archive_id` and reject `source_id`; source passages require `source_id` and reject `archive_id` (`passage_manager.py:134-139`, `passage_manager.py:286-293`).

For MemoryOS Lite replay, borrow the separation as:

- `expected_sources[]`: benchmark-visible source ids from the row.
- `indexed_sources[]`: `{source_id, indexed: bool, index_record_id, episode_id, message_id, page_id, session_id, speaker, timestamp, text_hash}`.
- `retrieved_evidence[]`: `{evidence_id, source_id, episode_id, message_id, page_id, rank, score, search_mode, query_variant, snippet_hash}`.
- `selected_evidence[]`: `{evidence_id, source_id, selection_rank, selection_reason, selected_by}`.
- `rendered_evidence[]`: `{evidence_id, source_id, rendered_component_id, rendered_order, rendered_text_hash}`.

Do not port:

- Letta archive ownership, organization/project permissions, vector provider switching, embedding padding, source/file CRUD, or dual SQL/vector writes.
- Letta's archival-vs-source passage class split as a new MemoryOS data model. Phase 9 only needs replay rows to distinguish benchmark expected source scope from indexed/retrieved/rendered evidence scope.

### Tool And Evidence Provenance

Letta provenance semantics worth borrowing:

- Tool execution has `function_name`, arguments, tool identity, `step_id`, execution status, return value, return truncation, stderr, and timing metrics (`tool_execution_manager.py:94-129`, `tool_execution_manager.py:156-160`).
- Conversation search returns structured results with timestamp, role, content, and optional relevance metadata such as `rrf_score`, `vector_rank`, `fts_rank`, and `search_mode` (`core_tool_executor.py:81-149`, `core_tool_executor.py:224-246`).
- Agent v3 uses durable `run_id`, generated `step_id`, LLM request boundaries, tool call ids, tool args, tool results, stop reasons, and per-step metrics (`letta_agent_v3.py:1037-1040`, `letta_agent_v3.py:1095-1166`, `letta_agent_v3.py:1811-1933`).

For MemoryOS Lite replay, model retrieval/selection/rendering/answering as provenance events even if they are not user-callable tools:

- `provenance_events[]`: `{stage, step_id, run_id, operation, input_hash, output_ids, status, error, duration_ms, params}`.
- `retrieval_event`: query analyzer output, BM25/vector mode if applicable, limits, ranks, scores, and retrieved ids.
- `selection_event`: planner/selector name, selected ids, dropped retrieved ids, and reason codes.
- `render_event`: final prompt/context package evidence ids and component ordering.
- `answer_event`: answer text, cited/source ids, citation support status, refusal flag.
- `judge_event`: judged pass/fail, judge label, judge rationale/summary if available, and report-level failure class.

Do not port:

- Letta tool rules, approval flows, client-side tools, parallel tool execution, heartbeat/loop continuation machinery, run manager, or agent v3 execution loop.
- Phase 9 replay should not introduce a fake "tool" layer that changes benchmark behavior. Treat provenance as diagnostic trace metadata only.

### Context Accounting

Letta context accounting semantics worth borrowing:

- Context overview separates total window size/current usage from per-component counts: system, core memory, memory filesystem, tool usage rules, directories, summary memory, function definitions, messages, archival memory count, and recall memory count (`memory.py:23-65`).
- Context window calculator extracts structured components from rendered system text, handles top-level vs nested tags, identifies summary memory, and counts each component separately before summing (`context_window_calculator.py:167-210`, `context_window_calculator.py:249-380`).
- Agent v3 exposes context token estimate from the actual request path rather than only aggregate prompt usage (`letta_agent_v3.py:421-433`, `letta_agent_v3.py:1248-1251`).

For MemoryOS Lite replay, borrow a compact accounting object:

- `context_accounting`: `{context_window_limit, total_tokens, query_tokens, instruction_tokens, memory_tokens, retrieved_evidence_tokens, selected_evidence_tokens, rendered_evidence_tokens, answer_prompt_tokens, judge_prompt_tokens, rendered_evidence_chars}`.
- `source_metrics`: retrieval/source overlap metrics only, such as expected source hit at retrieved/selected/rendered stages.
- `answer_metrics`: answer/judge outcome only, such as cited source support, unsupported citation, refusal despite evidence, judged pass/fail.

Do not port:

- Letta token-counter implementations, system-prompt parsers, compaction, summary-message detection, OpenAI tool schema counting, or context overflow behavior.
- Phase 9 only needs enough accounting to prove whether expected evidence reached the answer context and whether answer failure is separate from retrieval/source failure.

## Smaller Replay Schema To Borrow

Recommended minimal replay case shape:

```text
case_id
benchmark
report_path
context_bundle_path
active_goal
question
expected_answer
expected_source_ids[]
indexed_sources[]
retrieved_evidence[]
selected_evidence[]
rendered_evidence[]
rendered_components[]
provenance_events[]
answer
cited_source_ids[]
citation_support
judge_result
report_failure_class
path_failure_class
diagnostic_gap
movement_status
source_metrics
answer_metrics
context_accounting
notes
```

Borrow semantically:

- Component labels and render accounting from Letta blocks.
- Passage/source separation: benchmark expected source, indexed raw source, retrieved evidence, selected evidence, rendered evidence.
- Step/run/tool-style provenance as diagnostic events, even when MemoryOS uses internal functions rather than tools.
- Component token/char accounting and strict separation of source metrics from answer/judge metrics.

Do not borrow:

- Letta storage managers, ORM models, archive permissions, vector-provider support, runtime agent loop, tool approval rules, compaction, prompt XML format, or dependency graph.
- Any field that cannot be populated from real MemoryOS report rows or real diagnostic traces without synthetic case-specific assumptions.

## Over-Porting And Demo-Only Signals

Over-porting:

- Adding Letta as a dependency or copying Letta agent/block/archive/passage manager internals.
- Replacing MemoryOS SQLite/page/episode concepts with Letta archive/passage persistence.
- Adding tool execution machinery just to make replay artifacts look Letta-like.
- Introducing context compaction, heartbeat loops, approvals, or kernel default changes during Phase 9.

Demo-only completion:

- Producing only aggregate LongMemEval/LoCoMo scores without one replay row per failed LoCoMo case.
- Filling replay fields with placeholders while omitting `diagnostic_gap=true`.
- Treating final public `source_hit` as proof that retrieved/selected/rendered evidence was present.
- Hiding `conv-26_qa_015` as irrelevant because it passed instead of tracking it as judge/source-support risk.
- Using handcrafted expected-source mappings or case-specific fixes outside the real report/diagnostic path.
- Collapsing session, temporal, speaker/entity, selection, rendering, citation, and judge failures back into generic retrieval misses.

## Conclusion

Phase 9 should borrow Letta's discipline around explicit renderable components, passage/source boundaries, provenance events, and context accounting. It should not port Letta runtime architecture. The replay schema should stay small, report-derived, and strict enough to classify every failed LoCoMo case without changing retrieval, answer behavior, benchmark scoring, or the opt-in status of `MEMORYOS_AGENT_KERNEL=v1`.
