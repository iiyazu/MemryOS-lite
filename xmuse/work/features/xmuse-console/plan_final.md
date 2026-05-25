# xmuse-console Implementation Plan

feature_id: xmuse-console

> For agentic workers: execute with feature-local plan/execute/review nodes. Apply TDD for behavior changes.

## Goal

Build a read-only, local-only xmuse snapshot/API surface gated by `MEMORYOS_XMUSE_ENABLED=1`, plus a static console shell that consumes xmuse DTOs.

## Architecture

`xmuse` fixture or live files are read by `XmuseSnapshotBuilder`, normalized into stable dict DTOs, and exposed through FastAPI routes in `memoryos_lite.api.xmuse`. The frontend shell lives under `frontend/xmuse/` and fetches only xmuse API DTOs.

## Files

- Modify `src/memoryos_lite/config.py` for xmuse settings.
- Create `src/memoryos_lite/xmuse/__init__.py`.
- Create `src/memoryos_lite/xmuse/adapter.py`.
- Create `src/memoryos_lite/api/xmuse.py`.
- Modify `src/memoryos_lite/api/app.py` to include the router.
- Create fixture directories under `tests/fixtures/xmuse/`.
- Create `tests/test_xmuse_snapshot.py`, `tests/test_xmuse_adapter.py`, and `tests/test_xmuse_api.py`.
- Create `frontend/xmuse/index.html`, `frontend/xmuse/styles.css`, `frontend/xmuse/app.js`, and `frontend/xmuse/README.md`.

## Tasks

1. Write failing tests for settings defaults, snapshot degraded behavior, contract summaries, conflicts, stale runtime, lane detail registry lookup, disabled routes, enabled routes, traversal resistance, and redaction.
2. Run focused tests to confirm RED failures from missing xmuse modules/settings/routes.
3. Implement minimal xmuse settings, DTO builder, tolerant JSON reading, contract summaries, artifact checklist, conflict diagnostics, runtime diagnostics, repository diagnostics, redaction, and registry-only lane detail.
4. Wire FastAPI routes so `/xmuse/snapshot` and `/xmuse/lanes/{feature_id}` return 404 unless enabled.
5. Add a static console shell with Overview, Control Plane, Lanes, Conflicts, Runtime, and Lane Detail views. Ensure it has no write controls and reads only API DTOs.
6. Run focused verification: `tests/test_xmuse_snapshot.py`, `tests/test_xmuse_adapter.py`, `tests/test_xmuse_api.py`, and `tests/test_api.py`.
7. Run scoped lint/type checks where feasible.
8. Write `result.md`, `execute_review.md`, `review_verdict.json`, `ack.json`, and update `slave_state.json`.

## Gates

- xmuse disabled by default.
- API is opt-in via `MEMORYOS_XMUSE_ENABLED=1`.
- Route feature ids resolve only through `master_state.features[].id`.
- Path-like feature ids cannot read filesystem paths.
- No endpoint or UI control writes `xmuse`, git, MemoryOS data, or process state.
- Tests use `tests/fixtures/xmuse/` and temp dirs, not live `xmuse` as durable expectations.
- v3 default, v1 fallback, v2 recall opt-in, kernel opt-in, and SQLite authority are unchanged.

