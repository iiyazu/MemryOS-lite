# phase: phase-13

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

RED evidence only. Production implementation was not changed.

| Command | Exit code | Short failure reason |
|---|---:|---|
| `uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_updates_existing_core_block_in_place_with_history -q` | 1 | Promotion creates a second live `human` core block; expected in-place update and history. |
| `uv run pytest tests/test_memory_lifecycle.py::test_archival_to_core_candidate_rejects_duplicate_label_conflict -q` | 1 | Duplicate live labels are not rejected; lifecycle silently applies the candidate. |
| `uv run pytest tests/test_core_memory_store.py::test_core_memory_store_update_requires_audit_metadata -q` | 1 | Direct store update without audit metadata does not raise and mutates the block. |
| `uv run pytest tests/test_core_memory_store.py::test_read_only_core_block_rejects_store_update_and_delete -q` | 1 | Store update boundary lacks audited mutation arguments, raising `TypeError` before read-only enforcement. |
| `uv run pytest tests/test_context_composer.py::test_v3_composer_renders_approved_core_promotion_with_provenance -q` | 1 | v3 composer renders the original core value without promotion provenance because approved promotion is not updating the live block. |
