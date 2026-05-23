# phase: phase-12

# Phase 12 Execute Review

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.

## What real chain changed?

The real tool-write archival chain changed. `archive_write` now ensures the session scope exists, creates a same-session archive attachment when needed, and archival hit metadata now preserves passage provenance into v3 archival items. That makes the written archival memory visible through the real v3 composer path, not just as a recent tool message.

## What is still demo-only or partial?

Nothing in the Phase 12 archival bridge remains demo-only. Public benchmark behavior was not changed, so benchmark promotion evidence is not applicable here. Phase 11 LoCoMo debt remains unresolved and visible.

## What tests proved the behavior?

- `tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item`
- `tests/test_agent_kernel.py tests/test_archival_store.py tests/test_memory_lifecycle.py tests/test_context_composer.py -q`
- `uv run pytest -q`
- `uv run ruff check .`

## Which benchmark cases moved or regressed?

None were rerun in this phase. No benchmark improvement or regression claim is being made.

## Did v1 fallback, v3 default, and kernel opt-in remain intact?

Yes.

- v1 fallback was untouched.
- v3 remained the default memory architecture.
- `MEMORYOS_AGENT_KERNEL=v1` remained opt-in only.
