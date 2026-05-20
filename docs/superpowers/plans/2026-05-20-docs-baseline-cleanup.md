# MemoryOS Docs Baseline Cleanup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove obsolete process docs and keep a small set of current, readable baseline docs that describe the project as it exists now.

**Architecture:** Delete clearly historical phase/result writeups, then trim the remaining baseline docs so they describe the current v2-aware memory system, current store shape, and current benchmark position without duplicating the same story in multiple files.

**Tech Stack:** Markdown, git, ripgrep.

---

### Task 1: Remove obsolete process docs

**Files:**
- Delete: `docs/phase-2.6-results.md`
- Delete: `docs/phase-3-results.md`
- Delete: `docs/phase4-iterative-eval-summary.md`
- Delete: `docs/project-handoff.md`
- Delete: `docs/muse.md`
- Delete: `docs/architecture-and-results.md`
- Delete: `docs/architecture-and-results-zh.md`

- [ ] **Step 1: Confirm the files are process/history documents**

Run:

```bash
sed -n '1,40p' docs/phase-2.6-results.md
sed -n '1,40p' docs/phase-3-results.md
sed -n '1,40p' docs/phase4-iterative-eval-summary.md
sed -n '1,40p' docs/project-handoff.md
sed -n '1,40p' docs/muse.md
sed -n '1,40p' docs/architecture-and-results.md
sed -n '1,40p' docs/architecture-and-results-zh.md
```

Expected: each file reads like a historical report, handoff note, or scratch review log rather than a current baseline reference.

- [ ] **Step 2: Delete the obsolete docs**

Run:

```bash
git rm docs/phase-2.6-results.md docs/phase-3-results.md docs/phase4-iterative-eval-summary.md docs/project-handoff.md docs/muse.md docs/architecture-and-results.md docs/architecture-and-results-zh.md
```

Expected: the files disappear from the working tree.

- [ ] **Step 3: Check for broken references**

Run:

```bash
rg -n "phase-2.6-results|phase-3-results|phase4-iterative-eval-summary|project-handoff|muse|architecture-and-results" README.md docs -g '!docs/superpowers/**'
```

Expected: only historical references in already-deleted files, if any, or no matches.

- [ ] **Step 4: Commit**

```bash
git add -u docs
git commit -m "docs: remove obsolete process notes"
```

### Task 2: Trim the remaining baseline docs

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/public-benchmark-diagnosis.md`
- Modify: `docs/source-guide.md`
- Modify: `docs/store-interface.md`
- Modify: `docs/known-issues.md`
- Modify: `docs/agentic-memory-roadmap-zh.md`
- Modify: `docs/agent-answer-diagnostics.md`

- [ ] **Step 1: Write the current-state wording first**

Use the current verified state:

```text
memoryos_recall_pipeline default = v1
v2 enabled only with MEMORYOS_RECALL_PIPELINE=v2
full pytest = 311 passed, 1 warning
hard eval = 1.00/1.00
v2 smoke LongMemEval = episode_source_hit_at_10 8/10, planned_evidence_source_hit_at_5 8/10
v2 smoke LoCoMo = episode_source_hit_at_10 5/10, planned_evidence_source_hit_at_5 5/10
```

- [ ] **Step 2: Refresh `CLAUDE.md` as the authoritative working guide**

Keep the development commands and conventions, but replace stale M2-B/Postgres
content with:

```markdown
## Project Status

Current portfolio positioning: eval-driven, source-attributed Agent/RAG memory prototype.

Current baseline:
- default recall path is `v1`
- v2 episode-first recall is opt-in with `MEMORYOS_RECALL_PIPELINE=v2`
- storage is SQLite-first with Alembic migrations through `0004_add_episodes`
- Qdrant is optional for ANN/vector experiments; Postgres/pgvector is not the current backend
- full pytest: `311 passed, 1 warning`
- hard eval: `1.00/1.00`
```

Update the architecture list to mention current `Episode`, `RecallPipeline`,
`EpisodeSearcher`, and public diagnostics.

- [ ] **Step 3: Rewrite `README.md` into a shorter current overview**

Keep the operational entrypoint material: quick start, API commands,
configuration, eval commands, development commands, and prototype boundaries.
Replace stale metrics and architecture text with:

```markdown
# MemoryOS Lite

面向长对话的 Eval 驱动、源归因 Agent/RAG 记忆原型。

## 当前状态

- 默认回退路径仍是 `v1`
- `v2` 通过 `MEMORYOS_RECALL_PIPELINE=v2` 显式启用
- 全量测试：`311 passed, 1 warning`
- hard eval：`1.00/1.00`
- v2 smoke：LongMemEval / LoCoMo 的 episode 诊断已可读

## 当前文档

- `docs/public-benchmark-diagnosis.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`
- `docs/agent-answer-diagnostics.md`
```

Remove the old architecture diagram, stale 275-pass metrics, and duplicated
long-form roadmap text, but keep the README useful as the repo entrypoint.

- [ ] **Step 4: Rewrite `docs/public-benchmark-diagnosis.md` as the current benchmark baseline**

Keep the existing purpose, but compress it to:

```markdown
## Current Positioning
## Baseline Metrics
## v2 Smoke Diagnostics
## Open Limitations
```

Keep only the current verified metrics and the explanation of metric scope. Remove the long M1/M2/M3 historical progression once it is no longer needed in the baseline set.

- [ ] **Step 5: Update the remaining reference docs to current terminology**

Make the following edits:

```markdown
docs/source-guide.md
- remove references to "M2-B" as a frozen milestone if they are no longer current
- align the data flow with the current v2 episode-first recall path
- keep the file as a short reader's map, not a history log

docs/store-interface.md
- add the current `episodes` table and episode backfill/indexing methods
- keep the store contract short and table-driven

docs/known-issues.md
- leave only currently accepted limitations
- trim long historical eval narratives

docs/agentic-memory-roadmap-zh.md
- keep it as the forward-looking roadmap
- remove stale phase/result claims that are now superseded by the v2 baseline

docs/agent-answer-diagnostics.md
- keep it because the deterministic answer diagnostics are live
- trim only stale optional-real-LLM wording if it conflicts with current config
```

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md docs/public-benchmark-diagnosis.md docs/source-guide.md docs/store-interface.md docs/known-issues.md docs/agentic-memory-roadmap-zh.md docs/agent-answer-diagnostics.md
git commit -m "docs: trim baseline docs to current state"
```

### Task 3: Final verification

**Files:**
- All docs changed in Tasks 1 and 2

- [ ] **Step 1: Check for stale references and deleted filenames**

Run:

```bash
rg -n "phase-2.6-results|phase-3-results|phase4-iterative-eval-summary|project-handoff|muse|architecture-and-results|275 pass|M2-B|Postgres \\+ pgvector|pgvector" README.md CLAUDE.md docs -g '!docs/superpowers/**'
```

Expected: no matches in retained docs.

- [ ] **Step 2: Spot-check the updated docs**

Run:

```bash
sed -n '1,120p' README.md
sed -n '1,160p' CLAUDE.md
sed -n '1,160p' docs/public-benchmark-diagnosis.md
sed -n '1,160p' docs/source-guide.md
sed -n '1,160p' docs/store-interface.md
```

Expected: the docs read as a compact current baseline, not a historical log.

- [ ] **Step 3: Commit any follow-up fixes**

If the spot-check exposes stale wording, fix it inline and commit once.
