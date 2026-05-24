# xmuse-console Context Bundle

feature_id: xmuse-console
worktree: /home/iiyatu/projects/python/memoryOS-xmuse-console
branch: feat/xmuse-console
target_branch: feat/phase-2.5-3-retrieval-agent
dispatch_base: 4c4712df763c652952a8066060bdb8bb4b37ba0b

## Active Inputs Read

- Root master state: `/home/iiyatu/projects/python/memoryOS/xmuse/master_state.json`
- Feature entry: `xmuse-console`, state `planned`, branch `feat/xmuse-console`, worktree `/home/iiyatu/projects/python/memoryOS-xmuse-console`
- Slave prompt: `/home/iiyatu/projects/python/memoryOS/xmuse/prompts/slave_god_prompt.md`
- Slave contract: `/home/iiyatu/projects/python/memoryOS/xmuse/contracts/slave_dispatch_template.json`
- Slave state: `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/xmuse-console/slave_state.json`
- Blueprint: `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/xmuse-console/blueprint.md`

## Invariants

- MemoryOS Lite remains an eval-driven, source-attributed Agent/RAG memory prototype.
- Default memory architecture remains `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` remains available.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite remains the authoritative MemoryOS store.
- xmuse is opt-in, local-only, read-only, and gated by `MEMORYOS_XMUSE_ENABLED=1`.
- No benchmark score target or improvement claim is in scope.

## Existing Code Shape

- Settings live in `src/memoryos_lite/config.py`.
- Existing FastAPI app is a module-level `app` in `src/memoryos_lite/api/app.py`.
- No frontend package/toolchain exists in the repository.
- Existing tests use `fastapi.testclient.TestClient`, pytest fixtures, and hermetic temp directories.

## Implementation Scope For This Turn

- Add xmuse settings only.
- Add stable xmuse DTO/adapter modules under `src/memoryos_lite/xmuse/`.
- Add API routes under `src/memoryos_lite/api/xmuse.py`, mounted at import time but unavailable unless enabled.
- Add hermetic fixture directories under `tests/fixtures/xmuse/`.
- Add tests for snapshot behavior, conflict/runtime/contract diagnostics, disabled-by-default routes, registry-only lane detail, and redaction.
- Add a static, read-only console shell in `frontend/xmuse/` with no write controls and no raw `xmuse` reads.

