# Execute Self-Review: Phase 2 - Recall Memory Layer

## 小问题修复
- 修正 `.hermes-loop/result.md` 中焦点测试数量：本轮复验为 `66 passed in 363.80s`，不是旧记录的 `65 passed`。

## 大问题标记
- 无。
- `EpisodeSearcher` 仍保留 legacy `episode_bm25` source label 与旧 import path。
- v2 recall metadata 同时写入 recall-native keys 与 legacy compatibility keys。
- public benchmark report 仍暴露旧字段名，未泄漏 `recall_*` 内部 metadata。
- 默认 `v1` 行为未在本轮内审中发现被改动。

## 复验
- `uv run ruff check src/memoryos_lite/retrieval/episode_searcher.py src/memoryos_lite/retrieval/recall_pipeline.py src/memoryos_lite/evals.py tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_evals.py tests/test_public_benchmarks.py` -> passed。
- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_evals.py tests/test_public_benchmarks.py -q` -> `66 passed in 363.80s`。

## 结论
PASS — 可提交 Review。
