# phase: phase-10

status=DONE

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`

Active goal:

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Tests added:

- `tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor`
- `tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata`
- `tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice`

Command run:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice -q
```

Observed failure summary:

- `tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor` failed with `KeyError: 'session_diversified_anchor'` at `assert weak_hit.rank_features["session_diversified_anchor"] == 1.0`.
- `tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata` failed with `KeyError: 'recall_evidence_packets'` at `assert package.metadata["recall_evidence_packets"]`.
- `tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice` failed with `KeyError: 'recall_evidence_packets'` at `packets = report["v3_context"]["metadata"]["recall_evidence_packets"]`.

Full focused RED result:

```text
3 failed in 4.96s
```

RED validity:

The focused tests import and execute successfully. Failures are assertion/key failures caused by missing session-diversity rank features and missing recall packet metadata in the searcher, recall pipeline, and v3 public benchmark report path. No production code was modified.
