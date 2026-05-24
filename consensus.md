# MemoryOS / Hermes Consensus

Last updated: 2026-05-24

This document is the shared starting point for new Codex, Claude Code, or other
agent sessions working in this repository. It records the current architecture,
active goals, parallel feature lanes, and constraints that should not be
re-litigated unless the project owner explicitly changes direction.

## 1. Project Identity

MemoryOS Lite is an eval-driven, source-attributed Agent/RAG memory prototype.
It is not production-ready MemoryOS.

The project has two connected tracks:

- **MemoryOS Lite**: the memory architecture, retrieval pipeline, context
  composer, source attribution, storage, and benchmark diagnostics.
- **Hermes loop**: the agentic development control plane used to coordinate
  autonomous feature work, review, integration, and merge gating.

The current product goal is not to claim generic benchmark superiority. The goal
is to make long-context memory behavior measurable, debuggable, source-grounded,
and progressively usable on LongMemEval and LoCoMo style workloads.

## Session Bootstrap

New agent sessions should initialize from these files in order:

1. `AGENTS.md`
2. `consensus.md`
3. `.hermes-loop/master_status.json`
4. `.hermes-loop/master_state.json`
5. `.hermes-loop/work/features/<feature-id>/blueprint.md`

Use current code and live Hermes JSON as the facts when docs disagree. Historical
Hermes phase details have been summarized under `.hermes-loop/history/`; they
are audit history and must not drive active execution.

## 2. Current MemoryOS Architecture

Code and `AGENTS.md` are the source of truth when docs disagree. At this
checkpoint, `src/memoryos_lite/config.py` sets `memoryos_memory_arch = "v3"` by
default. Some older README wording may still describe v3 as opt-in; treat that
as stale unless updated in the same branch.

Current baseline:

- Default memory architecture: `v3` layered composer.
- Legacy `v1` ContextBuilder fallback: `MEMORYOS_MEMORY_ARCH=v1`.
- Episode-first recall: opt-in with `MEMORYOS_RECALL_PIPELINE=v2`.
- Agent kernel: opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- Storage: SQLite-first and DB-authoritative.
- Filesystem page/trace outputs: debug mirrors, not primary state.
- Qdrant: optional ANN/vector experiment backend.
- No separate production database backend is configured.

Main lifecycle:

```text
ingest(message)
  -> persist Message
  -> v3 default path keeps raw messages available
  -> v2 opt-in ensures Episode records for raw-message recall

build_context(task)
  -> v3 ContextComposer by default
       core / recall / archival / recent layers
       ContextPackage-compatible payload
       v3 diagnostics and budget decisions
  -> v1 ContextBuilder when MEMORYOS_MEMORY_ARCH=v1
  -> v2 RecallPipeline when MEMORYOS_RECALL_PIPELINE=v2
```

Important modules:

| Path | Role |
|---|---|
| `src/memoryos_lite/config.py` | Settings, feature flags, provider config. |
| `src/memoryos_lite/schemas.py` | Pydantic models for messages, episodes, pages, memory, evals. |
| `src/memoryos_lite/store.py` | SQLite persistence, migrations, debug mirrors, traces. |
| `src/memoryos_lite/engine.py` | Service facade, ingestion, paging, context build routing. |
| `src/memoryos_lite/context_composer.py` | v3 layered composer and budget diagnostics. |
| `src/memoryos_lite/retrieval/` | Episode, archival, and recall search primitives. |
| `src/memoryos_lite/core_memory.py` | Source-backed core memory service. |
| `src/memoryos_lite/memory_lifecycle.py` | Recall -> archival -> core promotion helpers. |
| `src/memoryos_lite/agent_kernel.py` | Experimental opt-in agent kernel. |
| `src/memoryos_lite/public_benchmarks.py` | LongMemEval/LoCoMo adapters and diagnostics. |

Storage tables include sessions, messages, episodes, pages, items, trace events,
core memory tables, and archival memory tables. The current migration head is
`0006_add_archival_memory`.

## 3. Current Hermes Loop Architecture

Hermes has migrated away from the old root-loop phase controller. The active
architecture is:

```text
Reporter watchdog
  -> god_launcher.sh runner
  -> Master control plane
  -> feature-local Slave lanes
  -> artifact + git/worktree based review and integration gates
```

Active facts:

- Master state source: `.hermes-loop/master_state.json`.
- Master status summary: `.hermes-loop/master_status.json`.
- Launcher entrypoint: `.hermes-loop/god_launcher.sh`.
- Hardening/controller helpers: `.hermes-loop/hermes_hardening.py`.
- Reporter/watchdog: `.hermes-loop/hermes_reporter.py`.
- Legacy root-loop files: `.hermes-loop/legacy/root-loop/`, audit-only.
- Deprecated scheduler entrypoint: `.hermes-loop/hermes_loop.py`, exits
  immediately and should not be used.

Master is the only active controller after activation. Slave Gods are
feature-local autonomous workers: they receive a feature blueprint, operate
inside the feature scope, emit artifacts, and report back to Master. Master owns
final review, integrated tests, merge decisions, and external approval gates.

Current feature lanes:

| Feature | State | Purpose |
|---|---|---|
| `v1-quarantine` | `ready_for_merge` | Isolate legacy v1 ContextBuilder behavior behind explicit fallback and merge gate. |
| `archive-rag` | `planned` | Complete the archival/RAG boundary into a usable source-backed layer. |

Current Master queue snapshot:

- `merge_queue`: `v1-quarantine`
- `planning_queue`: `archive-rag`
- `master_review_queue`: empty
- `blocked`: empty

Merge remains gated by explicit approval artifacts. A feature being in
`ready_for_merge` or `merge_queue` does not mean the agent may merge without the
configured approval gate.

## 4. Shared Purpose For The Next Work

The next project objective is to move from a research prototype toward a usable
multi-lane memory system without losing source attribution or benchmark
traceability.

The practical goals are:

1. Complete an engineering-grade archival RAG layer for MemoryOS while avoiding
   any unsupported claim that the whole product is production-ready.
2. Organize and harden the memory layers so LongMemEval and LoCoMo diagnostics
   become usable engineering signals.
3. Evaluate Redis or similar infrastructure as a performance layer without
   replacing SQLite as the authoritative store prematurely.
4. Promote Hermes loop into a reusable multi-agent development platform built
   around the current loop design, Superpowers methodology, MemoryOS memory,
   Codex, Claude Code, and other CLI agents.
5. Keep the architecture open to future A2A-style collaboration models,
   including peer-to-peer or federated agents, without making A2A a required
   dependency in the MVP.

## 5. Parallel Feature Routes

These routes are intentionally parallelizable. Each route should have a Master
feature entry, a feature-local blueprint, a branch/worktree when needed, and
explicit artifacts.

### Route A: Archive RAG

Goal: make the archival layer a real source-backed RAG layer, not only a storage
schema. The implementation should be production-shaped in discipline
(contracts, invalidation, stale-evidence prevention, tests, diagnostics), but
the project should not market itself as production-ready until that is verified
well beyond the current prototype scope.

Expected direction:

- Connect archival document/chunk/passage writes to context retrieval.
- Preserve source refs for every archival context item.
- Make attachment/scope rules explicit and testable.
- Ensure update/delete history prevents stale archival evidence from being
  selected.
- Add diagnostics for archival selected, eligible-no-match, scope-excluded, and
  no-attached-archive cases.
- Prove behavior with focused archival tests before broader benchmark runs.

Non-goals:

- Do not claim production-ready MemoryOS or benchmark improvement without
  evidence.
- Do not bypass source refs or explicit approval for memory mutation.
- Do not replace the episode-first recall path.

### Route B: Benchmark-Usable Layer Organization

Goal: optimize the implementation of message, episode, recall, archival, core,
and recent layers so benchmark results become actionable and stable.

Expected direction:

- Keep retrieval metrics separate from answer-quality metrics.
- Improve evidence ordering, neighbor policy, and budget diagnostics.
- Track fail->pass and pass->fail changes on fixed LongMemEval/LoCoMo slices.
- Avoid dataset-specific hacks, case-id rules, or benchmark-string overfitting.
- Keep `MEMORYOS_MEMORY_ARCH=v1` fallback available.
- Keep `MEMORYOS_RECALL_PIPELINE=v2` as an explicit recall experiment unless a
  later plan intentionally changes the default.

### Route C: Performance Layer Exploration

Goal: evaluate Redis or comparable infrastructure for performance-sensitive
parts of the memory system.

Allowed exploration areas:

- Hot query/result cache.
- Session or context package cache.
- Embedding/vector lookup cache.
- Agent coordination state cache.
- Background job queue or pub/sub for future multi-agent runners.

Hard boundary:

- Redis must not become the authoritative memory store in the first iteration.
- SQLite remains the source of truth for messages, episodes, core memory,
  archival memory, traces, and history.
- Any cache must be invalidatable and reproducible from SQLite state.
- Benchmark improvements must not be claimed unless measured.

### Route D: Hermes Multi-Agent Platform

Goal: evolve `.hermes-loop` from a project-local loop into a reusable
multi-agent development platform.

The platform should combine:

- Current Hermes Master/Slave control-plane design.
- Superpowers-style spec, plan, TDD, review, and verification workflows.
- MemoryOS memory as the session/project memory substrate.
- Codex CLI, Claude Code CLI, and other shell-driven agents as runner backends.
- Git/worktree/GitHub artifacts for durable collaboration and review.
- Future A2A-compatible communication adapters where useful.

The platform should preserve this authority model:

```text
Master control plane
  -> owns registry, queues, policy, integration, and merge gates

Slave runner
  -> owns feature-local execution under a blueprint

Artifacts
  -> provide durable evidence for review, audit, and handoff
```

Future A2A support should be introduced as an adapter layer, not as a replacement
for the Master control plane:

```text
Hermes feature blueprint -> A2A task/message
Hermes slave_state       -> A2A task status
Hermes result artifacts  -> A2A artifacts
Hermes Master review     -> final authority remains local Master
```

AutoGen, Microsoft Agent Framework, LangGraph, Pydantic AI, or other frameworks
may be explored as runner implementations or Slave-internal orchestration. They
should not replace Hermes Master state as the current source of truth.

## 6. Feature Blueprint Standard

Every new parallel feature should have:

- Master registry entry in `.hermes-loop/master_state.json`.
- Blueprint at `.hermes-loop/work/features/<feature-id>/blueprint.md`.
- Slave state at `.hermes-loop/work/features/<feature-id>/slave_state.json`.
- Branch and worktree when implementation touches product code.
- Artifact paths for result, ack, review verdict, Master review, integrated
  tests, approval request, merge decision, and post-merge verification.

Blueprints should specify:

- Goal and user-visible value.
- Non-goals.
- Allowed files/modules.
- Behavioral invariants.
- Required tests and evals.
- Completion criteria.
- Review failure criteria.
- Handoff artifacts.
- Runner type, currently `local_codex` unless explicitly changed.

Recommended future runner metadata:

```json
{
  "runner": {
    "type": "local_codex",
    "protocol": "hermes-local",
    "agent_id": "slave-god-<feature-id>",
    "task_id": null,
    "endpoint": null
  }
}
```

This keeps future `a2a`, `claude_code`, `langgraph`, or other runners additive
rather than disruptive.

## 7. Engineering Rules

MemoryOS rules:

- Preserve source attribution.
- Keep SQLite authoritative.
- Keep filesystem mirrors diagnostic-only.
- Do not call the project production-ready.
- Do not hide case-level regressions behind aggregate benchmark movement.
- Do not claim benchmark/product improvement without fresh evidence.
- Keep v1 fallback and kernel opt-in unless an explicit plan changes them.

Hermes rules:

- Master is the only active controller.
- Legacy root-loop is audit-only.
- Slave Gods are feature-local and blueprint-scoped.
- Master owns integrated tests, approval gates, and merge decisions.
- A ready feature is not mergeable without required approval artifacts.
- Shared documents and git artifacts are the durable coordination layer.

Agent-session rules:

- Read `AGENTS.md` and this file before making architecture claims.
- Prefer current code and control-plane JSON over stale docs.
- When docs disagree, record the discrepancy instead of silently choosing the
  convenient version.
- For reviews, lead with blocking findings and file/line references.
- For implementation, keep changes focused and verify with targeted tests.

## 8. Useful Commands

Baseline project checks:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Hard eval:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Public benchmark smoke examples:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
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

Hermes status inspection:

```bash
python3 .hermes-loop/hermes_reporter.py
python3 -m json.tool .hermes-loop/master_status.json
python3 -m json.tool .hermes-loop/master_state.json
```

## 9. Immediate Next Step

The most natural next Master-planned feature is `archive-rag`.

Before implementation, Master should ensure its blueprint has:

- narrow scope;
- source-backed archival write/read path;
- stale evidence prevention;
- focused tests;
- benchmark smoke only after focused tests pass;
- no merge without integrated tests and explicit approval.

This lets MemoryOS progress and simultaneously exercises the new multi-god
architecture on a real feature lane.
