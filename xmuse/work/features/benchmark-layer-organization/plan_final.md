# Plan Final: benchmark-layer-organization

feature_id: benchmark-layer-organization
updated_at: 2026-05-25T07:52:36Z

## Goal

Repair the in-authority hard-eval regression left by the previous partial ACK:
the documented default command `uv run memoryos eval run --case-set hard
--baseline memoryos_lite` reported `0.56/0.56` on the v3 default path even
though the v1 fallback path reported `1.00/1.00`.

## Files

Product:

- `src/memoryos_lite/evals.py`

Tests:

- `tests/test_evals.py`

Artifacts:

- `xmuse/work/features/benchmark-layer-organization/*`

Ignored local runtime setup:

- `benchmarks/longmemeval/longmemeval.json`
- `benchmarks/locomo/locomo10.json`
- `.memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json`
- `.memoryos/evals/routeb_locomo50_llm_20260524_locomo.json`

## TDD Steps

1. RED: add a default-v3 hard eval test and focused evidence-selection tests.
2. GREEN: skip generic acknowledgements during eval answer selection, prefer
   update evidence for slot questions, and preserve competing v3 restatements
   for habit/preference questions.
3. REFACTOR: keep the change inside eval answer projection and avoid changing
   v1 fallback, v3 defaults, retrieval-pipeline defaults, or public benchmark
   scoring semantics.

## Gates

- New focused RED/GREEN eval tests.
- `tests/test_evals.py`.
- Focused recall, context composer, and public diagnostics suites.
- Hard eval default command.
- Full pytest.
- Ruff.
- Targeted mypy for touched modules.
- Full-project mypy recorded as residual blocker if still failing.
- Public no-LLM relative-path smoke diagnostics.

## Non-Goals

- No benchmark score optimization.
- No public LLM full-chain claim without provider credentials.
- No default change for `MEMORYOS_RECALL_PIPELINE`, `MEMORYOS_MEMORY_ARCH`, or
  `MEMORYOS_AGENT_KERNEL`.
- No archive-rag work.
- No project-wide mypy cleanup outside this feature slice.
