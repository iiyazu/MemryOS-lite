# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

## Stale Artifact Scan

Phase start scan for active completion artifacts:

- `work/phase-8/ack.json`: absent in working tree; old tracked artifact is deleted and cannot be used as current ACK evidence.
- `work/phase-8/review_verdict.json`: absent in working tree; no current review verdict is available.
- `work/phase-8/result.md`: absent in working tree; no current result is available.

Additional stale artifact noted by dispatch:

- `work/phase-8/reviews/codex-review.md` exists, but predates the current `work/phase-8/context_bundle.md` and reviews a legacy defer/default-deprecation decision. It is not valid current Phase 8 review evidence.

Decision impact:

- Phase 8 must produce fresh `result.md`, `review_verdict.json`, and `ack.json` or `adjustment.md` from the current context bundle and reliability-gated eval evidence.

## Current Resolution

- Fresh `result.md`, `review_verdict.json`, and `ack.json` now exist and cite `work/phase-8/context_bundle.md`.
- `python .hermes-loop/hermes_hardening.py --write` reports `ack_gate: ok`.
- `work/phase-8/reviews/codex-review.md` remains stale; use `work/phase-8/reviews/codex-review-current.md` as the current review artifact.
