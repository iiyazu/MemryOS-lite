# Baseline — Before Enhancement (M0)

Captured on `main@28f905a` prior to the 10-day enhancement roadmap. This file is the objective reference point that every later milestone (M2 hybrid retrieval, M3 conflict detector, M4 LLM eval, M5 perf) diffs against.

## Reproduce

```bash
uv run memoryos eval run --run-id baseline_before --baseline all
# raw report: .memoryos/evals/baseline_before.json  (gitignored, 324 records)
```

Aggregation script is embedded below; raw per-case records live in `.memoryos/evals/baseline_before.json` (not tracked).

## Deterministic Benchmark Results (81 cases × 4 baselines)

| baseline | cases | accuracy | source_acc | avg ctx tokens | **accuracy / 1k tokens** | avg pages loaded | avg latency (ms) |
|---|---|---|---|---|---|---|---|
| sliding_window | 81 | 0.210 | 0.210 | 35.4 | 5.93 | 0.00 | 0.0 |
| naive_summary | 81 | 0.605 | 0.605 | 52.8 | 11.45 | 0.00 | 0.0 |
| vector_rag | 81 | **1.000** | **1.000** | 50.2 | **19.91** | 0.00 | 0.0 |
| memoryos_lite | 81 | **1.000** | **1.000** | 63.7 | 15.70 | 0.99 | 99.3 |

## Key Read

Under the **deterministic eval**, `vector_rag` and `memoryos_lite` both hit 1.00 accuracy, but `vector_rag` uses fewer tokens (50.2 vs 63.7) and scores higher on accuracy-per-1k (19.91 vs 15.70). On this eval alone, `memoryos_lite` is strictly inferior.

This is the expected result — the deterministic benchmark is lexical-overlap-driven; in small-corpus + high-recall regime BM25-style retrieval saturates easily and the cost of maintaining memory pages shows up as overhead. **The hypothesis to be validated by M4 (LLM eval) is that under faithfulness / hallucination / cost-per-correct-answer metrics, `memoryos_lite` wins where `vector_rag` silently fails.** That is the story this project has to prove.

## Frozen Numbers (for later diff)

- memoryos_lite avg_context_tokens: **63.7** — M2 + M4 aim to push this down via hybrid retrieval + better budgeting
- memoryos_lite accuracy_per_1k_tokens: **15.70** — target: ≥ 20 after M2
- memoryos_lite avg_latency_ms: **99.3** — M5 pressure test establishes P95
- No LLM-faithfulness / hallucinated_memory_rate data exists yet — M4 will introduce these columns

## Test Health

`uv run pytest -q` — **39 passed** in 62.4s (1 LangGraph deprecation warning). Treat this as the quality gate for every milestone commit.
