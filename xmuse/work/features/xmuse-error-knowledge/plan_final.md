# Xmuse Error Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Xmuse-local error knowledge maintainer that extracts repeated control-plane failures into quarantined knowledge objects without modifying MemoryOS behavior, Master decisions, prompts, active skills, or approval gates.

**Architecture:** Add a dedicated `knowledge_maintainer` contract and one standalone scanner/writer module. The module validates write authority, scans Xmuse artifacts digest-first, emits schema-versioned records/clusters/draft methods/draft skill proposals under `xmuse/knowledge/**`, rebuilds indexes from existing objects, and writes feature-local handoff artifacts.

**Tech Stack:** Python 3.11 standard library, pytest, JSON/Markdown artifacts, filesystem atomic replace.

---

## Files

- Create: `xmuse/contracts/knowledge_maintainer_template.json`
- Create: `xmuse/xmuse_error_knowledge.py`
- Create: `tests/test_xmuse_error_knowledge.py`
- Create/update: `xmuse/knowledge/**`
- Update: `xmuse/work/features/xmuse-error-knowledge/context_bundle.md`
- Update: `xmuse/work/features/xmuse-error-knowledge/execute_goal.md`
- Update: `xmuse/work/features/xmuse-error-knowledge/result.md`
- Update: `xmuse/work/features/xmuse-error-knowledge/execute_review.md`
- Update: `xmuse/work/features/xmuse-error-knowledge/review_verdict.json`
- Update: `xmuse/work/features/xmuse-error-knowledge/ack.json`
- Update: `xmuse/work/features/xmuse-error-knowledge/slave_state.json`

## Tasks

- [ ] Write RED tests for bootstrap missing/invalid contract no-op behavior.
- [ ] Write RED tests for allowed write boundaries and missing optional diagnostics.
- [ ] Write RED tests for required schema fields, source refs, and digest metadata.
- [ ] Write RED tests for digest idempotency and duplicate-collapse behavior.
- [ ] Write RED tests for missing artifact, invalid JSON, failed command, mypy, hard-eval drift, and review/ACK extraction.
- [ ] Write RED tests for same-feature recurrence, markdown-only diagnosis, root-cause confirmation, and promotion rules.
- [ ] Write RED tests for partial write failure index safety.
- [ ] Write RED tests for draft method/proposal generation, active prompt/skill non-mutation, and human-edit preservation.
- [ ] Run the focused test file and confirm it fails because `xmuse_error_knowledge` and the contract are missing.
- [ ] Add `knowledge_maintainer_template.json` with normal and bootstrap write contracts.
- [ ] Implement contract validation, path-boundary enforcement, bootstrap blocked artifact writing, and required-input checks.
- [ ] Implement source refs, digests, schema-versioned run/error/cluster/method/proposal/index objects.
- [ ] Implement JSON-first and bounded Markdown scanning with deterministic fingerprints.
- [ ] Implement idempotent record/cluster updates with same-feature, cross-feature, and source-run recurrence tracking.
- [ ] Implement conservative promotion and quarantined draft method/proposal generation.
- [ ] Implement human-edit preservation for `current.md` and append-only tombstone helpers.
- [ ] Rebuild indexes only from existing on-disk objects and write indexes last.
- [ ] Run `uv run pytest tests/test_xmuse_error_knowledge.py -q` until green.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py -q` if touched.
- [ ] Run a live feature-local maintainer pass to create `xmuse/knowledge/runs/<knowledge-run-id>.json`.
- [ ] Write `result.md`, `execute_review.md`, `review_verdict.json`, `ack.json`, and final `slave_state.json`.
- [ ] Review the diff for forbidden writes, MemoryOS runtime changes, benchmark score targets, prompt/skill mutation, and stale indexes.
- [ ] Commit the focused feature changes.

## Non-Goals

- Do not write MemoryOS memory or change MemoryOS runtime behavior.
- Do not install, enable, or modify active Codex skills.
- Do not modify active prompts.
- Do not edit Master state/status, Master review, integrated test, approval, or merge artifacts.
- Do not change v1 fallback, v2 recall opt-in, v3 default, or kernel opt-in behavior.
- Do not use benchmark scores as goals.

## Usable ACK Conditions

- Focused Xmuse error knowledge tests pass.
- Required lint passes.
- A real maintainer run writes bounded `xmuse/knowledge/**` output.
- `result.md` includes the phase completion matrix and exact verification evidence.
- `review_verdict.json` is PASS with conservative review eval decision.
- `ack.json` has `ack_level = "usable"` and records branch, worktree, head ref, verification commands, v3/v1/kernel preservation, and no benchmark improvement claim.
