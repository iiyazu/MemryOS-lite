# xmuse-core-state-extraction Result

Feature: `xmuse-core-state-extraction`
Branch: `feat/xmuse-core-state-extraction`
Worktree: `/home/iiyatu/projects/python/memoryOS-xmuse-core-state-extraction`
Head before feature work: `5f69b712a3adb22e9840dc211d1ff200c7f68ecb`

## Summary

Implemented the approved control-plane migration slice by adding `src/xmuse_core/core` and delegating the stable state/status subset from `xmuse/hermes_hardening.py` through that package.

## Changed

- Added `xmuse_core.core.paths` for controller path/display helpers.
- Added `xmuse_core.core.schema` for Master state validation constants and `validate_master_state()`.
- Added `xmuse_core.core.state` for read-only Master state loading and active controller resolution.
- Added `xmuse_core.core.status` for pure queue/status payload and Markdown builders.
- Kept `xmuse/hermes_hardening.py` as the compatibility facade.
- Preserved merge gate behavior by injecting shim-level `validate_merge_queue_gate()` into core status derivation.
- Added direct `tests/test_xmuse_core_*.py` coverage and shim delegation compatibility tests.
- Added feature-local baseline, dependency map, plan, dry-run validator, result, review, ACK, and slave state evidence.

## Not Changed

- No `xmuse/master_state.json` schema change.
- No writes to `xmuse/master_status.*`, `xmuse/master/features/**`, or `xmuse/approvals/**`.
- No `xmuse/__init__.py` or `src/xmuse/`.
- No MemoryOS product logic, retrieval, store, engine, eval, benchmark, or archive changes.
- No runner/framework/memory adapter dependency.
- No benchmark improvement claim.

## Verification Evidence

- `uv run pytest tests/test_xmuse_core_*.py -q` -> `12 passed in 0.06s`
- `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q` -> `117 passed in 0.48s`
- `uv run ruff check src/xmuse_core xmuse/hermes_hardening.py xmuse/hermes_reporter.py tests/test_hermes_*.py tests/test_xmuse_core_*.py` -> `All checks passed!`
- `uv run mypy src/xmuse_core` -> `Success: no issues found in 6 source files`
- `python3 -m py_compile $(find src/xmuse_core -name '*.py' -print | sort) xmuse/hermes_hardening.py xmuse/hermes_reporter.py` -> pass
- `bash -n xmuse/god_launcher.sh` -> pass
- no-start reporter import smoke -> `xmuse/master_state.json`
- `python3 xmuse/hermes_hardening.py --help` -> imports cleanly and prints CLI usage

## Full Regression Note

`uv run pytest -q` was attempted and interrupted after repeated unrelated product benchmark failures:

```text
6 failed, 514 passed, 1 warning in 2919.03s (0:48:39)
```

All reported failures were in MemoryOS public benchmark or LongMemEval integration tests and had the same root cause: `FastEmbedClient()` attempted to download model metadata from Hugging Face and raised `httpx.ConnectTimeout`. The failing paths were under `src/memoryos_lite/public_benchmarks.py`, `src/memoryos_lite/engine.py`, and `src/memoryos_lite/retrieval/providers/fastembed_client.py`, which are explicitly outside this control-plane migration's allowed product-code scope.

The literal blueprint command `python3 -m py_compile src/xmuse_core ...` was also checked and fails because `py_compile` does not accept a directory path. The file-list form above is the equivalent successful static compile check.

## Risks

- The runtime script needs a small `src` path bootstrap for raw importlib execution from `xmuse/hermes_reporter.py`; this is intentional and covered by the no-start smoke.
- `xmuse/jobs/xmuse-core-state-extraction.json` is absent in this worktree; dispatch proceeded from the feature-local blueprint and contract.
- Full regression is blocked by external model download timeouts in unrelated MemoryOS benchmark tests, not by `xmuse_core` or Hermes compatibility changes.

## Blast Radius

- `control_plane_only`: true
- `state_schema_change`: false
- `launcher_change`: false
- `reporter_change`: false
- `migration_required`: true
- `product_code_change`: false
- `memoryos_runtime_change`: false
