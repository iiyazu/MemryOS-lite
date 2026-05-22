# phase: phase-3

## Plan: Letta-Style Core Memory Blocks

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

This plan uses `.hermes-loop/work/phase-3/context_bundle.md` as the required handoff and treats old phase-3 result/ack files as stale inventory only.

Preservation constraints:

- `MEMORYOS_MEMORY_ARCH=v3` remains the default architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit legacy fallback and must not include v3 core blocks.
- `MEMORYOS_AGENT_KERNEL` remains default `off`; `MEMORYOS_AGENT_KERNEL=v1` remains opt-in only.

## File Map

Modify only during execute lane:

- `src/memoryos_lite/v3_contracts.py`: add `CoreMemoryBlock.read_only` and `CoreMemoryBlock.tags`.
- `src/memoryos_lite/store.py`: persist `read_only` and `tags_json`; update migration head stamping.
- `alembic/versions/0007_add_core_block_read_only_tags.py`: migrate existing SQLite rows with safe defaults.
- `src/memoryos_lite/core_memory.py`: add create fields, read-only enforcement, structured render helper.
- `src/memoryos_lite/context_composer.py`: consume structured core rendering and expose diagnostics.
- `tests/test_v3_contracts.py`: block model defaults and serialization.
- `tests/test_core_memory_store.py`: persistence, history snapshots, migration head.
- `tests/test_core_memory_service.py`: read-only mutation rejection, limit behavior, renderer output.
- `tests/test_context_composer.py`: structured v3 core items and budget diagnostics.
- `tests/test_engine.py`: replace stale core-ignore test with v3 inclusion and explicit v1 fallback isolation.
- `tests/test_public_benchmarks.py`: append-only v3 diagnostics with visible core layer inclusion/cost.

Do not modify docs, benchmark data, Hermes state, blueprint, answer prompts, or public benchmark scoring semantics in Phase 3 unless a RED test proves the existing diagnostic payload cannot satisfy the contract.

## RED

- [ ] Add `tests/test_v3_contracts.py::test_core_memory_block_has_letta_style_defaults_and_serialization`.

```python
def test_core_memory_block_has_letta_style_defaults_and_serialization():
    block = CoreMemoryBlock(
        id="core_1",
        label="human",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=200,
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
        metadata={"priority": "stable"},
        tags=["profile", "benchmark"],
    )

    assert block.read_only is False
    assert block.tags == ["profile", "benchmark"]
    data = block.model_dump(mode="json")
    assert data["read_only"] is False
    assert data["tags"] == ["profile", "benchmark"]
    assert data["source_refs"][0]["source_id"] == "msg_1"
    assert data["metadata"] == {"priority": "stable"}
```

Run:

```bash
uv run pytest tests/test_v3_contracts.py::test_core_memory_block_has_letta_style_defaults_and_serialization -q
```

Expected RED: fails because `CoreMemoryBlock` lacks `read_only` and/or `tags`.

- [ ] Update `tests/test_core_memory_store.py::test_core_memory_store_round_trip_history_and_soft_delete` to assert persistence and history snapshots.

Add these assertions after create/history:

```python
assert created.read_only is True
assert created.tags == ["profile", "source-backed"]
loaded = store.get_core_memory_block("core_1")
assert loaded is not None
assert loaded.read_only is True
assert loaded.tags == ["profile", "source-backed"]
add_event = store.list_core_memory_history("core_1")[-1]
assert add_event.after["read_only"] is True
assert add_event.after["tags"] == ["profile", "source-backed"]
```

Set the block fixture fields:

```python
read_only=True,
tags=["profile", "source-backed"],
metadata={"scope": "human"},
```

Run:

```bash
uv run pytest tests/test_core_memory_store.py::test_core_memory_store_round_trip_history_and_soft_delete -q
```

Expected RED: fails because SQLite record/model round trip lacks those fields.

- [ ] Update `tests/test_core_memory_store.py::test_init_db_stamps_current_migration_head`.

Expected assertion:

```python
assert version == "0007_add_core_block_read_only_tags"
```

Run:

```bash
uv run pytest tests/test_core_memory_store.py::test_init_db_stamps_current_migration_head -q
```

Expected RED: fails until migration/stamping updates.

- [ ] Add `tests/test_core_memory_service.py::test_core_memory_service_rejects_read_only_mutations`.

```python
def test_core_memory_service_rejects_read_only_mutations(tmp_path):
    service = _service(tmp_path)
    ref = SourceRef(source_type="message", source_id="msg_1")
    block = service.create_block(
        label="profile",
        description="Stable user facts",
        value="Alice lives in Shanghai.",
        limit_tokens=20,
        source_refs=[ref],
        actor="agent",
        reason="seed profile",
        read_only=True,
    )

    with pytest.raises(ValueError, match="read-only core memory block"):
        service.append_block(block.id, "Alice prefers rail.", source_refs=[ref], actor="agent", reason="append")
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.replace_block(block.id, old="Shanghai", content="Suzhou", source_refs=[ref], actor="agent", reason="replace")
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.update_block(block.id, "Alice lives in Suzhou.", source_refs=[ref], actor="agent", reason="update")
    with pytest.raises(ValueError, match="read-only core memory block"):
        service.delete_block(block.id, source_refs=[ref], actor="agent", reason="delete")
```

Run:

```bash
uv run pytest tests/test_core_memory_service.py::test_core_memory_service_rejects_read_only_mutations -q
```

Expected RED: fails because read-only is not in the block contract and is not enforced.

- [ ] Replace renderer assertions in `tests/test_core_memory_service.py::test_core_memory_service_append_replace_update_and_render`.

Expected render evidence:

```python
rendered = render_core_memory_blocks([updated], tokenizer=FakeTokenizer())
assert "<memory_blocks>" in rendered.text
assert "<profile>" in rendered.text
assert "<description>\nStable user facts\n</description>" in rendered.text
assert "- read_only=false" in rendered.text
assert "- tokens_current=4" in rendered.text
assert "- tokens_limit=20" in rendered.text
assert "- tags=profile" in rendered.text
assert "- message:msg_1" in rendered.text
assert "<value>\nAlice lives in Suzhou.\n</value>" in rendered.text
assert rendered.metadata_by_block[updated.id]["label"] == "profile"
assert rendered.metadata_by_block[updated.id]["tokens_limit"] == 20
```

Also pass `tags=["profile"]` when creating the block.

Run:

```bash
uv run pytest tests/test_core_memory_service.py::test_core_memory_service_append_replace_update_and_render -q
```

Expected RED: fails because current renderer returns a plain string.

- [ ] Add `tests/test_context_composer.py::test_v3_composer_core_items_use_structured_render_and_diagnostics`.

```python
def test_v3_composer_core_items_use_structured_render_and_diagnostics(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    ref = _ref()
    CoreMemoryService(store, WordTokenizer()).create_block(
        label="human",
        description="Stable user facts",
        value="Alice prefers rail travel.",
        limit_tokens=20,
        source_refs=[ref],
        actor="user",
        reason="explicit user instruction",
        tags=["profile"],
        metadata={"scope": "benchmark"},
    )

    package = V3ContextComposer(store=store, settings=settings, tokenizer=WordTokenizer()).build(
        ContextComposerRequest(session_id="ses_1", task="What does Alice prefer?", budget=80)
    )

    core_items = [item for item in package.items if item.layer == "core"]
    assert len(core_items) == 1
    core_item = core_items[0]
    assert "<memory_blocks>" in core_item.text
    assert "<human>" in core_item.text
    assert core_item.metadata["label"] == "human"
    assert core_item.metadata["tags"] == ["profile"]
    assert core_item.metadata["metadata"] == {"scope": "benchmark"}
    assert core_item.metadata["tokens_limit"] == 20
    assert core_item.source_refs[0].source_id == "msg_1"
    core_diagnostics = [d for d in package.diagnostics if d.layer == "core"]
    assert core_diagnostics
    assert core_diagnostics[0].budget_tokens == core_item.estimated_tokens
    assert core_diagnostics[0].metadata["source_ref_count"] == 1
```

Run:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_core_items_use_structured_render_and_diagnostics -q
```

Expected RED: fails because composer uses `label: value` and sparse metadata.

- [ ] Replace `tests/test_engine.py::test_build_context_ignores_core_memory_blocks` with two explicit routing tests.

`tests/test_engine.py::test_v3_build_context_includes_core_memory_diagnostics`:

```python
def test_v3_build_context_includes_core_memory_diagnostics(service):
    session = service.create_session("core-memory-v3")
    service.store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_1",
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
            tags=["profile"],
            metadata={"scope": "human"},
        )
    )

    context = service.build_context(session.id, "用户住在哪里？", budget=200)

    assert context.metadata["memory_arch"] == "v3"
    assert context.metadata["v3_layer_counts"]["core"] == 1
    assert any("<memory_blocks>" in item for item in context.pinned_core)
    core_diagnostics = [d for d in context.metadata["v3_diagnostics"] if d["layer"] == "core"]
    assert core_diagnostics
    assert core_diagnostics[0]["metadata"]["tags"] == ["profile"]
```

`tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_core_memory_blocks`:

```python
def test_explicit_v1_build_context_excludes_v3_core_memory_blocks(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v1")
    service = MemoryOSService(settings=settings)
    session = service.create_session("core-memory-v1")
    service.store.create_core_memory_block(
        CoreMemoryBlock(
            id="core_1",
            label="profile",
            description="Stable user facts",
            value="Alice lives in Shanghai.",
            limit_tokens=100,
            source_refs=[SourceRef(source_type="message", source_id="msg_1")],
            tags=["profile"],
        )
    )

    context = service.build_context(session.id, "用户住在哪里？", budget=200)

    assert context.metadata.get("memory_arch") != "v3"
    assert "v3_diagnostics" not in context.metadata
    assert "Alice lives in Shanghai." not in context.model_dump_json()
```

Run:

```bash
uv run pytest tests/test_engine.py::test_v3_build_context_includes_core_memory_diagnostics tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_core_memory_blocks -q
```

Expected RED: v3 inclusion fails until structured diagnostics exist; v1 must stay green.

- [ ] Add `tests/test_public_benchmarks.py::test_public_benchmark_v3_core_diagnostics_are_append_only`.

Add imports:

```python
import memoryos_lite.public_benchmarks as public_benchmarks
from memoryos_lite.v3_contracts import CoreMemoryBlock, SourceRef
```

Test body:

```python
def test_public_benchmark_v3_core_diagnostics_are_append_only(tmp_path, monkeypatch):
    data_path = _write_single_locomo_case(
        tmp_path,
        sample_id="sample_core_diag",
        text="Alice prefers rail travel.",
        question="What does Alice prefer?",
        answer="rail travel",
    )
    original_run_baseline = public_benchmarks._run_baseline

    def seeded_run_baseline(baseline, case, messages, service, settings, budget_override=None):
        original_build_context = service.build_context

        def build_context_with_core(
            session_id,
            task,
            budget=None,
            retrieval_query=None,
            include_global_core=False,
        ):
            if service.store.get_core_memory_block("core_public_profile") is None:
                service.store.create_core_memory_block(
                    CoreMemoryBlock(
                        id="core_public_profile",
                        label="profile",
                        description="Stable user facts",
                        value="Alice prefers rail travel.",
                        limit_tokens=100,
                        source_refs=[
                            SourceRef(source_type="message", source_id=messages[0].id)
                        ],
                        tags=["profile"],
                        metadata={"scope": "benchmark"},
                    )
                )
            return original_build_context(
                session_id,
                task,
                budget=budget,
                retrieval_query=retrieval_query,
                include_global_core=include_global_core,
            )

        service.build_context = build_context_with_core
        return original_run_baseline(
            baseline,
            case,
            messages,
            service,
            settings,
            budget_override=budget_override,
        )

    monkeypatch.setattr(public_benchmarks, "_run_baseline", seeded_run_baseline)
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")

    results = run_public_benchmark(
        settings,
        benchmark="locomo",
        data_path=data_path,
        run_id="public-v3-core-diagnostics-test",
        baselines=["memoryos_lite"],
        llm_answer=False,
        llm_judge=False,
    )

    report = results[0].to_report()
    assert "v3_layer_counts" in report
    assert "v3_budget_decisions" in report
    assert "v3_diagnostics" in report
    assert report["v3_layer_counts"]["core"] >= 1
    core_diagnostics = [d for d in report["v3_diagnostics"] if d["layer"] == "core"]
    assert core_diagnostics
    assert core_diagnostics[0]["budget_tokens"] > 0
    assert core_diagnostics[0]["metadata"]["label"] == "profile"
    assert core_diagnostics[0]["metadata"]["tags"] == ["profile"]
    assert "planned_evidence_source_hit_at_5" in report
```

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_core_diagnostics_are_append_only -q
```

Expected RED: fails until core diagnostic payload is visible through public report setup.

## GREEN

- [ ] Update `src/memoryos_lite/v3_contracts.py`.

Add fields to `CoreMemoryBlock`:

```python
read_only: bool = False
tags: list[str] = Field(default_factory=list)
```

Keep existing defaults and validation unchanged.

- [ ] Add Alembic revision `alembic/versions/0007_add_core_block_read_only_tags.py`.

Required migration intent:

```python
revision: str = "0007_add_core_block_read_only_tags"
down_revision: str = "0006_add_archival_memory"
```

Upgrade:

- Add `read_only` boolean to `core_memory_blocks`, non-null default false.
- Add `tags_json` text to `core_memory_blocks`, non-null default `"[]"`.
- Be idempotent in the same style as existing migrations.

Downgrade:

- Drop `tags_json`.
- Drop `read_only`.

- [ ] Update `src/memoryos_lite/store.py`.

Required edits:

- Add `CoreMemoryBlockRecord.read_only`.
- Add `CoreMemoryBlockRecord.tags_json`.
- Include both fields in `_core_block_from_record`.
- Include both fields in `create_core_memory_block`.
- Include both fields in `update_core_memory_block`.
- Preserve both fields in history snapshots through `model_dump(mode="json")`.
- Update DB migration head stamping from `0006_add_archival_memory` to `0007_add_core_block_read_only_tags`.

- [ ] Update `CoreMemoryService.create_block` in `src/memoryos_lite/core_memory.py`.

Add parameters:

```python
read_only: bool = False
tags: list[str] | None = None
metadata: dict[str, object] | None = None
```

Pass them into `CoreMemoryBlock` as:

```python
read_only=read_only,
tags=list(tags or []),
metadata=dict(metadata or {}),
```

- [ ] Enforce read-only in `src/memoryos_lite/core_memory.py`.

Add helper:

```python
@staticmethod
def _ensure_mutable(block: CoreMemoryBlock) -> None:
    if block.read_only:
        raise ValueError("read-only core memory block cannot be mutated")
```

Call it after `_require_block` in `append_block`, `replace_block`, `update_block`, and `delete_block`.

- [ ] Replace the plain renderer with a structured renderer.

Use a focused return type:

```python
@dataclass(frozen=True)
class CoreMemoryRender:
    text: str
    metadata_by_block: dict[str, dict[str, object]]
```

`render_core_memory_blocks(blocks, tokenizer)` must return `CoreMemoryRender`. Include `<memory_blocks>`, block labels, description, metadata, sources, and value. Keep ordering deterministic and skip deleted blocks.

- [ ] Update `src/memoryos_lite/context_composer.py`.

Required behavior:

- Import `render_core_memory_blocks`.
- For each active block, render one block at a time or use renderer metadata by block id.
- Set `ContextLayerItem.text` to structured rendered text.
- Set `estimated_tokens` from the structured text.
- Include metadata fields `label`, `description`, `read_only`, `tags`, `metadata`, `tokens_current`, `tokens_limit`, `source_ref_count`, and `reason`.
- Preserve existing `_try_add_layer` budget/drop behavior.

- [ ] Keep `tests/test_public_benchmarks.py` fixture plumbing limited to the explicit seeded `_run_baseline` wrapper above.

Preferred approach:

- Use existing public benchmark path.
- Seed a core block through the same store/service setup used by `run_public_benchmark`.
- Do not alter `PublicBenchmarkResult` fields unless diagnostics are otherwise inaccessible.
- Do not add core source refs to retrieval metrics.

## REFACTOR

- [ ] Run the focused Phase 3 suite.

```bash
uv run pytest tests/test_v3_contracts.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q
```

Expected GREEN: all added/updated Phase 3 tests pass.

- [ ] Remove duplication in renderer formatting only after tests pass.

Allowed refactor:

- Small private helpers for source-ref formatting and metadata formatting.
- No behavior changes.
- No broad composer/store restructuring.

- [ ] Confirm v1 fallback and kernel default with existing focused tests.

```bash
uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q
```

Expected GREEN:

- default memory arch remains `v3`;
- explicit v1 report has empty v3 diagnostics;
- kernel trace remains default-off.

## Full Verification

- [ ] Run full tests.

```bash
uv run pytest -q
```

Expected: pass. Record exact pass/warning count in result.

- [ ] Run lint.

```bash
uv run ruff check .
```

Expected: pass with no new lint errors.

## Smoke

Run both no-LLM diagnostic smokes through explicit v3. These are smoke gates, not benchmark-improvement claims.

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Required smoke notes:

- Report `run_id` or report path.
- Record `memory_arch`.
- Record `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics` presence.
- List case IDs and diagnostic classifications.
- List pass-to-fail and fail-to-pass if a comparable baseline is available.
- If no comparison baseline is available, state `no comparison baseline available` and do not claim improvement.
- Keep LongMemEval and LoCoMo separate; do not promote based on LongMemEval alone.

## Review

- [ ] Request review against active goal and anti-demo gates.

Review checklist:

- `spec.md`, `plan.md`, result, review, and ACK cite `.hermes-loop/work/phase-3/context_bundle.md`.
- Core memory is wired into real `MemoryOSService.build_context()` through v3 composer, not only service tests.
- Source-less automatic core writes were not added.
- Read-only blocks reject edit/delete APIs.
- Limit behavior is reject-on-over-limit and tested.
- Structured render includes description, tags, metadata, source refs, token current/limit, read-only state, and value.
- Public benchmark diagnostics preserve append-only fields.
- Retrieval/source-hit metrics are not polluted by core block source refs.
- Explicit v1 fallback excludes v3 core blocks.
- `MEMORYOS_MEMORY_ARCH=v3` remains default.
- `MEMORYOS_AGENT_KERNEL` remains default `off`.
- LoCoMo smoke is reported even if LongMemEval looks acceptable.
- Case-level regressions are listed or absence of comparison baseline is explicit.

## Anti-Demo ACK Criteria

Do not ACK Phase 3 unless all are true:

- All RED tests were observed failing for the intended reason or recorded as already-covered verification.
- GREEN implementation passes focused and full verification.
- The real v3 context path includes structured core memory diagnostics.
- Explicit v1 fallback remains isolated.
- Kernel opt-in is preserved.
- Public benchmark smoke reports are case-level.
- No answer prompt tuning, benchmark-specific memory writes, case-id hacks, or aggregate-only improvement claims were introduced.
- Review returns PASS against active goal, source grounding, overfitting, fallback/default preservation, and anti-demo completion.
