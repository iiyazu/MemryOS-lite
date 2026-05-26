# memoryos-redis-cache-probe Execute Review

feature_id: memoryos-redis-cache-probe
reviewed_at: 2026-05-25T08:10:19Z
base: 0b30e04194efbb5b70d215df7d5b1234886654a8
head: a8f2a8e609d2b1315a1710706bda77be3feb7e20

## Review Scope

Read-only local review of the rework diff:

- `src/memoryos_lite/engine.py`
- `tests/test_engine.py`
- `tests/conftest.py`

## Findings

No blocking issues found.

## Checks

- Optional provider fallback: FastEmbed import/construction exceptions now return no embedding client, matching the existing optional OpenAI-provider fallback style.
- Test isolation: pytest sets `HF_HUB_OFFLINE=1`, so direct `uv run pytest -q` no longer depends on Hugging Face availability.
- Regression coverage: `tests/test_engine.py::test_fastembed_provider_falls_back_to_no_embedding_when_unavailable` verifies service construction continues after FastEmbed construction failure.
- Runtime behavior: when FastEmbed is available, `FastEmbedClient()` is still used; when unavailable, existing lexical/no-embedding paths are used.
- Type cleanup: nullable LLM client and kernel tool spec handling were tightened without changing default behavior.
- Defaults: v3 default, v1 fallback, v2 recall opt-in, and kernel opt-in defaults remain unchanged.
- Benchmark policy: no benchmark score movement or improvement claim is made.

## Verification Evidence

- `uv run pytest tests/test_engine.py::test_fastembed_provider_falls_back_to_no_embedding_when_unavailable -q`
  - RED before repair: failed with `RuntimeError: model unavailable`.
  - GREEN after repair: `1 passed in 2.76s`.
- `uv run pytest tests/test_public_benchmarks.py::test_run_public_benchmark_without_llm_judge_writes_report -q`
  - `1 passed in 1.10s`.
- `HF_HUB_OFFLINE=1 uv run pytest tests/test_public_benchmarks.py tests/test_longmemeval_integration.py -q`
  - `78 passed in 120.06s`.
- `uv run pytest tests/test_config.py tests/test_memory_cache.py tests/test_recall_cache.py tests/test_recall_pipeline.py tests/test_engine.py::test_fastembed_provider_falls_back_to_no_embedding_when_unavailable tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q`
  - `28 passed in 32.34s`.
- `HF_HUB_OFFLINE=1 uv run pytest tests/test_engine.py tests/test_public_benchmarks.py tests/test_longmemeval_integration.py tests/test_config.py tests/test_memory_cache.py tests/test_recall_cache.py tests/test_recall_pipeline.py -q`
  - `142 passed in 232.67s`.
- `uv run pytest -q`
  - `616 passed, 1 warning in 999.13s`.
- `uv run ruff check .`
  - `All checks passed!`.
- `uv run mypy src/memoryos_lite/engine.py src/memoryos_lite/config.py src/memoryos_lite/cache src/memoryos_lite/retrieval/recall_pipeline.py`
  - `Success: no issues found in 4 source files`.
- `uv run mypy src`
  - `81 errors in 10 files`; outside this repair path.
- `git diff --check`
  - exit 0, no whitespace errors.

## External Review Attempt

- `gpt-5.2-codex` reviewer: provider `503 Service Unavailable`.
- default Codex reviewer: timed out after 120 seconds.

## Residual Risks

- Full project mypy remains red due existing unrelated type debt.
- Real Redis latency probe was not run.
