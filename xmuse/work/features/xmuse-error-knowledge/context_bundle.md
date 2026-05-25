# feature: xmuse-error-knowledge

## Dispatch Context

- Feature id: `xmuse-error-knowledge`
- Branch: `feat/xmuse-error-knowledge`
- Worktree: `/home/iiyatu/projects/python/memoryOS-xmuse-error-knowledge`
- Runner type: `knowledge_maintainer`
- Source dispatch state was present in the active controller checkout; the assigned worktree initially contained only `blueprint.md`.

## Required Inputs Read

- `xmuse/prompts/slave_god_prompt.md`
- `xmuse/contracts/slave_dispatch_template.json`
- `xmuse/contracts/master_dispatch_template.json`
- `xmuse/work/features/xmuse-error-knowledge/blueprint.md`
- Active-controller `xmuse/work/features/xmuse-error-knowledge/slave_state.json`
- Active-controller `xmuse/master_state.json` feature entry for `xmuse-error-knowledge`

## Implementation Boundary

Allowed normal-mode writes:

- `xmuse/contracts/knowledge_maintainer_template.json`
- `xmuse/xmuse_error_knowledge.py`
- `xmuse/knowledge/**`
- `tests/test_xmuse_error_knowledge.py`
- `xmuse/work/features/xmuse-error-knowledge/*`

Bootstrap failure mode writes only:

- `xmuse/work/features/xmuse-error-knowledge/ack.json`
- `xmuse/work/features/xmuse-error-knowledge/result.md`

Forbidden writes:

- Master state/status files
- Master review and integrated test artifacts
- Approval artifacts
- Active prompts or active skills
- MemoryOS runtime, storage, recall, or context behavior

## Design Decision

Implement the maintainer as a standalone Xmuse-local Python module with a small
programmatic API. The module validates its dedicated contract before any normal
write, scans existing Xmuse artifacts digest-first, writes versioned knowledge
objects under `xmuse/knowledge/**`, rebuilds indexes from existing objects, and
emits feature-local handoff artifacts. It does not wire into MemoryOS runtime
paths or alter active prompts/skills.

## Risk Controls

- Contract missing or invalid means bootstrap no-op: only blocked `ack.json` and `result.md`.
- Valid contract with missing required inputs blocks without writing knowledge objects.
- Error records and cluster occurrences are keyed by source artifact digest and fingerprint.
- Free-form markdown diagnosis cannot confirm root cause.
- Same-feature retries are tracked separately from cross-feature recurrence.
- Human-edited `current.md` files are preserved by writing generated candidates under `revisions/`.
- Indexes are rebuilt last from objects that exist on disk.
