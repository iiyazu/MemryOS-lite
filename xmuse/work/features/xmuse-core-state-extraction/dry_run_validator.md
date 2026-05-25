# xmuse-core-state-extraction Dry-Run Validator

Feature: `xmuse-core-state-extraction`
Recorded: `2026-05-25T04:16:33Z`

## files_to_change

- Add `src/xmuse_core/__init__.py`
- Add `src/xmuse_core/core/__init__.py`
- Add `src/xmuse_core/core/paths.py`
- Add `src/xmuse_core/core/schema.py`
- Add `src/xmuse_core/core/state.py`
- Add `src/xmuse_core/core/status.py`
- Modify `xmuse/hermes_hardening.py`
- Add `tests/test_xmuse_core_schema.py`
- Add `tests/test_xmuse_core_state.py`
- Add `tests/test_xmuse_core_status.py`
- Modify `tests/test_hermes_master_state.py`
- Add or update feature-local artifacts under `xmuse/work/features/xmuse-core-state-extraction/`

## active_sources_before

- Active state source: `xmuse/master_state.json`
- Active runtime facade: `xmuse/hermes_hardening.py`
- Active reporter: `xmuse/hermes_reporter.py`
- Active launcher: `xmuse/god_launcher.sh`
- Status outputs: `xmuse/master_status.json`, `xmuse/master_status.md`

## active_sources_after

- Active state source remains `xmuse/master_state.json`.
- Active runtime facade remains `xmuse/hermes_hardening.py`.
- Reporter and launcher entrypoints remain unchanged.
- `xmuse/hermes_hardening.py` delegates the extracted state/status subset to `xmuse_core.core`.
- Status file writes remain in `xmuse/hermes_hardening.py::write_master_status()`.

## legacy_audit_only_sources

- `xmuse/legacy/root-loop/state.json` remains audit-only.
- `xmuse/state.json` remains a legacy fallback only when no Master state exists.
- This feature does not reactivate legacy root-loop as an execution source.

## expected_status_projection

- Features in `planned`, active, review, held, blocked, and merged states map to the same queues as before.
- `ready_for_merge` and `merge_requested` features remain blocked in core when no merge gate validator is injected.
- The shim injects the existing `validate_merge_queue_gate(loop, feature)` to preserve current merge queue and blocked/error semantics.
- Markdown status keeps the existing status heading and count fields.

## rollback_plan

1. Revert this feature commit from `feat/xmuse-core-state-extraction`.
2. Restore direct implementations of `validate_master_state()`, `resolve_active_controller()`, `derive_master_queues()`, and Markdown status construction in `xmuse/hermes_hardening.py`.
3. Remove `src/xmuse_core/**` imports from `xmuse/hermes_hardening.py`.
4. Leave legacy root-loop audit-only; do not activate it as the rollback source.
5. Rerun focused Hermes tests and no-start reporter smoke before any Master activation decision.

## blast_radius

- `control_plane_only`: true
- `state_schema_change`: false
- `launcher_change`: false
- `reporter_change`: false
- `migration_required`: true
- `product_code_change`: false
- `memoryos_runtime_change`: false

## quarantine_status

This dry-run validates a staged shim delegation path only. It is not merge approval and does not request merge queue placement.
