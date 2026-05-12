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

## Hard Bench v3 (M10 #1 — Adversarial Set, 16 cases)

Captured to justify M10. The builtin set saturates at 1.00 for `vector_rag` and `memoryos_lite`, hiding real weaknesses. `hard_bench_v3` is a 16-case adversarial set (4 categories × 4 scenarios) designed to stress the gaps the code review flagged: ConflictDetector (玩具), LLM-judge stress, paging dedup.

### Reproduce

```bash
uv run memoryos eval run --run-id hard_bench_v3 --baseline all --case-set hard
# raw report: .memoryos/evals/hard_bench_v3.json
```

### Per-baseline accuracy on hard set

| baseline | builtin (81) | hard (16) | delta |
|---|---|---|---|
| sliding_window | 0.21 | 0.38 | +0.17 |
| naive_summary  | 0.60 | 0.31 | −0.29 |
| vector_rag     | **1.00** | 0.31 | **−0.69** |
| memoryos_lite  | **1.00** | 0.31 | **−0.69** |

`vector_rag` and `memoryos_lite` — the two systems that previously looked "perfect" — collapse on the hard set and do no better than the trivial sliding window. This is the smoking gun: the builtin benchmark was too easy to be trusted.

### Per-category breakdown (accuracy, n = cases)

| category | n | sliding | naive | vector | memoryos |
|---|---|---|---|---|---|
| `semantic_conflict_*` (no negation word) | 4 | **0.00** | **0.00** | **0.00** | **0.00** |
| `distractor_keyword_*` (plausible-wrong keyword) | 4 | 0.25 | 0.00 | 0.25 | 0.00 |
| `state_evolution_*` (fact revised 2–3×) | 4 | 0.25 | 0.25 | 0.00 | 0.25 |
| `restatement_dedup_*` (same fact, 3 phrasings) | 4 | 1.00 | 1.00 | 1.00 | 1.00 |

### What the zeros mean

- `semantic_conflict_*`: 0% everywhere — no baseline, including `memoryos_lite`, flags "数据库改用 MySQL" as contradicting an earlier "数据库选 PostgreSQL". `ConflictDetector` requires a negation word (`不做`/`改为`/…); these cases don't have one. Fixing this is M10 #2.
- `distractor_keyword_*`: 0–25% — the retrieval layer returns both facts and the answer concatenation includes the forbidden keyword. `memoryos_lite`'s heuristic-paging `summary = facts[:3]` ordering drops the newer statement when it comes after position 3.
- `state_evolution_*`: 0–25% — old versions are not evicted; answer contains all three and fails the `forbidden_facts` check.
- `restatement_dedup_*`: 1.00 on answer-accuracy is misleading — every baseline gets the fact right, but `memoryos_lite` stores the 3 restatements as 3 separate facts on the page (observable via `source_count` avg = 3.7, vs 2.2 for sliding_window). Dedup is a quality gap that answer-accuracy doesn't capture.

### Frozen numbers (for later diff)

- memoryos_lite hard-set accuracy: **0.31** — target after M10 #2 (ConflictDetector + embeddings): ≥ 0.60
- All baselines on `semantic_conflict_*`: **0.00** — target after M10 #2: memoryos_lite ≥ 0.75
- memoryos_lite `restatement_dedup_*` source_count avg: **3.7** — target after dedup work: ≤ 1.5

### Witness test

`tests/test_conflict_adversarial.py` holds four `xfail(strict=True)` tests. Each flips to a real PASS the moment `ConflictDetector` grows a semantic layer — making the M10 #2 acceptance criterion self-documenting.

## Hard Bench v4 (M10 #2 — After Semantic Conflict Detector)

Captured after implementing `SlotExtractor` + intra-draft conflict pruning + cross-page supersession. Compare directly to the v3 table above.

### Reproduce

```bash
uv run memoryos eval run --run-id hard_bench_v4 --baseline all --case-set hard
# raw report: .memoryos/evals/hard_bench_v4.json
```

### Per-baseline accuracy on hard set (v4)

| baseline | v3 | v4 | delta |
|---|---|---|---|
| sliding_window | 0.38 | 0.38 | — |
| naive_summary  | 0.31 | 0.31 | — |
| vector_rag     | 0.31 | 0.31 | — |
| memoryos_lite  | **0.31** | **0.56** | **+0.25** |

memoryos_lite is now the only baseline that beats the trivial sliding window on the hard set — the gap we were trying to open.

### Per-category breakdown (accuracy, memoryos_lite only)

| category | v3 | v4 | delta |
|---|---|---|---|
| `semantic_conflict_*` | 0/4 | **4/4** | **+1.00** |
| `distractor_*` | 0/4 | 0/4 | — |
| `state_evolution_*` | 1/4 | 1/4 | — |
| `restatement_dedup_*` | 4/4 | 4/4 | — |

### Scorecard vs M10 #2 targets

- memoryos_lite hard-set: **0.56** (target ≥ 0.60) — narrowly short; distractor/state_evolution are paging-quality gaps outside M10 #2 scope
- semantic_conflict: **1.00** (target ≥ 0.75) — **hit**
- The four `xfail(strict=True)` witnesses in `tests/test_conflict_adversarial.py` now pass — acceptance criterion self-validated


