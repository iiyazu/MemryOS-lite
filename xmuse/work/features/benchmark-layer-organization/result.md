# Result: benchmark-layer-organization

feature_id: benchmark-layer-organization
status: bounded_slice_complete_full_blueprint_incomplete
updated_at: 2026-05-24T16:06:24Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
head: 3b2a9730e8eb6cd1466ba42516083df5fbb723dc
commit: 3b2a973 feat: expose signed recall packet offsets

## Implemented Slice

Implemented a Phase 0/1 diagnostic improvement for same-session recall packets:

- `RecallMemorySearcher` now includes `packet_member_neighbor_offsets` in packet metadata.
- Offset semantics are signed relative to the packet anchor:
  - previous neighbor: negative;
  - anchor: `0`;
  - next neighbor: positive.
- `RecallPipeline` now serializes the same offset metadata in `recall_evidence_packets`.
- Existing v3 context trace plumbing preserves the selected recall item metadata in `final_context_trace`.

No benchmark-specific case ids, expected-source shortcuts, hard-coded answers, or dataset string overfitting were introduced.

## RED Evidence

Command:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_records_signed_packet_member_offsets tests/test_recall_pipeline.py::test_recall_pipeline_exposes_signed_packet_member_offsets tests/test_context_composer.py::test_v3_composer_final_trace_preserves_signed_packet_member_offsets -q
```

Result before implementation:

```text
3 failed in 6.47s
```

Expected failure reason:

- all three tests failed with `KeyError: 'packet_member_neighbor_offsets'`.

## GREEN Evidence

Command:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_records_signed_packet_member_offsets tests/test_recall_pipeline.py::test_recall_pipeline_exposes_signed_packet_member_offsets tests/test_context_composer.py::test_v3_composer_final_trace_preserves_signed_packet_member_offsets -q
```

Result after implementation:

```text
3 passed in 3.36s
```

## Focused Verification

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

Result:

```text
19 passed in 10.81s
```

```bash
uv run pytest tests/test_context_composer.py -q
```

Result:

```text
14 passed in 29.55s
```

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Result:

```text
91 passed in 131.00s (0:02:11)
```

```bash
uv run ruff check src/memoryos_lite/retrieval/episode_searcher.py src/memoryos_lite/retrieval/recall_pipeline.py tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_context_composer.py
```

Result:

```text
All checks passed!
```

```bash
uv run python - <<'PY'
from memoryos_lite.config import Settings
s = Settings()
print('resolved_memory_arch', s.resolved_memory_arch)
print('resolved_recall_pipeline', s.resolved_recall_pipeline)
print('resolved_agent_kernel', s.resolved_agent_kernel)
print('v1_fallback', Settings(memoryos_memory_arch='v1').resolved_memory_arch)
PY
```

Result:

```text
resolved_memory_arch v3
resolved_recall_pipeline v1
resolved_agent_kernel off
v1_fallback v1
```

## Evals

Public full-chain evals were not run in this bounded Slave turn:

- LongMemEval 50 with LLM answer/judge: not run.
- LoCoMo 50 with LLM answer/judge: not run.
- Hard eval gate: not run.
- Full suite: not run after this change.

No LongMemEval or LoCoMo score movement is claimed. This result is a diagnostic/layer-organization improvement only.

## Residual Work

- Complete broader Phase 2 composer/drop accounting review if Master wants full blueprint coverage beyond this diagnostic slice.
- Run full regression gates and public full-chain evals with comparison reports before any usable/full feature ack.
- Record fixed-slice fail-to-pass/pass-to-fail movement only after public comparison evals exist.
