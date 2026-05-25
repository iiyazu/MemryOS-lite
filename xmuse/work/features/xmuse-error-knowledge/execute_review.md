# feature: xmuse-error-knowledge

## Execute Review

Verdict: PASS for feature-local execution.

Implemented:

- `xmuse/contracts/knowledge_maintainer_template.json`
- `xmuse/xmuse_error_knowledge.py`
- `tests/test_xmuse_error_knowledge.py`
- `xmuse/knowledge/**`
- feature-local handoff artifacts under `xmuse/work/features/xmuse-error-knowledge/`

Checks:

- Bootstrap failure mode writes only blocked `ack.json` and `result.md`.
- Semantically invalid contracts cannot enter normal write mode.
- Normal write boundary is limited to `xmuse/knowledge/**` and own feature artifacts.
- Error records and clusters include schema version, knowledge run id, extractor version, source path, digest, and source refs.
- Run and index objects include source refs and source digest metadata.
- Digest reprocessing does not inflate counts.
- Same-feature recurrence does not satisfy cross-feature promotion.
- Markdown-only diagnosis remains suspected.
- Human-edited draft `current.md` files are not overwritten.
- Active prompts, active skills, MemoryOS files, Master state/status, and approvals are not modified.

Verification:

- `uv run pytest tests/test_xmuse_error_knowledge.py -q` -> `20 passed`.
- `uv run ruff check .` -> `All checks passed!`
- `uv run ruff check --no-cache xmuse/xmuse_error_knowledge.py tests/test_xmuse_error_knowledge.py` -> `All checks passed!`
- `uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py -q` -> `57 passed`.
- `uv run python xmuse/xmuse_error_knowledge.py --root . --run-id xmuse-error-knowledge-20260525T000000Z` -> usable live knowledge run.

Remaining risk:

- The scanner uses intentionally bounded heuristics for Markdown artifacts. It is conservative by design and should be extended only with new tests for specific control-plane failure shapes.
