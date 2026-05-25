# feature: xmuse-error-knowledge

## Result

- Status: `usable`
- Knowledge run: `xmuse-error-knowledge-20260525T000000Z`
- Error records: 22
- Clusters touched: 13
- Draft methods touched: 2
- Draft skill proposals touched: 2
- Benchmark improvement claim: false

## Phase Matrix

| Phase | Status | Evidence |
|---|---|---|
| Phase 0 | complete | Dedicated `knowledge_maintainer` contract added; bootstrap missing/invalid contract no-op and semantically invalid contract no-op are tested. |
| Phase 1 | complete | Versioned run, error record, cluster, method, proposal, and index objects include source refs and digest metadata. |
| Phase 2 | complete | JSON-first and bounded Markdown scanner extracts representative Xmuse control-plane failures, including JSON blocking findings, stale target gates, and approval blockers. |
| Phase 3 | complete | Stable fingerprints, digest idempotency, same-feature recurrence separation, deterministic duplicate collapse, and conservative promotion rules are tested. |
| Phase 4 | complete | Draft/quarantined methods and skill proposals are generated locally; human-edited `current.md` and proposal tombstones are preserved across reruns. |
| Phase 5 | complete | Live maintainer pass refreshed `xmuse/knowledge/runs/xmuse-error-knowledge-20260525T000000Z.json`. |

## Verification Evidence

- Focused suite: `uv run pytest tests/test_xmuse_error_knowledge.py -q` -> `23 passed in 1.26s`.
- Repository lint: `uv run ruff check .` -> `All checks passed!`
- Explicit Xmuse lint: `uv run ruff check --no-cache xmuse/xmuse_error_knowledge.py tests/test_xmuse_error_knowledge.py` -> `All checks passed!`
- Scoped legacy Xmuse regression: `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py -q` -> `57 passed in 0.22s`.
- Live run: `uv run python xmuse/xmuse_error_knowledge.py --root . --run-id xmuse-error-knowledge-20260525T000000Z` -> usable, 22 records, 13 clusters, 2 methods, 2 skill proposals.
- Index audit: `python3 - <<'PY' ... index reference audit ... PY` -> `index references ok`.
- Full-suite diagnostic: `uv run pytest -q` was interrupted after repeated unrelated `httpx.ConnectTimeout` failures while public benchmark tests attempted to initialize `FastEmbedClient` and download HuggingFace model metadata.

## Boundary Audit

- No MemoryOS runtime, store, recall, v1 fallback, v3 default, or kernel default behavior changed by this feature.
- No Master state/status, Master review, integrated test, approval, active prompt, or active skill files were modified by this feature.
- Knowledge output is local to `xmuse/knowledge/**`; methods and skill proposals are draft/quarantined only.
- Benchmark scores are diagnostic evidence only; no improvement claim is made.
- `xmuse/knowledge/indexes/*.json` references were checked and point to existing objects.

## Review Repairs

- Scanner extracts each missing terminal artifact independently instead of skipping a feature when any terminal artifact exists.
- Regression coverage proves a feature with only `ack.json` emits missing `result.md` and `review_verdict.json` records.
- Scanner walks structured JSON evidence for `blocking_findings`, failed command objects, stale target gates, and missing explicit approval blockers.
- Deterministic invariant duplicates collapse per artifact/fingerprint while distinct command evidence spans remain distinct.
- Cluster recomputation prunes missing record references before writing counts and indexes.
- Existing focused tests were tightened with complete terminal artifacts where missing-file extraction is not under test.
- Skill proposal manifests preserve existing tombstone metadata and original creation time when regenerated.
- Regression coverage proves rerunning the maintainer does not reset proposal `tombstones` or churn `created_at`.

## Dispatch Diagnostics

- `xmuse/jobs/xmuse-error-knowledge.json` is absent in this worktree.
- The checked-out `xmuse/master_state.json` does not contain an `xmuse-error-knowledge` feature entry.
- Feature-local blueprint, state, branch, worktree, and handoff artifacts are present and remain the authoritative local assignment inputs for this run.

## Blockers

- None.
