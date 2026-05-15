# Public Benchmark Diagnosis

This document freezes the first public LongMemEval and LoCoMo diagnosis for
MemoryOS Lite. The goal is not to claim production-grade memory, but to keep
future Agent/RAG changes measurable against simple baselines.

## Current Positioning

MemoryOS Lite is an eval-driven, source-attributed Agent/RAG memory prototype.
It is useful for demonstrating backend memory plumbing, source attribution,
token-budgeted context building, patch semantics, conflict guardrails, and
benchmark-driven iteration.

It is not production-ready MemoryOS. The LangGraph agent is a demo, heuristic
paging is a deterministic fallback, the conflict detector is a first-pass
slot/negation guardrail, and the API does not include production ownership,
auth, rate limiting, or a full error model.

## Frozen Results

Real DeepSeek run, `memoryos_lite`, LLM answer + LLM judge:

| Benchmark | Split | Pass | Source hit | Session hit | Report |
|---|---:|---:|---:|---:|---|
| LongMemEval oracle | first 10 | 1.00 | 1.00 | 1.00 | `/tmp/memoryos-public-real10/evals/deepseek_longmemeval_real10_llm_answer_longmemeval.json` |
| LoCoMo | first 10 | 0.00 | 0.00 | 0.00 | `/tmp/memoryos-public-real10/evals/deepseek_locomo_real10_llm_answer_locomo.json` |

Real-run report hashes on this machine:

- LongMemEval real10:
  `dc4db28b04f625cd43d1a03f026bf2b6c2f469fcee8be04107ca7f5cf25ecc82`
- LoCoMo real10:
  `8d1a9a34aaff0c3bf03f325051e681ac5ae3d8e6f3e207b9f09f586abbe8dec6`

Local no-LLM probe, first 10, projected answers:

| Benchmark | Baseline | Pass | Source hit | Session hit | Notes |
|---|---|---:|---:|---:|---|
| LongMemEval | sliding_window | 0.00 | 0.00 | 0.00 | Recent window misses old evidence |
| LongMemEval | naive_summary | 0.00 | 0.00 | 0.80 | Summary is too lossy for answer projection |
| LongMemEval | vector_rag | 0.00 | 0.30 | 1.00 | Message-level BM25 finds some source evidence |
| LongMemEval | memoryos_lite | 0.10 | 1.00 | 1.00 | Page source attribution works on this simple sample |
| LoCoMo | sliding_window | 0.00 | 0.00 | 0.00 | Recent D19 distractors dominate |
| LoCoMo | naive_summary | 0.00 | 0.00 | 0.00 | Early evidence is not preserved usefully |
| LoCoMo | vector_rag | 0.00 | 0.10 | 0.30 | Raw-message retrieval beats current page-level RAG |
| LoCoMo | memoryos_lite | 0.00 | 0.00 | 0.00 | Oversized page is dropped under budget |

M1 diagnostic harness, no LLM, first 50, compare-baselines:

| Benchmark | Baseline | Pass | Source hit | Session hit | Msg source@5 | Msg session@5 | Page src overlap@5 | Page session overlap@5 | Avg tokens | Pages | Loaded | Dropped | Relevant dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LongMemEval | sliding_window | 0.00 | 0.00 | 0.00 | - | - | - | - | 18 | 0.0 | 0.0 | 0.0 | 0 |
| LongMemEval | naive_summary | 0.02 | 0.02 | 0.50 | - | - | - | - | 48 | 0.0 | 0.0 | 0.0 | 0 |
| LongMemEval | vector_rag | 0.02 | 0.26 | 0.96 | 0.78 | 1.00 | - | - | 79 | 0.0 | 0.0 | 0.0 | 0 |
| LongMemEval | memoryos_lite | 0.10 | 0.96 | 0.98 | - | - | 1.00 | 1.00 | 50 | 1.0 | 1.0 | 0.0 | 2 |
| LoCoMo | sliding_window | 0.02 | 0.00 | 0.00 | - | - | - | - | 80 | 0.0 | 0.0 | 0.0 | 0 |
| LoCoMo | naive_summary | 0.02 | 0.00 | 0.00 | - | - | - | - | 80 | 0.0 | 0.0 | 0.0 | 0 |
| LoCoMo | vector_rag | 0.04 | 0.08 | 0.30 | 0.25 | 0.62 | - | - | 77 | 0.0 | 0.0 | 0.0 | 0 |
| LoCoMo | memoryos_lite | 0.02 | 0.00 | 0.00 | - | - | 0.98 | 1.00 | 80 | 1.0 | 0.0 | 1.0 | 47 |

In the M1 snapshot, `Msg source@5` and `Msg session@5` are budget-before
top-5 raw-message retrieval metrics for the message-level baselines.
`memoryos_lite` at that point retrieves pages, not evidence chunks, so its
top-5 diagnostic is reported separately as page source/session overlap. A high
page-overlap score only means the retrieved page's broad source set contains
the expected message; it does not mean the system localized the evidence. This
is why M2 must add raw-message/evidence-chunk retrieval.

Reproduce the M1 reports:

```bash
uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path /tmp/memoryos-public-benchmarks/longmemeval_oracle.json \
  --run-id m1_longmemeval_50 \
  --limit 50 \
  --compare-baselines \
  --no-llm-answer \
  --no-llm-judge

uv run memoryos eval public \
  --benchmark locomo \
  --data-path /tmp/memoryos-public-benchmarks/locomo10.json \
  --run-id m1_locomo_50 \
  --limit 50 \
  --compare-baselines \
  --no-llm-answer \
  --no-llm-judge
```

Reports:

- `.memoryos/evals/m1_longmemeval_50_longmemeval.json`
- `.memoryos/evals/m1_locomo_50_locomo.json`
- Tracked aggregate snapshot:
  `docs/baseline/public_m1_summary.json`
- Tracked LoCoMo failure sample:
  `docs/baseline/public_m1_locomo_failures_sample.json`

Input and tracked artifact hashes:

- LongMemEval input:
  `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c`
- LoCoMo input:
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`
- Tracked M1 aggregate summary:
  `36570996b1ebbeddfcdedb53c39d354205d21effd399fce39d17a013fe0a788e`
- LoCoMo failure sample:
  `72d4ab0a64f10859cd6f9dc6a3e722cbfc2451d247d23570c6107aa58a0c0a27`

The raw `.memoryos/evals/m1_*.json` reports are intentionally not used as
stable hashes because they include runtime-generated IDs such as page IDs. The
tracked summary and failure sample are the reproducible freeze artifacts.

## LoCoMo Failure Chain

The first LoCoMo sample has 419 messages across 19 benchmark sessions and about
19k estimated tokens per QA case. Current `memoryos_lite` baseline sets
`rot_safe_budget = 1` for eval and calls `page()` once, which compresses almost
the whole conversation into one page.

Observed in the real run:

- `page_count = 1` for every LoCoMo first-10 case.
- `page_type_counts = {"core_profile_page": 10}` across the real first-10 run.
- The single page has hundreds of `source_message_ids` but only a small facts
  slice and an oversized summary.
- Context budget is 90 tokens; the page costs about 135 tokens and is dropped
  as `core_profile_exceeds_budget`.
- The answerer sees either no memory or the two most recent D19 messages, while
  expected evidence lives in D1-D3.

This means LoCoMo failure is primarily a retrieval/context construction issue,
not just an answer-generation issue.

## Optimization Implications

M1 must land first: public benchmark reports need page type distribution,
dropped-page reasons, source/session overlap, and retrieval-only metrics before
M2/M3 changes are judged.

M2 must retrieve raw message/evidence chunks. Cutting evidence only from
`page.summary` or `page.facts` will not fix LoCoMo because many answers depend
on original utterances, dates, speakers, and benchmark session metadata.

## M2 Raw-Message Evidence Retrieval

M2 adds a raw-message evidence path to `ContextPackage.retrieved_evidence`.
Context building still keeps page retrieval for compatibility, but when a
retrieved page is too large to fit, the builder can now fall back to BM25-ranked
source messages under the same token budget. Paging itself is unchanged.

M2 diagnostic harness, no LLM, first 50, compare-baselines:

| Benchmark | Baseline | Pass | Source hit | Session hit | Msg source@5 | Msg session@5 | Page src overlap@5 | Page session overlap@5 | Avg tokens | Pages | Loaded | Dropped | Relevant dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LongMemEval | vector_rag | 0.06 | 0.32 | 0.98 | 0.90 | 1.00 | - | - | 78 | 0.0 | 0.0 | 0.0 | 0 |
| LongMemEval | memoryos_lite | 0.10 | 0.96 | 0.98 | 0.90 | 1.00 | 1.00 | 1.00 | 57 | 1.0 | 1.0 | 0.0 | 2 |
| LoCoMo | vector_rag | 0.02 | 0.21 | 0.36 | 0.46 | 0.74 | - | - | 80 | 0.0 | 0.0 | 0.0 | 0 |
| LoCoMo | memoryos_lite | 0.02 | 0.21 | 0.36 | 0.46 | 0.74 | 0.98 | 1.00 | 77 | 1.0 | 0.0 | 1.0 | 47 |

Compared with M1, LoCoMo `memoryos_lite` final source/session hit improves from
`0.00/0.00` to `0.21/0.36`, matching the raw-message `vector_rag` baseline
while preserving LongMemEval source/session at `0.96/0.98`. The remaining
LoCoMo gap is now evidence ranking/answer projection quality, not only page
budget loss; M3 should still fix the oversized single-page behavior.

Tracked M2 aggregate snapshot:
`docs/baseline/public_m2_summary.json`

M2 summary hash:
`2608e0360f3092494409c1dd91e67a9fced8b9a77429b3855e85d5f815d22d62`

M3 can then improve paging granularity. Session/window-aware paging should
reduce oversized pages and avoid misclassifying entire multi-session dialogues
as core profile pages, but it should not be mixed into the first evidence-level
retrieval change.

## Metric Scope Caveat

The public harness reports three related but different source metrics:

- `page_source_overlap_at_5` / `page_session_overlap_at_5`: page-candidate
  diagnostics. A hit means one of the top page candidates has
  `source_message_ids` that overlap the expected evidence/session. This is page
  granularity; it does not prove evidence localization.
- `msg_source_hit_at_5` / `msg_session_hit_at_5`: actual message evidence
  diagnostics for `memoryos_lite`. These are now read from
  `context.retrieved_evidence[:5]`, so they reflect message snippets that
  actually entered the context package under budget.
- `source_hit` / source accuracy: final projected-answer attribution. In the
  current deterministic eval implementation, `memoryos_lite` builds final
  evidence from multiple paths: actual `context.retrieved_evidence`, recent
  messages, and `_page_evidence(page, ...)` reconstructed from loaded page
  facts/decisions in the store. The last path uses the page object after the
  context builder has loaded a page summary under budget; it can credit source
  IDs from the page's stored `source_message_ids` and facts, so it is not the
  same as proving an evidence-first RAG path localized the original message.

Therefore, when judging evidence-level retrieval progress, prefer
`msg_source_hit_at_5` and inspect `context.retrieved_evidence`. Use
`page_source_overlap_at_5` as a page-ranking diagnostic and `source_hit` as the
final deterministic answer/source projection score, not as a pure retriever
metric.

Blocking interpretation rule for M3/M4: do not treat current
`source_hit`/source accuracy as evidence-first RAG validation. It is a mixed
final-answer attribution score because the eval can combine loaded
`retrieved_evidence` with page-fact evidence reconstructed from stored
`MemoryPage` objects. A page-level hit, an evidence-level hit, and the final
source score answer different questions and must be reported separately.

## M3 Session/Window-Aware Paging

M3 changes the heuristic pager from one page per paging call to conservative
session/window pages. It splits by benchmark session/date metadata when present
and by configurable window limits (`memoryos_page_window_max_messages = 24`,
`memoryos_page_window_max_tokens = 5000`). It also prioritizes raw retrieved
message evidence before loading non-core page summaries so extra small pages do
not starve source-attributed evidence. Raw evidence is compacted into bounded
source-attributed snippets (`memoryos_evidence_max_tokens = 48`) so long
messages can fit into the 90-token deterministic eval budget.

M3 diagnostic harness, no LLM, first 50, compare-baselines:

| Benchmark | Baseline | Pass | Source hit | Session hit | Msg source@5 | Msg session@5 | Page src overlap@5 | Page session overlap@5 | Avg tokens | Pages | Loaded | Dropped | Relevant dropped | Srcs/page |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LongMemEval | vector_rag | 0.06 | 0.32 | 0.98 | 0.90 | 1.00 | - | - | 78 | 0.0 | 0.0 | 0.0 | 0 | - |
| LongMemEval | memoryos_lite | 0.08 | 0.86 | 1.00 | 0.48 | 0.84 | 1.00 | 1.00 | 79 | 2.3 | 1.9 | 0.0 | 2 | 10.8 |
| LoCoMo | vector_rag | 0.02 | 0.21 | 0.36 | 0.46 | 0.74 | - | - | 80 | 0.0 | 0.0 | 0.0 | 0 | - |
| LoCoMo | memoryos_lite | 0.04 | 0.15 | 0.15 | 0.00 | 0.00 | 0.25 | 0.26 | 86 | 24.0 | 2.7 | 10.3 | 9 | 17.4 |

M3 is a mixed result, not a LoCoMo fix:

- LongMemEval stays reasonably close to M2 on source hit (`0.86` vs `0.96`),
  while actual loaded raw-evidence `Msg source@5` improves from `0.06` before
  snippet compaction to `0.48`.
- LoCoMo no longer has the single giant page pathology: average page count is
  `24.0`, and relevant dropped pages fall from `47` in M2 to `9`.
- LoCoMo final source/session hit regresses from M2 (`0.21/0.36`) to
  `0.15/0.15`. Page candidate overlap is also much lower than M2 because
  smaller pages remove the broad source-union effect and expose weak page
  ranking/answer projection.
- M3 `memoryos_lite` `Msg source@5` / `Msg session@5` now report actual
  `context.retrieved_evidence`, not a separate BM25 probe. The low
  `0.00/0.00` LoCoMo value shows that raw evidence is not being loaded
  reliably even when page candidates overlap; core-profile page pinning still
  consumes the available budget in those cases.
- The honest conclusion is that M3 improves page granularity diagnostics and
  reduces dropped relevant pages, but it does not solve LoCoMo. The next
  bottleneck is evidence/page ranking plus answer projection, not simply
  paging size.

Tracked M3 aggregate snapshot:
`docs/baseline/public_m3_summary.json`

M3 summary hash:
`9518d723b74ecb56a5d016b09dcfccc491b85c6dda2dbe550971cb8b243eda8d`

## M3b Supersession-Aware Raw Evidence Retrieval

T-06 showed that M3's LoCoMo failure was mostly not a page-window-size issue:
`40/47` traced expected sources were present only in superseded pages and
therefore excluded from active `source_page_ids`. M3b keeps page summary
retrieval unchanged but lets superseded pages contribute raw-message evidence
candidates. These snippets are marked with `ContextEvidence.superseded` so
downstream scoring can treat them as lower-confidence historical evidence.

M3b also reserves evidence budget only for multi-page dialogue contexts
(`memoryos_evidence_reserve_min_pages = 8`,
`memoryos_evidence_reserve_ratio = 0.6`,
`memoryos_evidence_reserve_tokens = 64`). This avoids regressing smaller
LongMemEval-style contexts while giving LoCoMo enough budget to load several
evidence snippets before core-profile pages consume the whole 90-token budget.

M3b diagnostic harness, no LLM, first 50, `memoryos_lite` only:

| Benchmark | Pass | Source hit | Session hit | Msg source@5 | Msg session@5 | Page src overlap@5 | Page session overlap@5 | Avg tokens | Pages | Loaded | Dropped | Relevant dropped | Sup recovered | Candidate budget dropped | Active overlap not top5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LongMemEval | 0.10 | 0.94 | 1.00 | 0.12 | 0.50 | 1.00 | 1.00 | 69.8 | 2.3 | 1.9 | 0.0 | 2 | 6 | 225 | 785 |
| LoCoMo | 0.02 | 0.00 | 0.00 | 0.21 | 0.38 | 0.25 | 0.26 | 82.0 | 24.0 | 2.7 | 10.3 | 16 | 27 | 187 | 10018 |

Tracked M3b aggregate snapshot:
`docs/baseline/public_m3b_summary.json`

M3b summary hash:
`1875597b7136d8a682526ab8849981a8f087f6d4e31f6b3a6975a80904d6c3c8`

M3b is still not a LoCoMo answer-quality fix:

- It meets the evidence-level target: LoCoMo `Msg source@5` rises from M3
  `0.00` to `0.21`, and `25/50` cases load at least one superseded-source
  evidence snippet.
- The `Active overlap not top5` column is a cumulative message count across
  all evaluated cases, not a case count. The LoCoMo value `10018` means many
  active messages had positive lexical overlap but were outside the top-5
  loaded evidence candidates; it should not be read as 10018 failed QA cases.
- A follow-up manual branch check shows remaining superseded-source failures
  are still high: `32/47` expected-source cases remain in the
  `expected source is only in superseded pages and was not loaded` bucket
  after M3b. This improves over M3's `40/47`, but misses the aspirational
  `<= 10/47` acceptance line.
- LongMemEval final source hit stays above the acceptance floor (`0.94` vs the
  required `>= 0.81`), because evidence reserve is gated to multi-page
  contexts and superseded snippets are downweighted in deterministic answer
  projection.
- LoCoMo final deterministic `source_hit` / `session_hit` falls to `0.00/0.00`.
  This is an accepted mixed result for M3b: the raw evidence path is now
  measurable, but answer projection and ranking still fail. Do not describe
  M3b as solving LoCoMo.

M4 is an interview demo target, not a production-agent target. The current
LangGraph demo supports evidence-grounded citation answers, patch conflict
interrupt, max tool-loop turns, and cross-session read rejection. These are
demo guardrails around the memory path, not full production orchestration or
general-purpose agent reliability.
