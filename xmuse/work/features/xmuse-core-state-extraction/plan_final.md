# xmuse-core-state-extraction Plan

Feature: `xmuse-core-state-extraction`
Branch: `feat/xmuse-core-state-extraction`
Worktree: `/home/iiyatu/projects/python/memoryOS-xmuse-core-state-extraction`

## Scope

Extract the stable Master state/status subset from `xmuse/hermes_hardening.py` into `src/xmuse_core/core` while preserving the existing runtime script surface and control-plane semantics.

## Real Files

- `src/xmuse_core/__init__.py`
- `src/xmuse_core/core/__init__.py`
- `src/xmuse_core/core/paths.py`
- `src/xmuse_core/core/schema.py`
- `src/xmuse_core/core/state.py`
- `src/xmuse_core/core/status.py`
- `xmuse/hermes_hardening.py`
- `tests/test_xmuse_core_schema.py`
- `tests/test_xmuse_core_state.py`
- `tests/test_xmuse_core_status.py`
- `tests/test_hermes_master_state.py`
- `xmuse/work/features/xmuse-core-state-extraction/*`

## RED -> GREEN -> REFACTOR Tasks

1. Add direct core schema/path/state/status tests that fail before `src/xmuse_core` exists.
2. Add compatibility tests proving `xmuse/hermes_hardening.py` delegates validation, active controller resolution, queue derivation, and status Markdown through core.
3. Implement the minimal core modules and shim delegation needed to pass those tests.
4. Preserve merge queue semantics by injecting the existing shim-level `validate_merge_queue_gate()` into core status builders.
5. Refactor only enough to keep the core package free of writes, git/subprocess, runner starts, MemoryOS imports, and direct merge gate imports.

## Non-Goals

- No Master state schema change.
- No Master-owned status, approval, or review artifact writes.
- No MemoryOS product logic changes.
- No runner/framework/memory adapter work.
- No migration activation or merge approval.
- No benchmark score targets.

## Verification Gates

- `uv run pytest tests/test_xmuse_core_*.py -q`
- `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q`
- `uv run ruff check src/xmuse_core xmuse/hermes_hardening.py xmuse/hermes_reporter.py tests/test_hermes_*.py tests/test_xmuse_core_*.py`
- `python3 -m py_compile $(find src/xmuse_core -name '*.py' -print | sort) xmuse/hermes_hardening.py xmuse/hermes_reporter.py`
- `bash -n xmuse/god_launcher.sh`
- no-start reporter import smoke
- `uv run pytest -q`

## Usable ACK Conditions

ACK may be usable only when direct core tests pass, compatibility tests pass, static checks pass, no-start smoke passes, full regression passes or any unrelated failure is documented, dry-run validator and rollback plan exist, and review verdict is PASS.
