# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Scope

This research compares the required Letta reference files against the Phase 6 answer projection/citation boundary. It borrows semantics only. Do not add Letta as a runtime dependency.

Phase 5 already made selected/rendered context auditable through `v3_component_accounting`, `v3_final_context_trace`, token/drop counts, LoCoMo neighbor diagnostics, and public case diagnostics. The remaining Phase 6 gap is that answer generation still crosses the boundary as loose text/source maps: deterministic projection emits uncited answer text, and the LLM answerer receives rendered snippets without a machine-checked citation contract.

## Letta Semantics To Borrow

| Letta reference | Useful semantic | MemoryOS Phase 6 use |
|---|---|---|
| `schemas/block.py`, `schemas/memory.py` | Blocks have durable id/label/value/limit/description/read-only/tags and are rendered as structured sections with metadata. | Treat answer input evidence as structured evidence blocks, not a newline-joined context blob. Each block needs `evidence_id`, `layer/component`, `text`, token estimate, and metadata needed for audit. |
| `schemas/archive.py`, `services/archive_manager.py` | Archives are named identity/scope containers that agents attach to; passage eligibility is scoped. | Do not change retrieval now. Carry existing archive/passage eligibility into answer evidence so citation failures can distinguish "not selected" from "not eligible/retrieved". |
| `schemas/passage.py`, `services/passage_manager.py` | Passage identity is separate from source identity; source passages and agent/archival passages have mutually exclusive invariants. | Citations should point to selected evidence IDs, with source refs derived from that evidence. Evidence IDs may be message IDs for recall, passage IDs for archival, or block IDs for core; source IDs remain provenance, not the citation namespace. |
| `services/block_manager.py` | Memory updates are persisted and prompt/context rebuild semantics matter after mutation. | Not a Phase 6 mutation task. Relevant contract: answer evidence must be generated from the already-built final context ledger, so rebuilt context and citations stay synchronized. |
| `tool_executor/tool_execution_manager.py`, `tool_executor/core_tool_executor.py`, `agents/letta_agent_v3.py` | Tool results are bounded/truncated, persisted with run/step IDs, approval states, and continuation decisions. | Only relevant if kernel/tool trace is rendered as answer evidence. Keep `MEMORYOS_AGENT_KERNEL` default-off. If tool trace appears in context, it needs the same evidence ID/source-ref treatment as any other block; do not introduce a broader kernel loop in Phase 6. |
| `context_window_calculator.py` | Context accounting is per component: system/core/tool/directories/summary/messages/functions, with current/max token totals. | MemoryOS already has the right direction. Build answer evidence from `ContextPackageV3.items` plus `final_context_trace`, preserving `rendered_index`, component, source refs, and token estimates; diagnostics should report dropped/uncited/unsupported evidence separately. |

## Contract Recommended For Phase 6

1. Add an internal structured answer input, e.g. `AnswerEvidence`, built only from selected/rendered context:
   - `evidence_id`: stable selected evidence ID; use `ContextLayerItem.item_id`.
   - `component`: `recall`, `archival`, `core`, `recent`, or `task` if intentionally answerable.
   - `text`: rendered text actually available to the answerer.
   - `source_refs`: existing v3 `SourceRef` payloads.
   - `source_ids`: flattened from `source_refs` for public report compatibility.
   - `rendered_index`, `estimated_tokens`, `metadata`.

2. Make deterministic projected answers return an answer contract before text:
   - `status`: `answered` or `unsupported`.
   - `answer_text`: final answer text.
   - `citations`: selected `evidence_id`s only.
   - `unsupported_reason`: set when no selected evidence or no projected clause survives.
   - The public text can render citations as `[evidence_id]`, but diagnostics should validate the structured contract directly.

3. Make the LLM answerer consume the same structured evidence:
   - Prompt from a JSON-like or XML-like evidence list with explicit `id`, `source_ids`, `component`, optional date/session metadata, and text.
   - Instruct the model to cite only evidence IDs from the list or return an explicit insufficient-evidence refusal.
   - Post-validate citations against selected evidence IDs; map cited evidence IDs back to source IDs for existing `answer_support_status`.

4. Preserve retrieval/context separation:
   - Retrieval miss remains based on candidate/planned evidence.
   - Context missing evidence remains based on selected/rendered/final trace.
   - Unsupported answer becomes: missing citation, citation not selected, citation has no source ref, no-evidence hallucination, or answer failed despite cited rendered evidence.
   - Do not count a dropped diagnostic row as selected evidence.

5. Keep LoCoMo temporal grounding explicit:
   - Answer evidence for LoCoMo should carry session/date metadata already present in recall/final trace.
   - A temporal answer should cite the evidence item(s) containing the date/session grounding, not only a summary clause.

## Focused Implementation Targets

- `src/memoryos_lite/evals.py`: deterministic `_project_answer` currently returns uncited text. Replace or wrap it with structured projection that cites selected evidence IDs or refuses.
- `src/memoryos_lite/public_benchmarks.py`: `PublicAnswerer.answer(question, sources)` currently accepts a loose `dict[source_id, text]`. Add a structured answer path for `memoryos_lite` public eval while preserving legacy compatibility.
- `src/memoryos_lite/agent_answer_eval.py`: citation extraction currently treats bracketed IDs as source IDs. Extend it to validate evidence IDs and expose mapped source refs/source IDs.
- `src/memoryos_lite/public_case_diagnostics.py`: add statuses for `missing_citation`, `unselected_citation`, `no_evidence_refusal`, and `evidence_hit_answer_fail`; keep existing fields append-only.
- Tests should start with the bundle's required RED cases: correct evidence ignored, citation not selected, no-evidence refusal, and temporal LoCoMo date/session citation.

## Non-Goals

- No Letta import, service port, or schema dependency.
- No default kernel enablement.
- No archive/retrieval rewrite unless a failing Phase 6 test proves the answer contract cannot be wired from the current selected context.
- No aggregate-only benchmark claim; Phase 6 milestone reports must list LongMemEval and LoCoMo case movement separately.
