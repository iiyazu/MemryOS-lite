# phase: phase-4

# Plan: Archive Eligibility And Passage Scope

Context bundle: `.hermes-loop/work/phase-4/context_bundle.md` (`god_dispatch.json` sha256 `c12ced67fcb4a1980a01659372e676570a9c0d199299c31a6afcdcd5cd674037`).

Active goal: "Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default."

Chosen route: Option B from `.hermes-loop/work/phase-4/brainstorm.md`, a narrow MemoryOS-native archive eligibility contract wired into the real v3 composer and public benchmark diagnostics.

## File Responsibilities

- Modify `src/memoryos_lite/v3_contracts.py`: add narrow archive eligibility request/result contracts, request scope metadata, and passage invariant validation.
- Modify `src/memoryos_lite/store.py`: add helper methods to resolve attached archive IDs and list eligible passages; enforce new passage invariants on new writes.
- Modify `src/memoryos_lite/context_composer.py`: replace unscoped global archival search with scoped eligibility resolution and diagnostics.
- Modify `src/memoryos_lite/engine.py`: pass request scope into the v3 composer and preserve v1 isolation; keep source-id extraction limited to selected v3 recall/archival/recent items.
- Modify `src/memoryos_lite/public_benchmarks.py`: expose archival eligibility through existing append-only v3/case diagnostic fields without changing scoring.
- Modify `src/memoryos_lite/retrieval/archival_searcher.py` only if hit metadata needs passage kind/deleted-state propagation; keep it operating on pre-filtered candidate passages.
- Modify `tests/test_archival_store.py`, `tests/test_archival_searcher.py`, `tests/test_context_composer.py`, `tests/test_engine.py`, and `tests/test_public_benchmarks.py`.
- Do not modify `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, docs, unrelated source files, or kernel defaults as part of this phase.

## RED

### 1. Composer excludes unattached archive pollution

Add `tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope`.

Test setup:

```python
store.create_archive_attachment(
    ArchiveAttachment(
        id="aatt_attached",
        archive_id="archive_attached",
        scope_type="session",
        scope_id="ses_1",
        source_refs=[_ref("msg_1")],
    )
)
store.create_archival_passage(
    ArchivalPassage(
        id="apsg_attached",
        archive_id="archive_attached",
        text="Alice moved to Shanghai.",
        source_refs=[_ref("msg_1")],
    )
)
store.create_archival_passage(
    ArchivalPassage(
        id="apsg_unattached_distractor",
        archive_id="archive_unattached",
        text="Alice moved to Shanghai Shanghai Shanghai.",
        source_refs=[_ref("msg_2")],
    )
)
```

Build:

```python
package = V3ContextComposer(store=store, settings=settings, tokenizer=WordTokenizer()).build(
    ContextComposerRequest(session_id="ses_1", task="Where did Alice move?", budget=80)
)
```

Expected assertions:

```python
archival_items = [item for item in package.items if item.layer == "archival"]
assert [item.item_id for item in archival_items] == ["apsg_attached"]
assert "apsg_unattached_distractor" not in package.model_dump_json()
assert package.metadata["archival_eligibility"]["eligible_archive_ids"] == ["archive_attached"]
assert package.metadata["archival_eligibility"]["archival_scope_excluded"] == 1
```

Run:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope -q
```

Expected RED: fails because `V3ContextComposer._archival_items()` currently calls `store.list_archival_passages()` globally.

### 2. Composer reports archival eligibility diagnostics

Add `tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility`.

Expected assertions:

```python
eligibility = package.metadata["archival_eligibility"]
assert eligibility["eligible_archive_ids"] == ["archive_attached"]
assert eligibility["selected_passage_ids"] == ["apsg_attached"]
assert eligibility["eligible_passage_count"] == 2
assert eligibility["selected_passage_count"] == 1
assert eligibility["archival_scope_excluded"] == 1
assert eligibility["archival_no_match"] == 1
reason_codes = {event.reason_code for event in package.diagnostics if event.layer == "archival"}
assert {"archival_scope_excluded", "archival_no_match"} <= reason_codes
```

Run:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility -q
```

Expected RED: fails because current diagnostics only describe selected/dropped items and do not expose eligibility.

### 3. Store enforces passage invariants and eligible helper behavior

Add `tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper`.

Expected assertions:

```python
with pytest.raises(ValueError, match="agent/archive passages cannot have source_id"):
    store.create_archival_passage(ArchivalPassage(id="bad_both", archive_id="archive_1", source_id="source_1", text="bad", source_refs=[ref]))

with pytest.raises(ValueError, match="source/file passages require source_id"):
    store.create_archival_passage(ArchivalPassage(id="bad_neither", text="bad", source_refs=[ref]))

eligible = store.list_archival_passages_for_scope(
    session_id="ses_1",
    identity_scope=None,
)
assert [passage.id for passage in eligible] == ["apsg_attached"]
```

Run:

```bash
uv run pytest tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper -q
```

Expected RED: fails because current store accepts passages with both `archive_id` and `source_id`, and no scoped helper exists.

### 4. Public benchmark diagnostics are append-only

Add `tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only`.

Patch `_run_baseline` similarly to the existing core diagnostics test, seed one attached archive passage and one unattached distractor before calling the original `service.build_context()`.

Expected assertions:

```python
report = results[0].to_report()
assert report["memory_arch"] == "v3"
assert "v3_diagnostics" in report
assert "v3_layer_counts" in report
assert "planned_evidence_source_hit_at_5" in report
eligibility = report["case_diagnostics"]["archival_eligibility"]
assert eligibility["selected_passage_ids"] == ["apsg_public_attached"]
assert eligibility["archival_scope_excluded"] == 1
assert report["verdict"] in {"pass", "fail"}
assert "failure_class" in report
```

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only -q
```

Expected RED: fails because public case diagnostics do not copy archival eligibility.

### 5. Explicit v1 excludes v3 archival diagnostics

Add `tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics`.

Expected assertions:

```python
context = service.build_context(session.id, "Where did Alice move?", budget=200)
assert context.metadata.get("memory_arch") != "v3"
assert "v3_diagnostics" not in context.metadata
assert "archival_eligibility" not in context.metadata
assert "Alice moved to Shanghai." not in context.model_dump_json()
```

Run:

```bash
uv run pytest tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Expected RED or guard: may pass before implementation for metadata absence, but it must remain in the focused suite as the v1 isolation gate.

## GREEN

### 6. Add contracts

Implement in `src/memoryos_lite/v3_contracts.py`:

```python
class ArchiveEligibilityScope(BaseModel):
    session_id: str
    identity_scope: IdentityScope | None = None
    source_ids: list[str] = Field(default_factory=list)
    file_ids: list[str] = Field(default_factory=list)

class ArchiveEligibilityResult(BaseModel):
    scope: ArchiveEligibilityScope
    eligible_archive_ids: list[str] = Field(default_factory=list)
    eligible_passage_ids: list[str] = Field(default_factory=list)
    selected_passage_ids: list[str] = Field(default_factory=list)
    selected_source_refs: list[SourceRef] = Field(default_factory=list)
    eligible_passage_count: int = 0
    selected_passage_count: int = 0
    archival_scope_excluded: int = 0
    archival_no_match: int = 0
    reason_codes: list[str] = Field(default_factory=list)
```

Extend `ContextComposerRequest` with:

```python
archival_scope: ArchiveEligibilityScope | None = None
```

Add `ArchivalPassage` validation:

```python
@model_validator(mode="after")
def validate_passage_identity(self) -> ArchivalPassage:
    if self.archive_id and self.source_id:
        raise ValueError("agent/archive passages cannot have source_id")
    if not self.archive_id and not self.source_id:
        raise ValueError("source/file passages require source_id or agent/archive passages require archive_id")
    return self
```

If source/file passage support needs clearer wording, keep the error messages stable with the RED test expectations.

### 7. Add store helpers

Implement in `src/memoryos_lite/store.py`:

```python
def resolve_attached_archive_ids(
    self,
    *,
    session_id: str,
    identity_scope: IdentityScope | None = None,
    source_ids: list[str] | None = None,
) -> list[str]:
    scope_pairs: list[tuple[str, str]] = [("session", session_id)]
    if identity_scope is not None:
        if identity_scope.agent_id:
            scope_pairs.append(("agent", identity_scope.agent_id))
        if identity_scope.run_id:
            scope_pairs.append(("run", identity_scope.run_id))
        if identity_scope.project_id:
            scope_pairs.append(("project", identity_scope.project_id))
        if identity_scope.user_id:
            scope_pairs.append(("user", identity_scope.user_id))
    for source_id in source_ids or []:
        scope_pairs.append(("source", source_id))

    archive_ids: list[str] = []
    seen: set[str] = set()
    for scope_type, scope_id in scope_pairs:
        for attachment in self.list_archive_attachments(
            scope_type=scope_type,
            scope_id=scope_id,
        ):
            if attachment.archive_id in seen:
                continue
            seen.add(attachment.archive_id)
            archive_ids.append(attachment.archive_id)
    return archive_ids

def list_archival_passages_for_scope(
    self,
    *,
    session_id: str,
    identity_scope: IdentityScope | None = None,
    source_ids: list[str] | None = None,
    file_ids: list[str] | None = None,
) -> list[ArchivalPassage]:
    archive_ids = self.resolve_attached_archive_ids(
        session_id=session_id,
        identity_scope=identity_scope,
        source_ids=source_ids,
    )
    if not archive_ids:
        return []
    passages: list[ArchivalPassage] = []
    allowed_files = set(file_ids or [])
    for archive_id in archive_ids:
        for passage in self.list_archival_passages(archive_id=archive_id):
            if allowed_files and passage.file_id not in allowed_files:
                continue
            passages.append(passage)
    return passages
```

Resolution rules:

- include `("session", session_id)`;
- include identity scope fields when present: `agent`, `run`, `project`, `user`;
- include `("source", source_id)` for explicit source IDs only;
- dedupe archive IDs preserving store order;
- return no passages when no archive is attached;
- count excluded passages separately in composer diagnostics, not by selecting them.

Keep `list_archival_passages()` unchanged for explicit admin/test use.

### 8. Scope composer archival retrieval

Modify `src/memoryos_lite/context_composer.py`:

- change `_archival_items(query)` to `_archival_items(request, query)`;
- derive `ArchiveEligibilityScope` from `request.archival_scope` or `request.session_id`;
- call `store.list_archival_passages_for_scope(session_id=request.session_id, identity_scope=scope.identity_scope, source_ids=scope.source_ids, file_ids=scope.file_ids)`;
- search only returned eligible passages;
- append eligibility diagnostics to `package.diagnostics`;
- write `package.metadata["archival_eligibility"]`.

Run after implementation:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility -q
```

Expected GREEN: both tests pass.

### 9. Preserve v1/v3 engine boundaries

Modify `src/memoryos_lite/engine.py` only as needed to pass scope into `ContextComposerRequest`.

Keep these invariants:

- `_should_route_to_v3_context()` remains `settings.resolved_memory_arch == "v3"`;
- explicit `MEMORYOS_MEMORY_ARCH=v1` never receives `v3_diagnostics`;
- `_v3_source_ids()` uses selected v3 items only, not scope-excluded diagnostics.

Run:

```bash
uv run pytest tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Expected GREEN: v1 has no archival eligibility metadata or scoped passage text.

### 10. Append public diagnostics

Modify `src/memoryos_lite/public_benchmarks.py`:

- keep `PublicBenchmarkResult` scoring fields unchanged;
- copy `output.v3_context["metadata"]["archival_eligibility"]` or equivalent into `case_diagnostics["archival_eligibility"]`;
- do not count scope-excluded passage source refs as `retrieval_candidate_source_ids`;
- preserve `v3_diagnostics` as the detailed event stream.

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only -q
```

Expected GREEN: archival eligibility appears in report/case diagnostics and scoring schema remains present.

## REFACTOR

### 11. Focus the API names and remove duplication

Review the new code for a single source of truth:

- one helper for attachment scope pair construction;
- one helper for eligibility result serialization;
- no duplicated `session/agent/run/source` scope logic in both store and composer;
- no new Letta imports;
- no new broad migration unless a deleted-state column was required by tests.

Run the focused phase suite:

```bash
uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q
```

Expected GREEN: all focused tests pass.

### 12. Baseline checks

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected GREEN:

- full pytest passes;
- ruff reports all checks passed;
- default settings still resolve `memoryos_memory_arch == "v3"` and `memoryos_agent_kernel == "off"`.

## Smoke And Milestone

### 13. Mandatory milestone full-chain evals

Run LongMemEval:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30
```

Run LoCoMo:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30
```

Record separately:

- pass/fail counts;
- fail-to-pass;
- pass-to-fail;
- retrieval miss;
- context missing evidence;
- evidence hit answer fail;
- unsupported answer;
- judge questionable;
- `archival_scope_excluded` vs `archival_no_match` counts;
- reports for the visible cases listed in `god_dispatch.json`.

If provider access blocks full-chain LLM answer/judge, record the exact blocker and run fallback smokes only as non-milestone evidence:

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

## Review

### 14. Anti-demo gates for review lane

Review must reject usable ACK if any gate fails:

- real v3 `build_context()` still calls global `list_archival_passages()` as the retrieval source;
- unattached archive passages can appear in selected context;
- public benchmark diagnostics omit archival eligibility;
- retrieval miss vs archive scope exclusion is not diagnosable per case;
- explicit v1 includes v3 archival metadata;
- `MEMORYOS_AGENT_KERNEL` default changes from `off`;
- Letta is added as a runtime dependency;
- implementation rewrites storage beyond the narrow helper/contract need;
- benchmark results are reported only as aggregate pass rate;
- LongMemEval improvement is promoted while LoCoMo remains unexplained;
- benchmark case IDs or expected answers influence retrieval.

### 15. Final evidence to include in result/ACK

Result and ACK must cite `.hermes-loop/work/phase-4/context_bundle.md` and include:

- RED command outputs before GREEN fixes;
- focused suite output;
- full pytest and ruff output;
- LongMemEval and LoCoMo reports or explicit provider/local-data blocker;
- case-level lists for `58bf7951`, `6ade9755`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`;
- confirmation that v3 remains default, v1 remains explicit fallback, and kernel remains opt-in/default-off.
