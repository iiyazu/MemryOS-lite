# phase: phase-10

# Phase 10 TDD Plan: Recall Memory Reliability

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Read-order confirmation: `.hermes-loop/work/phase-10/context_bundle.md` was read first, followed by `.hermes-loop/work/phase-10/brainstorm.md`, then `.hermes-loop/work/phase-10/god_dispatch.json`, then relevant Phase 9 evidence, recall code/tests, public benchmark diagnostics, and Letta reference files.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

No commits from this lane. Keep all implementation changes narrow and uncommitted for review.

## Files Likely To Modify

- `tests/test_episode_retrieval.py`: add RED unit tests for session-diverse direct selection, neighbor session boundaries, and LongMemEval-style strong-hit stability.
- `tests/test_recall_pipeline.py`: add RED integration test for packet metadata in `ContextPackage`.
- `tests/test_public_benchmarks.py`: add RED public/v3 test proving packet diagnostics flow through real benchmark reporting and kernel remains default-off.
- `src/memoryos_lite/retrieval/episode_searcher.py`: add bounded session-aware direct-hit selection and packet metadata on `EpisodeHit`.
- `src/memoryos_lite/retrieval/recall_pipeline.py`: serialize packet metadata into evidence and package metadata.
- `src/memoryos_lite/context_composer.py`: preserve packet metadata in v3 recall items and component accounting.
- `src/memoryos_lite/engine.py`: preserve packet metadata when converting v3 packages to eval/public `ContextPackage`.
- `src/memoryos_lite/public_benchmarks.py`: append packet/report fields only if needed after the public diagnostic RED test.
- `src/memoryos_lite/public_case_diagnostics.py`: append packet/session diagnostic fields only if needed after the public diagnostic RED test.

Do not modify `state.json`, `blueprint.md`, `config.json`, `brainstorm.md`, docs outside phase artifacts, or benchmark source data.

## RED

- [ ] Add a failing unit test in `tests/test_episode_retrieval.py`.

Test name:

```python
def test_recall_searcher_session_diversity_keeps_weak_same_session_anchor():
```

Test shape:

```python
def test_recall_searcher_session_diversity_keeps_weak_same_session_anchor():
    entries = [
        _recall_entry(
            "d1_weak",
            "Caroline started psychology classes after considering her education.",
            1,
        ),
        _recall_entry("d2_strong", "Caroline education fields career research.", 2),
        _recall_entry("d3_strong", "Caroline education fields career support.", 3),
        _recall_entry("d4_strong", "Caroline education fields career planning.", 4),
        _recall_entry("d5_strong", "Caroline education fields career options.", 5),
    ]
    for index, entry in enumerate(entries, start=1):
        entry.temporal_scope["benchmark_session_id"] = f"D{index}"

    hits = RecallMemorySearcher().search(
        entries,
        "What fields would Caroline pursue in her education?",
        top_k=3,
        preserve_neighbors=True,
    )

    assert "d1_weak" in [hit.episode.message_id for hit in hits]
    weak_hit = next(hit for hit in hits if hit.episode.message_id == "d1_weak")
    assert weak_hit.rank_features["session_diversified_anchor"] == 1.0
    assert weak_hit.rank_features["packet_rank"] >= 0.0
```

Run:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor -q
```

Expected RED:

- Fails because `d1_weak` is not in selected hits or because packet/session-diversity rank features are absent.

- [ ] Add a failing packet metadata integration test in `tests/test_recall_pipeline.py`.

Test name:

```python
def test_recall_pipeline_emits_session_packet_metadata(tmp_path):
```

Test shape:

```python
def test_recall_pipeline_emits_session_packet_metadata(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    for message_id, session_marker, content in [
        ("d1_1", "D1", "Caroline is weighing psychology classes."),
        ("d1_2", "D1", "Caroline said counseling could help people."),
        ("d2_1", "D2", "Caroline education fields career options distractor."),
        ("d3_1", "D3", "Caroline education fields career planning distractor."),
    ]:
        store.add_message(
            Message(
                id=message_id,
                session_id="ses",
                role=Role.USER,
                content=content,
                metadata={"benchmark_session_id": session_marker},
                token_count=len(content.split()),
            )
        )

    package = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build_context(
        session_id="ses",
        task="What fields would Caroline pursue in education?",
        budget=200,
    )

    assert package.metadata["recall_evidence_packets"]
    assert "D1" in package.metadata["recall_planned_session_ids"]
    assert any(
        evidence.metadata.get("packet_session_id") == "D1"
        for evidence in package.retrieved_evidence
    )
```

Run:

```bash
uv run pytest tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata -q
```

Expected RED:

- Fails with missing `recall_evidence_packets`, missing `recall_planned_session_ids`, or missing per-evidence packet metadata.

- [ ] Add a public/v3 RED diagnostic test in `tests/test_public_benchmarks.py`.

Test name:

```python
def test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice(tmp_path):
```

Test assertions:

```python
report = results[0].to_report()
packets = report["v3_context"]["metadata"]["recall_evidence_packets"]
assert packets
assert any(packet["packet_session_id"] == "D1" for packet in packets)
assert report["case_diagnostics"]["retrieved_evidence_ids"]
assert report["case_diagnostics"]["source_hit_semantics"] == "final_projection_source_overlap"
assert report["kernel_trace_events"] == []
```

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice -q
```

Expected RED:

- Fails because `recall_evidence_packets` are not present in `v3_context.metadata`.

- [ ] Run the initial focused RED set.

Command:

```bash
uv run pytest \
  tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor \
  tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata \
  tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice \
  -q
```

Expected RED:

- At least one test fails before production changes. Record exact failure text in phase execution notes.

## GREEN

- [ ] Implement the smallest searcher change in `src/memoryos_lite/retrieval/episode_searcher.py`.

Implementation requirements:

- Extend `EpisodeHit` with packet metadata fields or a single `packet_metadata: dict[str, object]`.
- Add deterministic packet ids from anchor message id plus benchmark session id.
- Add a private direct-hit selector that, when `preserve_neighbors=True` and benchmark sessions exist, keeps high-scoring direct hits while reserving bounded slots for distinct benchmark sessions.
- Mark diversified anchors with `rank_features["session_diversified_anchor"] = 1.0`.
- Add `packet_anchor_message_id`, `packet_session_id`, `packet_member_message_ids`, and `packet_reason` to diagnostics metadata.
- Keep default `EpisodeSearcher.search()` behavior unchanged unless the caller opts into neighbor/session preservation.

Focused command:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_session_diversity_keeps_weak_same_session_anchor -q
```

Expected GREEN:

- The weak same-session anchor is selected and has packet/session-diversity rank features.

- [ ] Preserve neighbor and strong-hit guards.

Commands:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_expands_neighbors_and_dedupes_message_ids -q
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_prioritizes_direct_hits_before_neighbors -q
```

Expected GREEN:

- Existing neighbor dedupe and direct-hit priority behavior still pass.

- [ ] Implement packet propagation in `src/memoryos_lite/retrieval/recall_pipeline.py`.

Implementation requirements:

- Add `recall_evidence_packets`, `recall_candidate_session_ids`, and `recall_planned_session_ids` to `ContextPackage.metadata`.
- Copy packet metadata into every `ContextEvidence.metadata`.
- Include packet metadata on budget-drop diagnostics when a packet member is dropped.
- Preserve existing metadata field names and meanings.

Focused command:

```bash
uv run pytest tests/test_recall_pipeline.py::test_recall_pipeline_emits_session_packet_metadata -q
```

Expected GREEN:

- Packet metadata appears on package and evidence objects.

- [ ] Preserve v3 composer and service conversion.

Files:

- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`

Implementation requirements:

- v3 recall layer item metadata must retain packet fields from recall evidence.
- `ContextPackageV3.metadata` must include `recall_evidence_packets`, `recall_candidate_session_ids`, and `recall_planned_session_ids`.
- `_context_package_from_v3()` must copy those fields back to `ContextPackage.metadata`.

Focused command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_reports_recall_packet_diagnostics_for_locomo_session_slice -q
```

Expected GREEN:

- Public report exposes packet metadata via the real v3/public benchmark path.

- [ ] Add append-only public diagnostic exposure only if the previous test cannot read packets through `v3_context.metadata`.

Files:

- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`

Implementation requirements:

- Do not change existing `source_hit` or failure-class semantics.
- Add only append-only fields such as `recall_evidence_packets`, `recall_candidate_session_ids`, and `recall_planned_session_ids`.
- Keep partial and final report schema parity.

Focused command:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_partial_and_final_reports_have_diagnostic_schema_parity -q
```

Expected GREEN:

- Partial and final reports contain the same diagnostic schema.

## REFACTOR

- [ ] Keep the implementation in existing modules; do not add broad new architecture.
- [ ] Rename helper functions for clarity if needed, but avoid unrelated refactors.
- [ ] Ensure packet metadata is constructed once and reused rather than reconstructed differently in searcher, pipeline, composer, and eval code.
- [ ] Run focused regression tests.

Commands:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
uv run pytest tests/test_public_benchmarks.py -q
uv run ruff check .
```

Expected GREEN:

- Focused tests pass.
- Ruff reports `All checks passed!`.

## Smoke

- [ ] Run deterministic no-LLM LoCoMo smoke first.

Command:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Expected output:

- A final report under `.memoryos/evals/`.
- Rows include `episode_candidate_message_ids`, `planned_evidence_message_ids`, `v3_diagnostics`, `case_diagnostics`, and packet metadata via `v3_context.metadata`.
- `kernel_trace_events` remains empty unless `MEMORYOS_AGENT_KERNEL=v1` is explicitly set.

- [ ] Produce phase-local case-level artifacts during execute/review lanes.

Artifacts:

- `.hermes-loop/work/phase-10/case_matrix.md`
- `.hermes-loop/work/phase-10/result.md`
- `.hermes-loop/work/phase-10/execute_review.md`
- `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json`
- `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json`

Each report must list:

- fail-to-pass cases;
- pass-to-fail cases;
- unchanged-fail cases;
- retrieval candidate movement;
- planned evidence movement;
- selected/rendered evidence movement;
- failure-class movement;
- packet/session movement;
- cause and disposition for every pass-to-fail.

- [ ] Run full-chain 30-case gates if LLM provider access is available.

Commands:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge
```

Expected gate result:

- LoCoMo 30 shows same-case explainable recall/session signal.
- LongMemEval 30 shows no material collapse.
- Full-chain result is not accepted if reports are projected/no-judge or `judge_done=0`.

If provider access is unavailable:

- Record the blocker in `result.md`.
- Keep deterministic no-LLM smoke as fallback evidence.
- Do not mark the milestone gate satisfied.

## Review

- [ ] Run baseline verification.

Commands:

```bash
uv run pytest -q
uv run ruff check .
```

Expected GREEN:

- Full pytest passes.
- Ruff passes.

- [ ] Run targeted default/fallback guards.

Commands:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off -q
```

Expected GREEN:

- Explicit v1 fallback has no v3 case context.
- Kernel trace remains default-off.
- Settings default agent kernel remains `off`.

- [ ] Review overfitting constraints before ACK.

Checklist:

- No case ids, expected answer strings, expected source ids, or benchmark-specific terms influence retrieval behavior.
- No scoring semantics changed.
- No v1 fallback regression.
- No default kernel enablement.
- `source_hit` is still reported as final projection source overlap.
- `case_matrix.md` separates retrieval/source metrics from judged answer quality.
- Every pass-to-fail has cause and disposition.
- No commits were made by this lane.

decision=ready_for_execute_after_plan_review
