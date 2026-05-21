# phase: phase-1

# PLAN_STORM Brainstorm - Letta Gap Matrix To Testable Contracts

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Inputs Consumed

- Context bundle citation: `.hermes-loop/work/phase-1/context_bundle.md` defines Phase 1 as contract and evidence planning only, requires the Letta comparison to become MemoryOS-specific benchmark-impact contracts, and forbids `src/`, `tests/`, docs, benchmark data, state, blueprint, or runtime behavior changes in this phase.
- Dispatch citation: `.hermes-loop/work/phase-1/god_dispatch.json` requires `PLAN_STORM` to keep LongMemEval and LoCoMo impacts separate, map high-priority gaps to future failing tests or Phase 0 cases, and preserve no-Letta-runtime, v1 fallback, v3 default, and kernel opt-in constraints.
- Research citation: `.hermes-loop/work/phase-1/research.md` separates LongMemEval evidence-hit-answer-fail pressure from LoCoMo retrieval/scope pressure and warns against treating `source_hit` as pure evidence localization.
- Matrix citation: `.hermes-loop/work/phase-1/letta_gap_matrix.md` identifies P0 contracts for archive attachment/scope, passage source-vs-agent role, answer citation/unsupported behavior, default v3 routing verification, and case-level public benchmark diagnostics.

This file replaces stale Phase 3 core-memory brainstorm content. It is a plan-lane contract brainstorm only; it does not implement or change behavior.

## Route Options

### Option A - Answer-First Contract Route

Order future contracts around the LongMemEval evidence-hit-answer-fail cases first:

1. Define a benchmark answer object with final answer, cited selected evidence ids, cited source ids, unsupported/refusal status, and failure taxonomy.
2. Add rendered prompt/component accounting only enough to prove selected evidence reached the final answer prompt.
3. Use `e47becba`, `118b2229`, `51a45a95`, and `conv-26_qa_001` as future RED anchors.
4. Defer archive attachment/scope and passage-role invariants until after answer evidence survives into public output.

Tradeoffs:

- Strongest direct fit for LongMemEval sampled failures because three of five failures already had evidence but missed the answer.
- Produces a clean anti-demo guard: retrieval success cannot be claimed unless cited selected evidence supports the answer.
- Too weak for LoCoMo because four sampled failures are retrieval misses. It risks improving LongMemEval diagnostics while leaving LoCoMo scope failures under-specified.
- Could tempt prompt-only fixes unless the contract explicitly binds answers to selected evidence ids and unsupported/refusal states.

Verdict: useful but incomplete. It should be part of the route, not the whole ordering.

### Option B - Recommended: Split P0 Contract Route By Failure Mode

Order future contracts by benchmark failure mode, not by Letta subsystem order:

1. Lock the public evaluation taxonomy and v3 route contract first:
   - default service/public benchmark path must expose v3 diagnostics without explicit `MEMORYOS_MEMORY_ARCH=v3`;
   - explicit `MEMORYOS_MEMORY_ARCH=v1` must preserve the fallback path;
   - `source_hit` remains final projection/source overlap, not pure evidence localization;
   - reports keep case-level `retrieval_miss`, `evidence_hit_answer_fail`, `unsupported_answer`, and `supported_cited_answer`.
2. Add LoCoMo retrieval/scope contracts:
   - v3 archival retrieval derives eligible archive scope from session/agent/project/source attachments or emits a diagnostic reason for no scope/global fallback;
   - benchmark-eligible passages declare a source-vs-agent role, and agent-written memory cannot satisfy source-grounded evidence without source refs.
3. Add LongMemEval answer-use contracts:
   - supported answers must cite selected evidence ids and source ids;
   - empty or unsupported selected evidence must produce unsupported/refusal output rather than uncited content;
   - selected evidence inclusion must survive into rendered answer artifacts.
4. Defer P1 work until P0 contracts are RED-tested:
   - read-only/write-policy core-memory mutation semantics;
   - rendered component token accounting beyond selected evidence inclusion;
   - opt-in kernel tool-result expansion and core-memory tools.

Tradeoffs:

- Directly follows the matrix P0 priorities while preserving benchmark-specific diagnosis.
- Avoids hiding LoCoMo retrieval misses behind LongMemEval answer work.
- Avoids hiding LongMemEval answer failures behind retrieval/source-overlap work.
- Produces future tests that can fail before implementation without relying on Letta runtime or expected-answer hacks.
- Requires discipline in later phases because it spans public benchmark reports, v3 routing, archival retrieval, passage contracts, and answer artifacts.

Verdict: recommended. This is the best route for turning the Letta gap matrix into future testable MemoryOS contracts without demo-only phase completion.

### Option C - Letta Subsystem Order Route

Order future contracts to mirror Letta architecture:

1. Core memory block/write-policy contract.
2. Archive and passage managers/scope contract.
3. Context component accounting contract.
4. Tool execution and kernel trace contract.
5. Public answer/citation contract.

Tradeoffs:

- Easy to explain as a Letta-style architecture map.
- Gives each subsystem a clean local contract.
- Misaligned with Phase 0 evidence: kernel/core-memory work is not the main sampled public-benchmark bottleneck.
- Risks broad "port Letta" planning and plan-only artifacts before benchmark-critical answer/retrieval contracts are nailed down.
- Could defer public case-level diagnostics too late, allowing aggregate or trace-only progress to look usable.

Verdict: reject as primary ordering. Use Letta semantics as references inside MemoryOS contracts, not as the phase order.

## Chosen Route

Choose Option B: split P0 contracts by observed failure mode and keep public case-level taxonomy as the guardrail.

The future contract chain should be:

```text
v3 route and case taxonomy contract
  -> LoCoMo archive scope and passage-role contracts
  -> LongMemEval answer citation and unsupported-answer contracts
  -> rendered evidence survival/accounting contracts
  -> opt-in kernel/tool mutation contracts only after benchmark evidence contracts hold
```

This route treats Letta as a design reference, not a dependency. MemoryOS should adopt the useful semantics: scoped archive attachment, passage role/source auditability, selected evidence citation, component accounting, and traceable tool mutation. It should not import Letta services, managers, schemas, or runtime.

## Future Contract Set

P0 contracts to draft next:

- Default v3 routing: default settings through service/public benchmark must produce v3 diagnostics; explicit `MEMORYOS_MEMORY_ARCH=v1` must keep v1 fallback behavior.
- Case-level diagnostics: public output must preserve retrieval miss versus evidence-hit answer fail versus unsupported answer versus supported cited answer.
- Archive scope: archival retrieval must use attachment-derived eligible archives or report why no scope was available; silent global retrieval is not acceptable once scoped archives exist.
- Passage role: benchmark evidence must distinguish source-backed passages from agent-written archival memory; agent summaries cannot count as source evidence without source refs.
- Answer citation: supported answers must cite selected evidence ids and source ids; unsupported or empty evidence must be explicit.

P1 contracts to hold until after P0 RED tests exist:

- Rendered component accounting: selected evidence ids must be visible in the final rendered answer-prompt component map, with token estimates later.
- Core-memory write policy: read-only/write-policy semantics should gate any future kernel core-memory mutation.
- Kernel/tool result: kernel remains opt-in, emits trace/tool result/source-ref diagnostics, and does not become benchmark success evidence by trace presence alone.

## LongMemEval Impact

LongMemEval Phase 0 smoke pressure is mainly answer-use, not retrieval:

- Evidence-hit answer failures: `e47becba`, `118b2229`, `51a45a95`.
- Retrieval miss: `58bf7951`.
- Pass: `1e043500`.

For LongMemEval, future RED tests should prove that selected evidence reaches the final answer artifact and that supported answers cite the selected evidence ids/source ids that justify the answer. `58bf7951` must remain classified as retrieval miss until evidence is actually recovered; answer-citation work must not hide it.

Expected contract value:

- prevents "retrieval succeeded" from being counted as answer success;
- exposes evidence-hit-answer-fail cases at case level;
- forces unsupported/refusal behavior when selected evidence is absent or insufficient;
- reduces risk that `source_hit` is misread as evidence localization.

## LoCoMo Impact

LoCoMo Phase 0 smoke pressure is mainly retrieval and scope:

- Evidence-hit answer failure: `conv-26_qa_001`.
- Retrieval misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

For LoCoMo, future RED tests should focus first on scoped archival eligibility and passage/source-role auditability. A synthetic two-archive fixture should fail when an unattached archive with a stronger lexical match is selected. Public benchmark diagnostics should continue to show which LoCoMo cases lack planned/episode evidence instead of burying them under answer-only work.

Expected contract value:

- prevents global archival top-k pollution;
- separates absent source evidence from answer projection failure;
- keeps `conv-26_qa_001` as an answer-use guard while treating `conv-26_qa_002` through `conv-26_qa_005` as retrieval/scope guards;
- makes future LoCoMo movement attributable to retrieval/scope changes rather than aggregate score drift.

## Constraints To Preserve

- v1 fallback remains available with `MEMORYOS_MEMORY_ARCH=v1`; no contract may remove or silently bypass it.
- v3 remains the intended default memory architecture, but future tests must verify the real service/public benchmark path instead of relying only on settings documentation.
- The v3 kernel remains opt-in with `MEMORYOS_AGENT_KERNEL=v1`; kernel trace presence is not answer-quality evidence.
- Letta is a reference design only. No runtime dependency, import path, database dependency, manager reuse, or schema inheritance from Letta should be introduced.
- No benchmark case-id hacks, expected-answer leaks, or dataset-specific string rules.
- No Phase 1 code, test, docs, benchmark data, state, or blueprint edits.

## What Would Count As Demo-Only Or Plan-Only

- Reporting only aggregate benchmark score movement while hiding per-case regressions.
- Calling `source_hit` evidence localization without checking planned/episode evidence, selected evidence ids, and final answer support.
- Claiming progress from a prompt wording change when the answer artifact has no cited selected evidence ids.
- Treating a kernel trace sequence as benchmark usability while final answers still fail.
- Leaving "port Letta" as an open-ended task instead of naming MemoryOS contracts and future RED anchors.
- Writing plans that do not identify the failing tests, synthetic fixtures, or Phase 0 case anchors that would prove the contract.
- Allowing silent global archival search after archive attachments exist.
- Counting agent-written summaries as source-grounded evidence without source refs.

## Risks

- Default-route ambiguity: if the public benchmark path does not actually exercise v3 by default, later benchmark claims can be invalid even with good contracts.
- Scope overreach: trying to adopt Letta's full AgentV3/tool runtime would dilute the immediate benchmark contracts and violate the no-runtime-dependency constraint.
- Benchmark conflation: LongMemEval answer failures and LoCoMo retrieval misses require different contracts; one aggregate priority can hide the other.
- Citation formalism risk: answers could mechanically cite ids without the cited evidence supporting the claim; future tests need both cited ids and expected fact/support checks.
- Diagnostic drift: adding new fields without preserving existing taxonomy can make regressions harder to compare with Phase 0.
- Kernel temptation: expanding tools before evidence contracts hold can create visible traces without improving benchmark usability.

## PLAN_DRAFT Direction

The next plan-lane artifact should draft contracts in this order:

1. Public benchmark taxonomy and default v3/v1 fallback route verification.
2. Archive attachment scope and passage-role invariants, with LoCoMo retrieval-miss anchors.
3. Answer citation and unsupported-answer schema, with LongMemEval evidence-hit-answer-fail anchors and `conv-26_qa_001`.
4. Rendered evidence survival diagnostics as the bridge from context selection to answer artifacts.
5. P1 reservations for core-memory write policy and opt-in kernel tool results, explicitly excluded from P0 benchmark-usability claims.

Acceptance for the next artifact: every P0 contract must name its future failing test shape or benchmark case anchor, and every benchmark impact must remain split between LongMemEval and LoCoMo.
