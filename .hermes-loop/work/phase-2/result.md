# Result: Phase 3 - Core Memory Blocks

## 修改的文件
- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/core_memory.py`
- `alembic/versions/0005_add_core_memory.py`
- `tests/test_v3_contracts.py`
- `tests/test_core_memory_store.py`
- `tests/test_core_memory_service.py`
- `tests/test_engine.py`

## 测试结果
- Focused:
  - `uv run pytest tests/test_v3_contracts.py -q` -> `15 passed`
  - `uv run pytest tests/test_core_memory_store.py -q` -> `2 passed`
  - `uv run pytest tests/test_core_memory_service.py -q` -> `3 passed`
  - `uv run pytest tests/test_engine.py -q` -> `35 passed`
- Full regression:
  - `uv run pytest -q` -> `337 passed, 1 warning`

## 变更摘要
- Core memory contracts now carry soft-delete fields and `replace` requires `old`.
- SQLite store now persists `core_memory_blocks` and `core_memory_history`, and stamps Alembic head at `0005_add_core_memory`.
- `CoreMemoryService` owns create / append / replace / update / delete semantics plus token-limit checks and deterministic render output.
- Engine default context remains unchanged; core memory is still opt-in from the legacy path.

## 备注
- 本轮接手时工作区里已经有相关实现草稿，我只做了验证、补齐交付文件和状态推进。
- 未创建 git commit。
