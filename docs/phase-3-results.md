# Phase 3 Results — Answer Accuracy Eval + Structured Memory Agent

## Summary

Phase 3 established an answer accuracy baseline using LLM judge and implemented
a structured Think-Act-Observe agent loop with Letta-style memory lifecycle
actions (memorize/recall/patch/answer_directly/none).

## Results

| Metric | SQLite cosine | Qdrant ANN |
|--------|--------------|------------|
| Hard eval | 1.00/1.00 | 1.00/1.00 |
| LongMemEval source_hit | 46/50 (92%) | 46/50 (92%) |
| LongMemEval answer_accuracy (LLM judge) | 38/50 (76%) | 40/50 (80%) |
| Full pytest | 275 pass | 275 pass |
| fail→pass | — | +2 |
| pass→fail | — | 0 |

## Architecture

```
router → ingest → paging → tool_agent → memory_think → memory_action → memory_observe → build_context → answer/END
       → tool_agent → memory_think → memory_action → memory_observe → build_context → answer/END
```

### New Components

| Component | Location | Role |
|-----------|----------|------|
| `MemoryDecision` | agent_graph.py | Structured output: action + reason_code + query + content + confidence |
| `MemoryObservation` | agent_graph.py | Tool result: success + recalled_item_ids + patched_item_id + error |
| `memory_think_node_fn` | agent_graph.py | Classifies intent into memory lifecycle action |
| `memory_action_node_fn` | agent_graph.py | Deterministic dispatch to memory tools |
| `memory_observe_node_fn` | agent_graph.py | Deterministic summary of action results |

### Graph Trace Events

After wiring, every agent invocation produces these trace events:
- `memory_thought` — action decision with confidence
- `memory_action` — tool execution result
- `memory_observation` — deterministic summary

## Key Design Decisions

1. **Deterministic dispatch** — memory_action_node uses if/elif, not free-form LLM tool choice
2. **No unbounded loop** — patch is max 2 actions (recall + patch), others are single action
3. **Observe is deterministic** — no LLM in observe node; optional LLM sufficiency check deferred
4. **Backward compatible** — existing tool_agent loop preserved, structured nodes inserted after it
5. **answer_directly vs none** — only differ in trace reason_code, not control flow

## Known Limitations

1. **memory_think_node uses fallback "none"** — Without API key, think node always returns
   action="none". Real LLM-backed classification requires DeepSeek API key.
2. **No multi-turn re-think** — Patch is max 2 actions (recall + patch). No iterative
   refinement loop.
3. **Item search is text-match** — memory_action_node uses simple substring matching on
   `store.list_items`, not full BM25/embedding search.
4. **Answer accuracy gap** — 92% source_hit → 76% correct answer. 16pp gap likely due to
   context assembly (page summaries vs raw messages) and LLM answer generation quality.

## Next Phase: Answer Accuracy Optimization

- Wire real LLM (DeepSeek) into memory_think_node for production classification
- Improve context-to-answer projection (raw evidence → better prompting)
- Investigate the 11 failing answer cases (what's in context but LLM gets wrong?)
- Consider Core Memory hot layer for frequently-accessed facts

## Verification

```bash
# Hard eval (must be 1.00/1.00)
uv run memoryos eval run --case-set hard --baseline memoryos_lite

# Full test suite
uv run pytest -q

# Demo agent (deterministic, no API key needed)
uv run memoryos demo agent

# LongMemEval with LLM judge (requires DEEPSEEK_API_KEY)
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge --run-id phase3_verify
```
