# phase: phase-1

# Spec - Phase 1 Letta Gap Contracts

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Inputs And Citations

- Context bundle citation: `.hermes-loop/work/phase-1/context_bundle.md` defines Phase 1 as contract and evidence planning only. It requires Letta comparison output to become MemoryOS-specific benchmark-impact contracts, consumes the Phase 0 case taxonomy, forbids code/test/docs/benchmark/state/blueprint behavior changes, and keeps Letta as a reference only.
- Dispatch citation: `.hermes-loop/work/phase-1/god_dispatch.json` binds this phase to `phase-1`, requires LongMemEval and LoCoMo impacts to stay separate, and requires every high-priority gap to map to a future failing test or Phase 0 benchmark case anchor.
- Research citation: `.hermes-loop/work/phase-1/research.md` identifies LongMemEval sampled pressure as mostly evidence-hit answer failure and LoCoMo sampled pressure as mostly retrieval/scope failure.
- Matrix citation: `.hermes-loop/work/phase-1/letta_gap_matrix.md` is the execute-lane source of truth for the P0/P1 priorities and explicitly preserves no-Letta-runtime, v1 fallback, v3 default, kernel opt-in, and conservative `source_hit` interpretation.
- Brainstorm citation: `.hermes-loop/work/phase-1/brainstorm.md` chooses the split P0 contract route by failure mode instead of a broad Letta subsystem port.

## Chosen Route

Use the split P0 contract route by observed failure mode:

```text
default v3 route and public case taxonomy
  -> LoCoMo archive scope and passage-role contracts
  -> LongMemEval answer citation and unsupported-answer contracts
  -> rendered evidence survival diagnostics
  -> P1 core-memory/kernel/accounting extensions only after P0 RED tests exist
```

This route adopts Letta semantics selectively: scoped archive attachment, passage role/source auditability, selected evidence citation, rendered component accounting, and traceable tool mutation. It rejects a broad Letta runtime port.

## P0 Contracts

1. Default v3 route and v1 fallback:
   - The real service/public benchmark path must emit v3 diagnostics by default without requiring callers to set `MEMORYOS_MEMORY_ARCH=v3`.
   - Explicit `MEMORYOS_MEMORY_ARCH=v1` must still route through the v1 fallback and must not emit v3-only composer diagnostics as if it were v3.
   - The v3 kernel remains off unless `MEMORYOS_AGENT_KERNEL=v1` is explicitly set.

2. Public taxonomy:
   - Public benchmark output must keep case-level taxonomy visible.
   - Required case statuses are `retrieval_miss`, `evidence_hit_answer_fail`, `unsupported_answer`, `supported_cited_answer`, and `pass` where applicable.
   - Aggregate score movement must not hide per-case regressions.

3. Archive attachment scope:
   - v3 archival retrieval must derive eligible archive scope from session, agent, project, or source attachments when scoped archives exist.
   - Silent global archival retrieval is not acceptable once attached archive records exist.
   - If no eligible scope exists, diagnostics must state whether retrieval was skipped, explicit global fallback was allowed, or no archive scope was available.

4. Passage source-vs-agent role:
   - Every benchmark-eligible v3 passage must declare whether it is source-backed evidence or agent-written archival memory.
   - Agent-written memory may assist retrieval, but it cannot satisfy source-grounded benchmark evidence unless it carries source refs to the original source/message.
   - Mixed or ambiguous source/agent passage role must be rejected or diagnosed before public evidence metrics consume it.

5. Answer citation and unsupported behavior:
   - A supported public answer must cite selected evidence ids and source ids.
   - Empty, missing, or insufficient selected evidence must produce an explicit unsupported/refusal answer artifact instead of uncited content.
   - `source_hit=true` is not enough to prove answer support.

6. Rendered evidence survival:
   - Future answer artifacts must expose whether selected evidence ids survived into the rendered answer prompt/context component that the answerer used.
   - Diagnostics must distinguish selected context items from rendered answer-prompt evidence.

7. Public benchmark diagnostics:
   - Reports must preserve retrieval evidence metrics, final projection/source-overlap metrics, answer support/citation status, v3 rendered evidence inclusion, and kernel trace presence as separate fields.
   - `source_hit` must be labeled and interpreted as final projection/source overlap, not pure evidence localization.

## P1 Contracts

1. Core-memory write policy:
   - Before any kernel core-memory mutation is expanded, core blocks need explicit read-only or write-policy semantics.
   - Source-backed or approved provenance remains mandatory.

2. Rendered component accounting:
   - Existing layer budget diagnostics should be extended with rendered component token estimates after the P0 evidence-survival contract exists.
   - This should extend, not replace, current v3 layer budget decisions.

3. Opt-in kernel/tool result expansion:
   - Kernel tooling remains opt-in.
   - Any future v3 memory mutation through tools must emit trace events, approval state when required, source refs, and tool result diagnostics.
   - Legacy v1 page/item tools must not be presented as v3 source-backed kernel tools.

## Benchmark Anchors

LongMemEval anchors:

- Evidence-hit answer failures: `e47becba`, `118b2229`, `51a45a95`.
- Retrieval miss: `58bf7951`.
- Stable pass: `1e043500`.
- Contract implication: answer/citation and rendered evidence survival work must not reclassify `58bf7951` as solved until evidence is recovered.

LoCoMo anchors:

- Evidence-hit answer failure: `conv-26_qa_001`.
- Retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- Contract implication: archive scope and passage-role work must treat `conv-26_qa_002` through `conv-26_qa_005` as retrieval/scope guards, not answer-projection guards.

## Non-Runtime Letta Rule

Letta is a reference design only. Phase 1 and later MemoryOS implementation phases must not import Letta schemas, managers, services, agent runtime, database providers, or tool executors as runtime dependencies. The acceptable output is MemoryOS-native contracts and tests inspired by Letta semantics.

## Source Hit Interpretation

`source_hit` is a final projection/source-overlap signal. It is not pure evidence localization and must not be used alone to claim retrieval success, answer support, or evidence use. Future diagnostics must continue to inspect episode evidence, planned evidence, selected v3 context evidence, rendered evidence inclusion, answer citation/support status, and case-level movement separately.

## Architecture Constraints

- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback.
- v3 remains the intended default memory architecture and must be verified through the real service/public benchmark path.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in. Kernel trace presence is not answer-quality evidence.
- SQLite remains the current authoritative store; filesystem outputs remain debug/eval artifacts.
- Phase 1 does not edit `src/`, `tests/`, `docs/`, `alembic/`, benchmark data, `.hermes-loop/state.json`, or `.hermes-loop/blueprint.md`.

## Anti-Demo Acceptance Criteria

Phase 1 is acceptable only if:

- `spec.md` and `plan.md` are phase-bound with `# phase: phase-1`.
- The chosen route is contract-first and MemoryOS-native.
- Every P0 contract maps to a future RED test shape or concrete Phase 0 case anchor in `plan.md`.
- LongMemEval and LoCoMo anchors remain separated.
- No broad "port Letta" task remains.
- No runtime Letta dependency is proposed.
- `source_hit` is interpreted conservatively.
- v1 fallback, v3 default verification, and kernel opt-in constraints remain explicit.
- No code, test, active docs, benchmark data, state, blueprint, or commit action is part of Phase 1.
