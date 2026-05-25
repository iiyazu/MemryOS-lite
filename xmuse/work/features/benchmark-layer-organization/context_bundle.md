# Context Bundle: benchmark-layer-organization

feature_id: benchmark-layer-organization
updated_at: 2026-05-25T07:52:36Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization

## Inputs Read

- `xmuse/prompts/slave_god_prompt.md`
- `xmuse/work/features/benchmark-layer-organization/slave_state.json`
- `xmuse/work/features/benchmark-layer-organization/blueprint.md`
- `xmuse/jobs/benchmark-layer-organization.json`
- `xmuse/contracts/slave_dispatch_template.json`
- `xmuse/dispatch/features/benchmark-layer-organization/slave_dispatch_prompt.md`

The assigned worktree does not carry `xmuse/prompts/slave_god_prompt.md` or
`xmuse/work/features/benchmark-layer-organization/blueprint.md`; the current
control-plane copies were read from `/home/iiyatu/projects/python/memoryOS`.
Writes stayed under the assigned feature worktree and feature-local artifacts.

## Prior State

- ACK was partial.
- Review verdict was FAIL for full-blueprint readiness.
- Previous implemented slices covered signed recall packet offsets and public
  benchmark movement/source-metric summaries.
- Remaining blockers included missing LLM credentials, absent ignored benchmark
  data in the worktree, pre-existing full-project mypy failures, and a default
  hard-eval mismatch.

## Current Repair Slice

This pass repairs the default v3 hard-eval mismatch while preserving the v1
fallback and v3 default. The deterministic eval evidence selector now:

- ignores generic acknowledgement evidence during answer selection;
- prefers update-marked evidence for ordinary slot-value questions, not only
  explicit temporal questions;
- widens habit/preference answer projection only when the v3 retrieved-message
  path has competing restatements.

The documented hard eval command now reports `accuracy=1.00` and `source=1.00`
under default settings. Local ignored symlinks were added for the public
benchmark JSON files and baseline comparison reports so relative public smoke
commands can resolve their inputs in this worktree.

## Residual Blockers

- Full public LongMemEval/LoCoMo LLM answer and judge gates remain blocked
  because `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` are unset.
- Full-project `uv run mypy src` still fails with 90 pre-existing errors in 12
  files. Targeted mypy for touched modules passes.

No benchmark score target, case-id shortcut, hard-coded answer,
archive-rag dependency, recall-pipeline default change, v1 fallback change, or
kernel default change was introduced.
