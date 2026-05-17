# Phase 3: Answer Accuracy Eval + Structured Memory Agent

## Context

Phase 2.6 achieved 92% source_hit on LongMemEval through infrastructure fixes.
Phase 3 validates whether correct retrieval translates to correct answers, and
introduces a structured Think-Act-Observe agent loop with Letta-style memory
lifecycle actions (memorize/recall/patch).

## Success Criteria

| Level | Metric | Target |
|-------|--------|--------|
| Gate | hard eval | 1.00/1.00 |
| Gate | LongMemEval source_hit | >= 92% (no regression) |
| Primary | LongMemEval answer_accuracy (LLM judge) | Measure baseline |
| Demo | 5-10 deterministic cases | Agent correctly memorizes/recalls/patches |

## Iteration 1: Answer Accuracy Eval (LLM Judge)

### LLMAnswerer

Given query + context sources, generate an answer using DeepSeek.

```python
class LLMAnswerer:
    def answer(self, question: str, sources: dict[str, str]) -> str
```

### LLMJudge

Given question + expected_answer + system_answer, judge correctness.

```python
class JudgeVerdict(BaseModel):
    verdict: Literal["correct", "partial", "wrong"]
    reasoning: str

class LLMJudge:
    def judge(self, question: str, expected: str, answer: str) -> JudgeVerdict
```

### CLI Integration

```bash
memoryos eval public --benchmark longmemeval \
  --answerer deepseek --judge deepseek \
  --limit 50 --run-id phase3_answer_eval
```

### Output

New fields in PublicBenchmarkResult:
- `answer_accuracy: str` — correct / partial / wrong
- `answer_reasoning: str` — judge explanation

## Iteration 2: Structured Memory Think-Act-Observe Agent

### Architecture

```
router → optional ingest/page → memory_think_node → memory_action_node
       → memory_observe_node → build_context_node → answer/END
```

### memory_think_node

LLM structured output (or scripted fallback for tests).
Outputs `MemoryDecision`:

```python
class MemoryDecision(TypedDict):
    action: Literal["memorize", "recall", "patch", "answer_directly", "none"]
    reason_code: Literal[
        "durable_fact", "memory_question", "correction",
        "sufficient_context", "irrelevant",
    ]
    query: str
    content: str
    confidence: float
```

### memory_action_node

Deterministic dispatch. Only executes memory tools. Does NOT build context.

- `memorize` → `memorize_item`
- `recall` → `recall_items`
- `patch` → `recall_items(query)` → select first item → `patch_item(item_id, content)`
- `answer_directly` / `none` → skip

Patch selection rule: select first recalled item. If no item found:
`success=false, error="no item found to patch"`.

### memory_observe_node

Deterministic by default. Parses tool outputs, emits `MemoryObservation`:

```python
class MemoryObservation(TypedDict):
    success: bool
    recalled_item_ids: list[str]
    patched_item_id: str | None
    error: str | None
```

Optional LLM sufficiency check only in real LLM mode, not required for demo.

### build_context_node

Runs after observe for ALL paths (including answer_directly/none).
Unified context assembly point. Separated from memory_action_node.

### Loop Constraints

- No unbounded loop.
- `patch` may perform two tool actions (recall + patch). All others: single.
- `answer_directly` and `none` only differ in trace reason_code, not control flow.
- `agent_max_tool_turns` remains safety guard.

### MemoryDecision Location

Initially in `agent_graph.py`. Move to `schemas.py` only if CLI/eval needs it.

## Iteration 3: Demo Eval Cases

5-10 deterministic cases covering memory lifecycle:

1. User states fact → agent memorizes → recall confirms
2. User asks question → agent recalls → correct answer
3. User corrects prior fact → agent patches → recall returns updated value
4. Irrelevant input → agent decides `none` → no memory action
5. Multi-turn: memorize → later recall → answer uses memorized fact

## Files to Modify

| File | Iteration | Change |
|------|-----------|--------|
| `src/memoryos_lite/agent_answer_eval.py` | 1 | LLMAnswerer + LLMJudge |
| `src/memoryos_lite/public_benchmarks.py` | 1 | Wire answerer/judge CLI flags |
| `src/memoryos_lite/agent_graph.py` | 2 | Add think/action/observe nodes |
| `tests/test_agent_answer_eval.py` | 1 | Judge verdict tests |
| `tests/test_agent.py` | 2 | Deterministic agent loop tests |

## Constraints

- DeepSeek API key required for LLM answerer/judge
- Without API key: falls back to projected answer + substring match
- Hard eval must remain 1.00/1.00
- LongMemEval source_hit must remain >= 92%
- No unbounded autonomous behavior
