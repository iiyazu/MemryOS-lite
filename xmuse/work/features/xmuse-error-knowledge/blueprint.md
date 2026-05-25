# feature: xmuse-error-knowledge

## Goal / User-Visible Value

Create a Xmuse-local error knowledge layer that reads existing Xmuse
control-plane artifacts, extracts representative failures, clusters recurring
error patterns, and drafts local methods / skill proposals.

The value is to let Xmuse learn from repeated loop failures without modifying
MemoryOS memory, active prompts, active skills, Master decisions, or feature
implementation code.

## Non-Goals

- Do not write MemoryOS memory or change MemoryOS retrieval/runtime behavior.
- Do not install, enable, or modify active Codex skills.
- Do not auto-inject methods into Master/Slave prompts in v1.
- Do not modify Master state/status, Master review artifacts, approvals, or
  merge gates.
- Do not change v1 fallback, v2 recall opt-in, or agent kernel opt-in
  boundaries.
- Do not require Redis, Qdrant, A2A, AutoGen, or network services.
- Do not merge.

## Runner Type

`knowledge_maintainer`

`knowledge_maintainer` is a Xmuse maintenance runner, not Master and not a
feature Slave. It derives local knowledge from existing Xmuse artifacts. It has
no decision authority over review, merge, approval, prompts, skills, or
MemoryOS memory.

## Required Contract

Create:

```text
xmuse/contracts/knowledge_maintainer_template.json
```

Normal authorized mode allowed writes:

```text
xmuse/knowledge/**
xmuse/work/features/xmuse-error-knowledge/result.md
xmuse/work/features/xmuse-error-knowledge/review_verdict.json
xmuse/work/features/xmuse-error-knowledge/ack.json
xmuse/work/features/xmuse-error-knowledge/slave_state.json
```

Bootstrap exception:

If the knowledge maintainer contract is missing or does not authorize
`xmuse/knowledge/**`, the runner must no-op. It may write only:

```text
xmuse/work/features/xmuse-error-knowledge/ack.json
xmuse/work/features/xmuse-error-knowledge/result.md
```

Both must report blocked/no-op. It must not write `review_verdict.json`,
`slave_state.json`, or any `xmuse/knowledge/**` file in bootstrap failure
mode.

## Allowed Files / Modules

Normal authorized mode only:

- `xmuse/contracts/knowledge_maintainer_template.json`
- `xmuse/xmuse_error_knowledge.py`
- `xmuse/knowledge/**`
- `xmuse/work/features/xmuse-error-knowledge/blueprint.md`
- `xmuse/work/features/xmuse-error-knowledge/result.md`
- `xmuse/work/features/xmuse-error-knowledge/review_verdict.json`
- `xmuse/work/features/xmuse-error-knowledge/ack.json`
- `xmuse/work/features/xmuse-error-knowledge/slave_state.json`
- `tests/test_xmuse_error_knowledge.py`

Bootstrap failure mode only:

- `xmuse/work/features/xmuse-error-knowledge/ack.json`
- `xmuse/work/features/xmuse-error-knowledge/result.md`

## Required Inputs

Required for a normal scan:

```text
xmuse/master_state.json
xmuse/master_status.json
xmuse/contracts/master_dispatch_template.json
xmuse/contracts/slave_dispatch_template.json
xmuse/contracts/knowledge_maintainer_template.json
```

Failure modes:

- If `knowledge_maintainer_template.json` is valid but required state/input
  files are missing, the runner must not write knowledge files. It may write
  blocked `ack.json` / `result.md`.
- If `knowledge_maintainer_template.json` is missing or invalid, the runner
  enters bootstrap no-op mode and may write only blocked `ack.json` /
  `result.md`.

Optional scan inputs:

```text
xmuse/reports/latest.json
xmuse/reports/latest.md
xmuse/work/features/*/{ack.json,result.md,review_verdict.json,execute_review.md,slave_state.json,plan_final.md}
xmuse/master/features/*/{master_review.json,integrated_tests.json}
xmuse/approvals/*/{merge_approval_request.json,merge_approval.json,merge_decision.json,post_merge_verification.json}
```

Missing optional inputs produce diagnostics, not run failure.

## Knowledge Layout

```text
xmuse/knowledge/
  runs/<knowledge-run-id>.json
  error_records/<feature-id>/<record-id>.json
  clusters/<cluster-id>.json
  methods/<method-id>/{current.md,manifest.json,revisions/,tombstones/}
  skill_proposals/<proposal-id>/{current.md,manifest.json,revisions/,tombstones/}
  indexes/{error_index.json,cluster_index.json,method_index.json,proposal_index.json}
```

## Behavioral Invariants

- Read-only over existing Xmuse artifacts.
- Writes only to `xmuse/knowledge/**` and own feature artifacts in normal
  authorized mode.
- Writes only blocked `ack.json` / `result.md` in bootstrap failure mode.
- Every object includes `schema_version`, `knowledge_run_id`,
  `extractor_version`, source artifact path, digest, and source refs.
- Reprocessing the same artifact digest must not inflate counts.
- Same-feature retries cannot satisfy cross-feature promotion.
- Markdown free-form diagnosis cannot mark `root_cause_status=confirmed`.
- `confirmed` root cause requires verification evidence or allowlisted
  deterministic invariant.
- Methods and skill proposals are draft/quarantined by default.
- Human edits must not be silently overwritten.
- Tombstones are append-only metadata.
- Index updates must not leave references to missing objects after partial
  failure.

## Promotion Rules

- ErrorRecord: auto-create for representative failures.
- Cluster: auto-create/update by stable fingerprint.
- `observed -> method_candidate`: automatic when `occurrence_count >= 2`, but
  non-authoritative.
- `method_candidate -> method_created`: requires cross-feature recurrence,
  independent cross-run recurrence, or allowlisted deterministic control-plane
  invariant.
- `method_created -> skill_candidate`: draft only; requires multiple mature
  methods or repeated cross-feature method references.
- Environment, transient, dirty-worktree, missing optional-file, baseline-drift,
  or unrelated pre-existing failures cannot promote without independent
  evidence.

## Deterministic Invariant Allowlist

Only these control-plane findings may support confirmed root cause or method
promotion without cross-feature recurrence:

- missing required artifact
- invalid JSON artifact
- ACK exists but `ack_level != usable`
- `review_verdict.json` exists but verdict is not `PASS`
- required `result.md` missing
- `integrated_tests.json` missing when merge was requested
- approval artifact digest mismatch
- stale target HEAD against integrated-test evidence
- merge requested without explicit approval
- Master/Slave/knowledge-maintainer contract write-boundary violation

## Phased Execution Plan

This feature must be implemented in bounded phases. Each phase produces a
testable layer and records evidence before the next phase expands scope.

### Phase 0: Contract And Bootstrap Boundary

Goal: introduce the `knowledge_maintainer` runner boundary without allowing
normal Xmuse Master or Slave write permissions to leak into
`xmuse/knowledge/**`.

Allowed work:

- Add `xmuse/contracts/knowledge_maintainer_template.json`.
- Define normal authorized writes and bootstrap no-op writes.
- Add bootstrap tests proving missing/invalid contract writes only blocked
  `ack.json` / `result.md`.

Exit gate:

- Contract tests pass.
- Bootstrap failure mode cannot write `xmuse/knowledge/**`,
  `review_verdict.json`, or `slave_state.json`.
- Master/Slave contracts remain unchanged unless explicitly amended for this
  runner.

### Phase 1: Knowledge Object Schemas And Atomic Index Writes

Goal: define durable, versioned knowledge objects before extracting real
artifacts.

Allowed work:

- Add schema models for run summaries, error records, clusters, method
  manifests, proposal manifests, indexes, revisions, and tombstones.
- Add source artifact references with paths, digests, artifact type, feature id,
  and source run id when present.
- Add atomic-enough index update behavior so failed writes cannot leave indexes
  pointing to missing objects.

Exit gate:

- Unit tests prove required schema fields, source refs, digest fields, and
  schema version are present.
- Partial write failure tests prove indexes do not reference missing records,
  clusters, methods, or proposals.

### Phase 2: Structured Artifact Scanner

Goal: scan existing Xmuse artifacts digest-first and extract representative
failures without duplicate-count inflation.

Allowed work:

- Parse JSON artifacts first.
- Parse markdown artifacts with bounded heuristics.
- Extract missing artifacts, invalid JSON, failed commands, blocking findings,
  stale gates, approval mismatches, and explicit eval/baseline drift.
- Treat optional inputs as diagnostics when absent.

Exit gate:

- Tests prove digest-based idempotency.
- Reprocessing the same artifact digest does not inflate occurrence,
  cross-run, or cross-feature counts.
- Duplicate failures inside one artifact collapse to one cluster occurrence
  unless distinct commands or evidence spans exist.

### Phase 3: Clustering And Promotion Safety

Goal: cluster recurring failures and enforce conservative promotion rules.

Allowed work:

- Create/update clusters by stable fingerprint.
- Track same-feature, cross-feature, and independent cross-run recurrence
  separately.
- Enforce deterministic invariant allowlist.
- Keep environment, transient, dirty-worktree, baseline drift, and unrelated
  pre-existing failures from promoting without independent evidence.

Exit gate:

- Tests prove same-feature retries cannot satisfy cross-feature promotion.
- Tests prove markdown-only free-form diagnosis cannot confirm root cause.
- Tests prove root cause confirmation requires verification evidence or an
  allowlisted deterministic invariant.

### Phase 4: Draft Method And Skill Proposal Generation

Goal: generate useful local drafts without activating them or hiding
uncertainty.

Allowed work:

- Generate draft/quarantined method documents from eligible clusters.
- Generate draft skill proposals from mature method groups.
- Preserve human edits by creating revision candidates or quarantining updates
  instead of overwriting `current.md`.
- Write append-only tombstones for archived/superseded objects.

Exit gate:

- Tests prove generated methods and skill proposals remain local drafts.
- Tests prove active prompts and active skills are not modified.
- Tests prove human-edited `current.md` is not silently overwritten.

### Phase 5: Integrated Knowledge Run And Handoff

Goal: run the maintainer over fixture or live Xmuse artifacts and produce a
bounded handoff for Master review.

Required verification:

```bash
uv run pytest tests/test_xmuse_error_knowledge.py -q
uv run ruff check .
```

Additional verification if touched:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py -q
```

Exit gate:

- `result.md` includes a phase-by-phase completion matrix.
- `ack.json` records usable/blocked/failed status with exact blockers.
- `review_verdict.json` records PASS/FAIL and whether the feature may advance
  to Master review.
- `xmuse/knowledge/runs/<knowledge-run-id>.json` records scanned
  artifacts, generated/updated objects, diagnostics, and blocked/promoted
  counts.
- No merge, Master-state/status write, approval write, prompt write, active
  skill write, or MemoryOS memory write is performed.

## Required Tests

- Contract missing writes only blocked `ack.json` / `result.md`; no knowledge
  files.
- Scanner refuses writes outside allowed paths.
- Missing optional reports produce diagnostics only.
- Digest-based scan is idempotent.
- Duplicate failures inside one artifact do not inflate cluster counts.
- Distinct failed commands can create distinct records.
- Missing ACK/result/review artifacts are extracted.
- Mypy failure and hard-eval drift produce distinct fingerprints.
- Same-feature retries do not satisfy cross-feature promotion.
- Markdown-only diagnosis cannot confirm root cause.
- Partial write failure does not leave indexes pointing to missing records,
  clusters, methods, or proposals.
- Generated methods/proposals remain local drafts.
- Master state/status, approvals, prompts, skills, and MemoryOS memory are not
  modified.

## Completion Criteria

- Dedicated `knowledge_maintainer` contract exists and is tested.
- Knowledge scan produces idempotent records, clusters, draft methods, and draft
  skill proposals.
- Bootstrap no-op behavior is tested.
- Promotion safety rules are enforced.
- All required tests pass.
- Handoff artifacts record scanned inputs, generated/updated object ids,
  diagnostics, and blocked/promoted counts.

## Review Failure Criteria

- Writes outside `xmuse/knowledge/**` or own feature artifacts.
- Writes knowledge files in bootstrap failure mode.
- Bootstrap failure mode writes `review_verdict.json` or `slave_state.json`.
- Master/Slave contracts are bypassed instead of adding a dedicated knowledge
  contract.
- Active prompts or active skills are modified.
- MemoryOS memory/store files are modified.
- Records lack source paths, digests, schema version, extractor version, or
  knowledge run id.
- Reprocessing creates duplicate records or inflated counts.
- A single feature retry satisfies cross-feature promotion.
- Root cause is marked confirmed without verification evidence or allowlisted
  deterministic invariant.
- One-off environment/baseline failures promote beyond candidate.
- Indexes reference missing records, clusters, methods, or proposals.
- Human edits are overwritten silently.
- Skill proposals are installed or activated.
- MemoryOS v1 fallback, v2 recall opt-in, or agent kernel opt-in behavior
  changes.

## Handoff Artifacts

- `xmuse/work/features/xmuse-error-knowledge/result.md`
- `xmuse/work/features/xmuse-error-knowledge/review_verdict.json`
- `xmuse/work/features/xmuse-error-knowledge/ack.json`
- `xmuse/work/features/xmuse-error-knowledge/slave_state.json`
- `xmuse/knowledge/runs/<knowledge-run-id>.json`
- phase-by-phase completion matrix in `result.md`

## Master Gates

Master review:

- verify write boundaries and contract compliance
- inspect generated knowledge objects and indexes
- confirm no prompt, skill, MemoryOS, Master-state, approval, or merge-gate
  mutation

Integrated tests:

- run `uv run pytest tests/test_xmuse_error_knowledge.py -q`
- run relevant current legacy-named Xmuse hardening/reporter tests if touched
- run `uv run ruff check .`

Merge approval:

- requires explicit merge approval artifact and fresh target validation
- Master must not self-sign external approval

Post-merge verification:

- rerun knowledge scan in dry-run or fixture mode
- confirm no unexpected writes outside allowed paths
