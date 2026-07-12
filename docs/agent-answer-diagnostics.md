# Agent Answer Diagnostics

MemoryOS Lite includes deterministic diagnostics for the experimental
LangGraph answer surface. These diagnostics check grounding behavior; they are
not production answer-quality claims.

## Scope

The diagnostics compare final answer text with the raw message evidence in
`ContextPackage.retrieved_evidence`.

Reported metrics:

| Metric | Meaning |
|---|---|
| `answer_has_citation` | The answer contains at least one `[message_id]` citation. |
| `answer_uses_retrieved_source` | At least one cited source ID appears in retrieved evidence. |
| `refusal_when_no_evidence` | No-evidence cases return a deterministic refusal. |
| `unsupported_answer_rate` | Non-refusal answers that lack retrieved citation support. |

These metrics are separate from public benchmark retrieval diagnostics such as
`episode_source_hit_at_10` and `planned_evidence_source_hit_at_5`.

## Offline Commands

```bash
uv run memoryos demo agent
uv run memoryos eval agent-answer
uv run pytest tests/test_agent_answer_eval.py tests/test_agent.py -q
```

The deterministic paths use fixtures, mocked responses, or scripted fake LLM
behavior. They do not require `OPENAI_API_KEY` or `DEEPSEEK_API_KEY`.

## Optional Real LLM Paths

Real LLM calls are opt-in:

- `MEMORYOS_PAGING_MODE=llm`
- `uv run memoryos eval run --llm-judge`
- `uv run memoryos eval public --llm-answer`
- `uv run memoryos eval public --llm-judge`
- custom LangGraph runs without a fake/scripted LLM

Minimal chat configuration:

```bash
MEMORYOS_LLM_PROVIDER=openai
OPENAI_API_KEY=...
MEMORYOS_MODEL=gpt-4o-mini
```

```bash
MEMORYOS_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
```

OpenAI-compatible embeddings require `OPENAI_API_KEY`; DeepSeek is used only
for chat-compatible paths in this project.
