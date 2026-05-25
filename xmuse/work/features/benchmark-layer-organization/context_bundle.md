# Context Bundle: benchmark-layer-organization

feature_id: benchmark-layer-organization
updated_at: 2026-05-25T06:43:25Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization

## Inputs Read

- `/home/iiyatu/projects/python/memoryOS/xmuse/prompts/slave_god_prompt.md`
- `/home/iiyatu/projects/python/memoryOS/xmuse/contracts/slave_dispatch_template.json`
- `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/benchmark-layer-organization/slave_state.json`
- `/home/iiyatu/projects/python/memoryOS/xmuse/work/features/benchmark-layer-organization/blueprint.md`
- `/home/iiyatu/projects/python/memoryOS/xmuse/jobs/benchmark-layer-organization.json`
- `/home/iiyatu/projects/python/memoryOS/xmuse/dispatch/features/benchmark-layer-organization/slave_dispatch_prompt.md`

The assigned worktree did not contain `xmuse/` at dispatch time, so control-plane
inputs were read from the main checkout. Writes in this pass stay under the
assigned worktree.

## Prior State

- Previous ACK was partial.
- Previous review verdict was FAIL for full-blueprint readiness.
- Prior implemented slices already covered signed recall packet offsets and
  regular public benchmark movement-summary artifacts.
- Remaining full-blueprint blockers were missing LLM credentials, absent raw
  public benchmark JSON files in this worktree, project-wide mypy failures, and
  a hard-eval baseline mismatch.

## Current Repair Slice

This pass adds source-metric movement accounting to regular public comparison
movement summaries. Verdict movement is now separate from movement in:

- `source_hit`
- `planned_evidence_source_hit_at_5`
- `episode_source_hit_at_10`

Post-review hardening adds an explicit note that metric movement omits cases
with missing baseline or current metric values.

No benchmark score target, case-id shortcut, hard-coded answer, archive-rag
dependency, default recall-pipeline change, v1 fallback change, or kernel default
change was introduced.
