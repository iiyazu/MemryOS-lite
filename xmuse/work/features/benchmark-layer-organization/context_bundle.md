# Context Bundle: benchmark-layer-organization

feature_id: benchmark-layer-organization
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
target_branch: feat/phase-2.5-3-retrieval-agent
dispatch_base: 4c4712df763c652952a8066060bdb8bb4b37ba0b

## Active Inputs

- Root control-plane feature entry confirms branch `feat/benchmark-layer-organization`, worktree `/home/iiyatu/projects/python/memoryOS-benchmark-layer-organization`, target branch `feat/phase-2.5-3-retrieval-agent`.
- Root feature `slave_state.json` was `planned` before this turn.
- Blueprint goal is LoCoMo-first benchmark layer organization, with LongMemEval as a regression guard and no benchmark-specific hacks.
- Allowed product files include recall search/pipeline, v3 composer, public diagnostics, public movement, public benchmarks, and evals.

## Current Code Observations

- `RecallMemorySearcher` already supports direct hits, packet metadata, same-session neighbor expansion, session-diversified anchors, and diagnostics.
- `RecallPipeline` serializes recall diagnostics and exposes `recall_evidence_packets`.
- `V3ContextComposer` already records `component_accounting`, `final_context_trace`, component token/drop counts, and `locomo_neighbor_diagnostics`.
- `public_case_diagnostics` already separates retrieval, selected context, rendered context, answer evidence, citation, judge status, failure class, movement status, and evidence handoff.
- `public_case_movement` already emits `fail_to_pass`, `pass_to_fail`, `unchanged_pass`, `unchanged_fail`, and `new_case_no_baseline`.

## Bounded Slice

This Slave turn will not optimize benchmark scores or run full public LLM evals. The smallest useful real slice is to improve packet/neighbor diagnostics by making packet member offsets explicit and signed:

- Anchor offset: `0`.
- Previous same-session neighbor: negative offset.
- Next same-session neighbor: positive offset.
- The same offset metadata should be visible in `recall_evidence_packets`, evidence metadata, recall diagnostics, and v3 final context trace metadata when selected/rendered.

## Invariants To Preserve

- Default memory architecture remains `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains available.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite remains authoritative.
- No benchmark-specific case ids, answer strings, expected-source shortcuts, or dataset string overfitting.
- Benchmark scores are diagnostic/gate evidence only.
