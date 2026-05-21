# Result: Phase 2 - Recall Memory Layer

## 修改的文件
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/retrieval/__init__.py`
- `src/memoryos_lite/evals.py`
- `tests/test_episode_retrieval.py`
- `tests/test_recall_pipeline.py`
- `tests/test_evals.py`
- `tests/test_public_benchmarks.py`

## 测试结果
- RED: `uv run pytest tests/test_recall_pipeline.py tests/test_evals.py tests/test_public_benchmarks.py tests/test_episode_retrieval.py -q`
  - 首次暴露 `RecallMemoryEntry` 适配错误：pipeline 仍读取 legacy `benchmark_session_id` 字段。
- RED: `uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_prioritizes_direct_hits_before_neighbors -q`
  - 暴露 neighbor expansion 抢占 top-k，挤掉后续 direct hit。
- GREEN: `uv run pytest tests/test_recall_pipeline.py tests/test_evals.py tests/test_public_benchmarks.py tests/test_episode_retrieval.py -q`
  - `66 passed in 363.80s`
- Smoke benchmarks:
  - `MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge`
    - `episode_source_hit_at_10 = 8/10`
    - `planned_evidence_source_hit_at_5 = 8/10`
  - `MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge`
    - `episode_source_hit_at_10 = 5/10`
    - `planned_evidence_source_hit_at_5 = 5/10`
- Lint: `uv run ruff check src/memoryos_lite/retrieval/episode_searcher.py src/memoryos_lite/retrieval/recall_pipeline.py src/memoryos_lite/evals.py tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_evals.py tests/test_public_benchmarks.py`
  - passed
- Full regression: `uv run pytest -q`
  - `329 passed, 1 warning in 321.18s`

## 变更摘要
- 新增 `RecallMemorySearcher` 及 structured diagnostics / rank features，`EpisodeSearcher` 保留 legacy `episode_bm25` 兼容层。
- `RecallPipeline` 改为先把 episodes 转成 recall entry，再写入 recall-native 与 legacy 双轨 metadata。
- `evals.py` 改为 presence-aware 读取 recall-native metadata，legacy 仅作为回退。
- public benchmark 报告字段保持旧 schema，不暴露新的 recall 字段。

## 备注
- LongMemEval / LoCoMo smoke 已按本地数据实际运行，不是推断值。
- 未创建 git commit。
