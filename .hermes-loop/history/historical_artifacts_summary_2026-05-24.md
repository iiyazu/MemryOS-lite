# Hermes Historical Artifacts Summary

Date: 2026-05-24

This file replaces the detailed historical Hermes phase work directories that
were removed from the active workspace. It is an audit summary, not an active
execution source.

## Authority

Current Hermes execution authority lives in:

- `.hermes-loop/master_state.json`
- `.hermes-loop/master_status.json`
- `.hermes-loop/master_blueprint.md`
- `.hermes-loop/master_config.json`
- `.hermes-loop/work/features/`
- `.hermes-loop/master/`
- `.hermes-loop/approvals/`

Legacy root-loop files under `.hermes-loop/legacy/root-loop/` remain audit-only.

## Deleted Detail Sets

The following detailed historical artifacts were summarized and removed from the
active repository surface:

- Old Hermes phase work directories: `phase-0` through `phase-18`.
- Manual full-chain 5-case run artifacts.
- Top-level `reflect_phase-*.md` notes.
- Old setup/window prompt files.
- Old `hermes-loop-architecture.html`.
- Obsolete `.hermes-loop/phases/README.md`.

These files were not active control-plane inputs after the Master migration.

## Preserved Summaries

The phase 0-18 history remains summarized in:

- `.hermes-loop/history/main_loop_phase0_18.md`
- `.hermes-loop/history/main_loop_phase0_18.json`

Key preserved facts:

- The original single-mainline Hermes loop completed through `phase-18`.
- The old root-loop state reached `DONE` with `current_phase_idx=19`.
- Default MemoryOS architecture became `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` remained the explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remained opt-in.
- SQLite remained the authoritative store.
- Phase 8 accepted governance baseline evidence:
  - LongMemEval 50 full-chain LLM judge: 47 pass / 3 fail.
  - LoCoMo 50 full-chain LLM judge: 30 pass / 20 fail.
- Phase 17 LoCoMo r3 diagnostic runs showed 8 pass / 2 fail for both baseline
  and opt-in repair smoke, with no fail-to-pass or pass-to-fail movement.
- Phase 18 was governance-only, with usable ACK, PASS review, and
  `continue_targeted` decision.

## Preserved Test Fixture

The only test dependency on detailed phase work was the phase-9 context bundle
used by public failure replay tests. That content is preserved as:

- `tests/fixtures/public_failure_replay/phase9_context_bundle.md`

Tests should not depend on `.hermes-loop/work/phase-*` directories.

## Continuing Bottlenecks

The historical detail supported these continuing diagnostics:

- LoCoMo remains the controlling bottleneck.
- `conv-26_qa_008` remains a useful retrieval-miss case.
- `conv-26_qa_006` remains a useful evidence-hit-answer-fail case.
- `conv-26_qa_002` through `conv-26_qa_005` remain source-miss judge-pass risk
  examples.
- LongMemEval-only evidence must not be used to claim chain-level improvement.

## Rule For Future Agents

Do not resurrect old phase work as active state. Future feature work should use
Master feature lanes, feature blueprints, artifacts, and explicit approval
gates.
