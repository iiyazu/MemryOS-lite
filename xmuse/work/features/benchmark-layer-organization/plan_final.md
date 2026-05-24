# Benchmark Layer Organization Implementation Plan

feature_id: benchmark-layer-organization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve LoCoMo-style packet/neighbor diagnostics by preserving signed neighbor offsets from recall packets through v3 context trace metadata.

**Architecture:** Add explicit packet member offset metadata at the recall search layer, serialize it through `RecallPipeline`, and rely on existing `V3ContextComposer` accounting to preserve selected item metadata in final context trace rows. The change is diagnostic-only and does not alter default architecture, v2 opt-in behavior, v1 fallback, kernel defaults, or benchmark score targets.

**Tech Stack:** Python 3.11+, pytest, MemoryOS Lite recall/v3 context contracts.

---

### Task 1: RED Tests For Signed Packet Offsets

**Files:**
- Modify: `tests/test_episode_retrieval.py`
- Modify: `tests/test_recall_pipeline.py`
- Modify: `tests/test_context_composer.py`

- [ ] **Step 1: Add failing recall searcher test**

Add a test that builds a D1 packet around an anchor with one previous and one next message. Assert `packet_member_neighbor_offsets` is present and equals:

```python
[
    {"message_id": "d1_prev", "neighbor_offset": -1},
    {"message_id": "d1_anchor", "neighbor_offset": 0},
    {"message_id": "d1_next", "neighbor_offset": 1},
]
```

- [ ] **Step 2: Add failing recall pipeline test**

Add a test that uses `RecallPipeline.build_context()` and asserts the same offset metadata is visible in `package.metadata["recall_evidence_packets"]` and selected evidence metadata.

- [ ] **Step 3: Add failing v3 composer test**

Add a test that opts into `v3` context construction and asserts the selected recall row in `metadata["final_context_trace"]` contains `packet_member_neighbor_offsets`.

- [ ] **Step 4: Verify RED**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py::test_recall_searcher_records_signed_packet_member_offsets tests/test_recall_pipeline.py::test_recall_pipeline_exposes_signed_packet_member_offsets tests/test_context_composer.py::test_v3_composer_final_trace_preserves_signed_packet_member_offsets -q
```

Expected: all three tests fail because `packet_member_neighbor_offsets` is missing.

### Task 2: Minimal Implementation

**Files:**
- Modify: `src/memoryos_lite/retrieval/episode_searcher.py`
- Modify: `src/memoryos_lite/retrieval/recall_pipeline.py`

- [ ] **Step 1: Add packet member offset metadata**

In `_packet_metadata`, compute each member's signed offset relative to the anchor position and include:

```python
"packet_member_neighbor_offsets": [
    {"message_id": entry.message_id, "neighbor_offset": entry.position - anchor.position}
    for entry in member_entries
],
```

- [ ] **Step 2: Serialize offsets in packet summaries**

In `_packet_summaries`, include:

```python
"packet_member_neighbor_offsets": list(
    hit.packet_metadata.get("packet_member_neighbor_offsets", [])
),
```

- [ ] **Step 3: Verify GREEN**

Run the RED command again. Expected: pass.

### Task 3: Focused Regression

- [ ] **Step 1: Run focused recall tests**

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

- [ ] **Step 2: Run focused composer tests**

```bash
uv run pytest tests/test_context_composer.py -q
```

- [ ] **Step 3: Run focused public diagnostics tests**

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

- [ ] **Step 4: Check defaults with config tests or targeted assertions**

Use existing tests or a small Python check to confirm default memory arch remains `v3`, v1 fallback remains configurable, recall pipeline v2 remains opt-in, and agent kernel default is unchanged.

### Task 4: Handoff Artifacts

**Files:**
- Create or update: `xmuse/work/features/benchmark-layer-organization/result.md`
- Create or update: `xmuse/work/features/benchmark-layer-organization/execute_review.md`
- Create or update: `xmuse/work/features/benchmark-layer-organization/review_verdict.json`
- Create or update: `xmuse/work/features/benchmark-layer-organization/ack.json`
- Update: `xmuse/work/features/benchmark-layer-organization/slave_state.json`

- [ ] **Step 1: Record commands and outcomes in `result.md`**
- [ ] **Step 2: Self-review invariants and leakage criteria in `execute_review.md`**
- [ ] **Step 3: Write `review_verdict.json`**
- [ ] **Step 4: Write `ack.json` with `ack_level` based on actual verification**
- [ ] **Step 5: Update `slave_state.json`**
