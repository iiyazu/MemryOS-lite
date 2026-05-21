# Result: Phase 1 - Memory v3 Contracts

## 修改的文件
- `src/memoryos_lite/v3_contracts.py` - 新增 Memory v3 contract module，包含 provenance/source refs、layer contracts、adapter helpers、table boundaries、kernel policy/approval/trace/protocol contracts、显式 `__all__`。
- `tests/test_v3_contracts.py` - 新增 13 个 contract tests，覆盖 shared formats、legacy adapters、source-backed core updates、table boundaries、kernel policy/approval/trace、public exports。

## 测试结果
- RED: `uv run pytest tests/test_v3_contracts.py -v`
  - Task 2/3: import errors for missing memory layer and boundary symbols.
  - Task 4: import error for missing `KernelTraceEvent`.
  - Task 5: `AttributeError` for missing `contracts.__all__`.
- GREEN: `uv run pytest tests/test_v3_contracts.py -v` -> `13 passed in 0.11s`.
- Lint: `uv run ruff check src/memoryos_lite/v3_contracts.py tests/test_v3_contracts.py` -> passed.
- Full regression: `uv run pytest -q` -> `324 passed, 1 warning in 315.89s`.

## 边界确认
- 未修改 `src/memoryos_lite/engine.py`、`src/memoryos_lite/cli.py`、`src/memoryos_lite/api/app.py`。
- 未新增 phase-1 migration；`alembic/versions/` 仍只有 `0001` 到 `0004`。
- Legacy runtime paths remain on existing `schemas.py` / store / retrieval modules; v3 contracts are standalone.

## 实现说明
- `MemoryPage` / `MemoryItem` are declared as legacy adapter inputs only via `V3_NO_NEW_TARGETS` and `REQUIRED_V3_ADAPTERS`.
- Core memory updates require either source refs or an approved `ApprovalState`.
- Tool policy decisions forbid implicit `allow` with no matched rule.

## 偏差 / 问题
- Task 4 的 plan sample 使用 `SourceRef(source_type="manual", source_id="policy")`，但 Task 1 明确要求 manual source refs 必须带 `approval_id`。测试中保留该约束并使用 `approval_id="appr_policy"`。
- Plan 中的 per-task commit 步骤未执行；当前工作区已有多处 `.hermes-loop` 预存改动，EXECUTE 阶段只产出代码/测试与 Hermes 结果文件，未创建 git commit。

## 自检补充
- 修复了 `ruff` 报告的格式问题，未改变行为。
- 复验通过：`uv run pytest tests/test_v3_contracts.py -q` -> `13 passed`。
