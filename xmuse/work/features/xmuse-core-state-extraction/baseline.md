# xmuse-core-state-extraction Baseline

Feature: `xmuse-core-state-extraction`
Recorded: 2026-05-25
Branch: `feat/xmuse-core-state-extraction`
Worktree: `/home/iiyatu/projects/python/memoryOS-xmuse-core-state-extraction`
Head: `5f69b712a3adb22e9840dc211d1ff200c7f68ecb`

## Dispatch Inputs

- Read `xmuse/prompts/slave_god_prompt.md`.
- Read `xmuse/work/features/xmuse-core-state-extraction/slave_state.json`.
- Read `xmuse/work/features/xmuse-core-state-extraction/blueprint.md`.
- Attempted to read `xmuse/jobs/xmuse-core-state-extraction.json`; the file is absent in this worktree. Implementation proceeds from the feature-local blueprint and records this as a non-blocking dispatch artifact gap.

## Initial Worktree State

- `git status --short`: clean.
- Current branch: `feat/xmuse-core-state-extraction`.
- Worktree is linked to `/home/iiyatu/projects/python/memoryOS/.git`.

## Baseline Verification

Command:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q
```

Result:

```text
113 passed in 0.83s
```

## Baseline Active Sources

- Active runtime dir: `xmuse/`.
- Active state source: `xmuse/master_state.json`.
- Active status projection files: `xmuse/master_status.json`, `xmuse/master_status.md`.
- Current compatibility facade: `xmuse/hermes_hardening.py`.
- Reporter entrypoint: `xmuse/hermes_reporter.py`.
- Launcher entrypoint: `xmuse/god_launcher.sh`.
- Legacy root-loop files remain audit-only under `xmuse/legacy/root-loop/`.

## Baseline Blast Radius

- `control_plane_only`: true
- `state_schema_change`: false
- `launcher_change`: false
- `reporter_change`: false
- `migration_required`: true
- `product_code_change`: false
- `memoryos_runtime_change`: false
