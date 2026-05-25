# feature: xmuse-error-knowledge

## Result

- Status: `usable`
- Knowledge run: `xmuse-error-knowledge-20260525T000000Z`
- Error records: 12
- Clusters touched: 7
- Draft methods touched: 2
- Draft skill proposals touched: 2
- Benchmark improvement claim: false

## Phase Matrix

| Phase | Status | Evidence |
|---|---|---|
| Phase 0 | complete | Dedicated `knowledge_maintainer` contract added; bootstrap missing/invalid contract no-op and semantically invalid contract no-op are tested. |
| Phase 1 | complete | Versioned run, error record, cluster, method, proposal, and index objects include source refs and digest metadata. |
| Phase 2 | complete | JSON-first and bounded Markdown scanner extracts representative Xmuse control-plane failures. |
| Phase 3 | complete | Stable fingerprints, digest idempotency, same-feature recurrence separation, and conservative promotion rules are tested. |
| Phase 4 | complete | Draft/quarantined methods and skill proposals are generated locally; human-edited `current.md` is preserved even when the marker remains. |
| Phase 5 | complete | Live maintainer pass wrote `xmuse/knowledge/runs/xmuse-error-knowledge-20260525T000000Z.json`. |

## Verification Evidence

- RED: `uv run pytest tests/test_xmuse_error_knowledge.py -q` failed before implementation because `xmuse/xmuse_error_knowledge.py` was missing.
- RED review regressions: focused test run failed for invalid-contract normal writes, same-feature allowlisted promotion, marker-preserving human edits, and missing run/index source metadata.
- RED lint regression: `uv run ruff check --no-cache xmuse/xmuse_error_knowledge.py tests/test_xmuse_error_knowledge.py` failed with 14 `E501` line-length errors.
- GREEN: `uv run pytest tests/test_xmuse_error_knowledge.py -q` -> `19 passed`.
- Repository lint: `uv run ruff check .` -> `All checks passed!`
- Explicit Xmuse lint: `uv run ruff check --no-cache xmuse/xmuse_error_knowledge.py tests/test_xmuse_error_knowledge.py` -> `All checks passed!`
- Scoped legacy Xmuse regression: `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py -q` -> `57 passed`.
- Live run: `uv run python xmuse/xmuse_error_knowledge.py --root . --run-id xmuse-error-knowledge-20260525T000000Z` -> usable, 12 records, 7 clusters, 2 methods, 2 skill proposals.

## Boundary Audit

- No MemoryOS runtime, store, recall, v1 fallback, v3 default, or kernel default behavior changed.
- No Master state/status, Master review, integrated test, approval, active prompt, or active skill files were modified by this feature.
- Knowledge output is local to `xmuse/knowledge/**`; methods and skill proposals are draft/quarantined only.
- `xmuse/knowledge/indexes/*.json` references were checked and point to existing objects.
- Benchmark scores are diagnostic evidence only; no improvement claim is made.

## Review Repairs

- Contract validation now requires exact normal/bootstrap write lists before normal mode can write knowledge files.
- Same-feature retries remain `method_candidate` even for allowlisted deterministic control-plane findings.
- Human edits below generated digest markers create revision candidates instead of overwriting `current.md`.
- Run and index objects now include `source_refs` and `source_digest`.
- Explicit Xmuse lint is recorded because the repository ruff config excludes `xmuse/**`.

## Blockers

- None.
