# phase: phase-13

# Phase 13 Context Bundle

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Phase Objective

Phase: `phase-13`.

Name: Core Memory Lifecycle.

Target state: `core-memory-lifecycle-usable`.

Target chain components:

- store: source-backed core block writes, updates, deletes, and history;
- retrieval: candidate promotion inputs and conflict checks;
- context composer: rendered core block inclusion and budgeted accounting;
- answer projection: only if core memory enters public report evidence;
- kernel loop: opt-in tests only if memory tools touch kernel paths;
- public eval: only if default v3 public context changes.

## Why This Phase Exists Now

`state.json` now points to `phase-13` in `GOD_DISPATCH`. Phase 12 is marked completed after proving the tool-written archival/RAG bridge through focused structural tests. Phase 11 remains visible unfinished LoCoMo debt and must not be hidden by structural Phase 13 success.

Phase 13 exists to make core memory a controlled promotion target rather than a manually edited block store.

Current design gap:

- core blocks can already be rendered;
- block updates exist;
- but the promotion path from evidence to approved core memory is not yet treated as a first-class lifecycle with conflict handling, deprecation, and history preservation.

## Current Hypothesis

Core memory should be updated only through a source-backed promotion path:

```text
recall / archival evidence
-> candidate
-> conflict check
-> approval / provenance gate
-> core update
-> history
-> rendered block
```

Likely failure mode to prove first:

- candidate evidence can render into v3 context only after a direct update path, not through a clear promotion lifecycle;
- conflicting or low-density evidence may overwrite current core text without explicit protection;
- read-only blocks may not be enforced tightly enough on all write paths.

Disconfirming evidence:

- core-memory updates already preserve source refs, conflict checks, and history on the real path;
- read-only blocks already reject all mutation paths;
- stale core facts are already deprecated without losing audit history;
- no new lifecycle behavior is actually needed beyond phase-local reporting.

## Scope

Allowed:

- add focused RED tests for candidate promotion, conflict rejection, history preservation, and read-only enforcement;
- verify or change `MemoryStore` core block helpers, render accounting, and history tracking;
- verify or change `V3ContextComposer` core-layer rendering and budget accounting if needed;
- add append-only diagnostics for candidate source refs, old value, deprecation, and rendered block identity;
- keep v1 fallback, v3 default, and kernel opt-in unchanged.

Non-goals:

- do not enable `MEMORYOS_AGENT_KERNEL=v1` by default;
- do not change benchmark scoring or judge semantics;
- do not claim benchmark improvement from a core-memory structural test alone;
- do not let direct manual edits bypass the promotion lifecycle.

## State Snapshot

From `.hermes-loop/state.json` at dispatch refresh:

- `current_state = GOD_DISPATCH`;
- `current_phase_idx = 13`;
- `execute_lane.phase = phase-13`;
- `execute_lane.state = GOD_DISPATCH`;
- `plan_lane.phase = phase-14`;
- `plan_lane.state = PLAN_STORM`;
- `research_lane.phases = ["phase-14"]`.
- `phase-11.status = in_progress`;
- `phase-12.status = completed`;
- `phase-13.status = in_progress`.

Because `current_state` is `GOD_DISPATCH`, God may generate or refresh only phase-local context and dispatch artifacts in this startup pass. Do not run tests, evals, `uv`, `pytest`, `ruff`, or implementation commands until the controller enters the appropriate planning or execution state.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` as the active blueprint. Relevant sections:

- `Current Baseline And Phase 8 Evidence`;
- `Hard Constraints`;
- `Context Bundle Requirement`;
- `Full-Chain LLM Judge Gates`;
- `Phase 11 - Evidence Handoff And Context Selection`;
- `Phase 12 - Archival/RAG Memory Unification`;
- `Phase 13 - Core Memory Lifecycle`;
- `Phase 14 - Agent Memory Loop`.

Promoted amendment source:

- `.hermes-loop/work/phase-8/blueprint_amendment.md`;
- `.hermes-loop/work/phase-8/blueprint_promotion.md`.

The Phase 8 amendment is already promoted into the root blueprint. It remains the rationale for the targeted LoCoMo reliability loop and for preserving case-level pass-to-fail reporting.

## Required Read-First Files

- `.hermes-loop/work/current_goal.md`;
- `.hermes-loop/state.json`;
- `.hermes-loop/blueprint.md`;
- `.hermes-loop/work/phase-12/context_bundle.md`;
- `.hermes-loop/work/phase-12/god_dispatch.json`;
- `.hermes-loop/work/phase-12/result.md`;
- `.hermes-loop/work/phase-12/ack.json`;
- `.hermes-loop/work/phase-11/result.md`;
- `.hermes-loop/work/phase-11/case_matrix.md`;
- `.hermes-loop/work/phase-11/review_verdict.json`;
- `docs/known-issues.md`;
- `docs/public-benchmark-diagnosis.md`;
- `docs/agentic-memory-roadmap-zh.md`;
- `src/memoryos_lite/store.py`;
- `src/memoryos_lite/context_composer.py`;
- `src/memoryos_lite/memory_lifecycle.py`;
- `src/memoryos_lite/v3_contracts.py`;
- `tests/test_memory_lifecycle.py`;
- `tests/test_context_composer.py`;
- `tests/test_core_memory_store.py`.

Required Letta reference files, design-only:

- `/home/iiyatu/projects/python/letta/letta/schemas/block.py`;
- `/home/iiyatu/projects/python/letta/letta/schemas/memory.py`;
- `/home/iiyatu/projects/python/letta/letta/services/block_manager.py`;
- `/home/iiyatu/projects/python/letta/letta/services/tool_executor/core_tool_executor.py`;
- `/home/iiyatu/projects/python/letta/letta/agents/letta_agent_v3.py`;
- `/home/iiyatu/projects/python/letta/letta/services/context_window_calculator/context_window_calculator.py`.

Borrow semantics for block metadata, read-only enforcement, prompt rebuild, audited core-memory tools, approval boundaries, and component accounting. Do not add Letta as a runtime dependency.

## Relevant Prior Evidence

Phase 12 completed structural archival/RAG bridge work:

- approved `archive_write` creates a same-session attachment when needed;
- bridged archival passage metadata propagates into v3 archival items;
- same-session v3 context can select the bridged `apsg_{memory_id}` passage;
- full suite: `446 passed, 1 warning`;
- ruff: clean;
- no public benchmark improvement was claimed.

Latest Phase 11 full-chain gate remains the current case-level benchmark warning:

- LongMemEval 30: `30 pass / 0 fail`;
- LoCoMo 30: `20 pass / 10 fail`;
- LoCoMo fail-to-pass: `conv-26_qa_027`;
- LoCoMo pass-to-fail: `conv-26_qa_028`;
- source-miss judged-pass risk: `conv-26_qa_005`;
- unchanged LoCoMo failures: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`;
- all 60 rows used `memory_arch=v3`;
- default kernel traces stayed empty.

Use Phase 11 debt as regression context. Do not present Phase 13 structural lifecycle work as a LoCoMo quality fix unless a real public benchmark gate proves same-case movement.

## Pass-To-Fail Risks

- allowing direct core updates to bypass candidate approval can make memory mutation unauditable;
- replacing a block value without source refs can create unsupported stable facts;
- rendering candidate text before approval can leak speculative facts into default v3 context;
- overly broad conflict rules can block valid updates and leave stale facts active;
- changing core-layer token accounting can silently drop recall or archival evidence;
- opt-in kernel tests must not imply kernel default enablement.

## RED Evidence To Start From

No Phase 13 RED has been run in this dispatch state. The execute lane must add failing tests before production changes, preferably:

- repeated recall or archival evidence proposes a core promotion candidate with source refs and target block metadata;
- a conflicting candidate does not overwrite an existing core block silently;
- an approved replacement records old value, new value, source refs, approval/provenance, and history;
- a read-only core block rejects all mutation paths;
- a stale core fact can be deprecated without deletion from history;
- v3 context renders only approved/source-backed core memory, not unapproved candidates.

## Evidence and Verification Hints

Start from failing cases rather than claims.

Expected phase-local smoke:

- focused lifecycle tests for promotion, overwrite rejection, and history;
- no-LLM structural smoke only if core memory changes affect v3 context rendering;
- no public benchmark promotion claim unless default v3 benchmark context changes.

Focused test candidates:

```bash
uv run pytest tests/test_memory_lifecycle.py tests/test_context_composer.py -q
uv run pytest tests/test_core_memory_store.py tests/test_core_memory_service.py -q
```

Baseline checks before review:

```bash
uv run pytest -q
uv run ruff check .
```

Structural no-LLM public smoke, only if the default v3 public context path changes:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

Run LongMemEval 30 and LoCoMo 30 full-chain LLM judge in parallel only if Phase 13 changes alter default public benchmark context composition. Otherwise record `case_level_eval.limit = 0` and explain why full-chain milestone eval is not applicable to this structural lifecycle phase.

## Anti-Demo Completion Criteria

Phase 13 is usable only if:

- the real store/lifecycle/composer chain is exercised, not only helper objects;
- at least one RED test fails before production changes;
- approved core updates preserve source refs and history;
- direct manual or sourceless mutation does not bypass provenance;
- rendered core memory is budget-accounted and traceable in v3 context diagnostics when applicable;
- v1 fallback, v3 default, and kernel opt-in remain unchanged;
- Phase 11 LoCoMo debt remains visible in `result.md`, `review_verdict.json`, and `ack.json`.
