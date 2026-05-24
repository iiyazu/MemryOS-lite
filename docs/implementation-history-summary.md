# Implementation History Summary

Date: 2026-05-24

This file replaces detailed historical implementation specs, plans, baseline
snapshots, and the old root-level project concept note. It keeps the facts that
future agents need without requiring new sessions to read obsolete design
threads.

## Project Origin

MemoryOS Lite began as an OS-style memory prototype for long-running agents:

- Treat the LLM context window as working memory.
- Keep a conservative context-rot budget instead of filling the model window.
- Persist overflow into source-attributed memory pages and later memory layers.
- Use provenance, patches, traces, and benchmarks to make memory behavior
  auditable.

That early concept has been superseded by the current architecture documented in
`README.md`, `docs/source-guide.md`, `docs/store-interface.md`, and
`consensus.md`.

## Historical Design Threads

Detailed historical Superpowers specs/plans were summarized and removed. The
important retained decisions are:

- v3 layered composer became the default memory architecture.
- v1 ContextBuilder remains available with `MEMORYOS_MEMORY_ARCH=v1`.
- v2 episode-first recall remains opt-in with `MEMORYOS_RECALL_PIPELINE=v2`.
- The agent kernel remains opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- SQLite remains the authoritative store.
- Qdrant/vector paths remain optional experiments.
- Source attribution and benchmark diagnostics are more important than broad
  product claims.
- Answer-quality diagnostics must stay separate from retrieval diagnostics.
- Public benchmark movement must report case-level fail-to-pass and
  pass-to-fail changes, not only aggregate movement.

## Historical Baseline Results

The removed `docs/baseline/` detail captured early deterministic and hard-set
results. Retained facts:

- Original deterministic eval had 81 cases across four baselines.
- `vector_rag` and `memoryos_lite` both reached 1.00 on the easy deterministic
  set, showing that the set was saturated.
- `memoryos_lite` used more context tokens than `vector_rag` on that early
  deterministic set.
- The hard adversarial set exposed weaknesses hidden by the easy set.
- Early hard-set v3 showed `memoryos_lite` at 0.31 accuracy.
- Semantic conflict detector work later improved `memoryos_lite` hard-set
  accuracy to 0.56 and solved the semantic-conflict category, while distractor
  and state-evolution gaps remained.

These numbers are historical diagnostics. Do not use them as current benchmark
claims unless reproduced.

## Deleted Detail Sets

The following historical detail sets were summarized and removed:

- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- `docs/baseline/`
- `memoryos-lite-design.md`

Future architecture and feature work should start from:

- `AGENTS.md`
- `consensus.md`
- `README.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- current code
- live Hermes `master_state.json` and `master_status.json`

## Rule For Future Agents

Do not treat this summary as proof of current performance. For current claims,
run fresh tests or evals and report exact commands and results.
