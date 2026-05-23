# phase: phase-12

# Phase 12 RED Result

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.

Command:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Result: RED.

Observed failure:

- `assert [item.text for item in archival_items] == ["approved archival fact"]`
- Actual value: `[]`

Interpretation:

- Approved `archive_write` persisted archival memory, but same-session v3 archival eligibility did not yet select the bridged `apsg_{memory_id}` passage as an archival context item.
