# phase: phase-12

# Phase 12 Result

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.

## Summary

Phase 12 implemented the scoped tool-written archival memory bridge:

- approved `archive_write` now creates an exact-scope session attachment for the written archive when missing;
- `archive_write` now ensures the session row exists before creating that attachment if the tool path is invoked before a normal service-created session row exists;
- archival passage hits now preserve passage metadata into v3 archival items;
- same-session v3 context now selects the bridged `apsg_{memory_id}` passage as archival evidence;
- legacy `MemoryOSService.build_context()` now exposes the archival item through `retrieved_evidence` with archival origin metadata.

## Changed Chain

- `store`: verified existing archival persistence, update, delete, and attachment logic;
- `retrieval`: changed archival hit metadata propagation in `src/memoryos_lite/retrieval/archival_searcher.py`;
- `context_composer`: verified existing scoped archival selection and legacy projection;
- `kernel_loop`: changed `archive_write` to create an idempotent session attachment;
- `public_eval`: not applicable; no public benchmark code changed;
- `answer_projection`: verified only through existing legacy projection path;
- `ingest`: not applicable.

## Verification

RED:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Focused GREEN/regression:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_archival_store.py tests/test_memory_lifecycle.py tests/test_context_composer.py -q
```

Baseline:

```bash
uv run pytest -q
uv run ruff check .
```

Results:

- focused regression slice: `30 passed`
- full suite: `446 passed, 1 warning`
- ruff: clean

## Case-Level Eval

Not applicable for promotion in this phase.

- `longmemeval`: `limit=0`
- `locomo`: `limit=0`

Phase 11 LoCoMo debt remains visible and unchanged:

- `conv-26_qa_028`
- `conv-26_qa_005`
- `conv-26_qa_003`
- `conv-26_qa_004`
- `conv-26_qa_006`
- `conv-26_qa_008`
- `conv-26_qa_016`
- `conv-26_qa_019`
- `conv-26_qa_020`
- `conv-26_qa_024`
- `conv-26_qa_025`

## Notes

- No LongMemEval/LoCoMo improvement is claimed.
- v1 fallback remained unchanged.
- v3 default remained unchanged.
- `MEMORYOS_AGENT_KERNEL=v1` remained opt-in.
