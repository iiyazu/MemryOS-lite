# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

Decision source: `work/phase-8/promotion_decision.md`.

Status: superseded by promoted root `.hermes-loop/blueprint.md` and
`.hermes-loop/config.json` on 2026-05-23. Keep this file only as the reviewed
candidate source for the promotion record.

## Blueprint Name

MemoryOS v3 Usable Agent Memory Blueprint.

## Core Thesis

The next loop should not only patch a single LoCoMo failure. It should turn the
existing v3 memory layers into a usable, source-attributed, lifecycle-governed,
agent-operable memory system.

Letta is a reference, not a template to copy. MemoryOS should keep Letta-style
core memory, archival memory, and agent memory tools, but add a stronger
benchmark-governed evidence layer:

- source-attributed evidence packets instead of opaque top-k snippets;
- failure replay before implementation;
- explicit lifecycle promotion from recall to archival to core;
- reversible provenance for every long-term memory mutation;
- eval gates that separate retrieval quality from judged answer quality.

## Current Evidence

Phase 8 accepted evidence:

- LongMemEval 50 full-chain LLM judge: `47/50`.
- LoCoMo 50 full-chain LLM judge: `30/50`.
- No same-subset pass-to-fail cases were recorded.
- Kernel default remained off.

LoCoMo is the controlling bottleneck:

- Retrieval/session localization misses:
  `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`, `conv-26_qa_035`, `conv-26_qa_036`,
  `conv-26_qa_039`, `conv-26_qa_044`, `conv-26_qa_050`.
- Evidence-hit-answer-fail cases:
  `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_016`,
  `conv-26_qa_024`, `conv-26_qa_027`, `conv-26_qa_033`,
  `conv-26_qa_041`, `conv-26_qa_048`.
- Judge/source-support questionable:
  `conv-26_qa_015`.

Therefore the next loop starts with recall/evidence reliability, then expands
to archival, core, and agent-loop lifecycle work.

## Global Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not remove explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Do not change benchmark scoring semantics.
- Do not use benchmark case-id hacks or expected-answer leaks.
- Do not claim production readiness.
- Do not accept aggregate-only improvements without same-case analysis.
- Do not rewrite the full architecture unless case evidence proves local fixes
  cannot solve the bottleneck.

## 30/50-Case Eval Gate Policy

30/50-case public benchmark runs are milestone gates, not routine regression
tests.

Mandatory rules:

- no projected/no-LLM report can satisfy a quality gate;
- every quality gate command must explicitly include `--llm-answer` and
  `--llm-judge`;
- every gate must record run id, command, report path, comparison report, and
  whether kernel was off or opt-in;
- retrieval/source movement must be reported separately from judged answer
  movement;
- pass-to-fail and fail-to-pass lists must be explicit, even when empty;
- LoCoMo failure-class movement must be reported separately from aggregate
  pass/fail movement;
- 50-case runs are reserved for promotion, strong-signal confirmation, or a
  God-approved escalation after a useful 30-case signal.

Default milestone pattern:

1. focused tests;
2. fixed failure-slice full-chain smoke;
3. LoCoMo 30 full-chain gate;
4. LongMemEval 30 full-chain regression guard;
5. optional 50-case confirmation only if the 30-case signal is useful and
   same-case explainable.

## God Adjustment And Repeat Protocol

God may change the local plan, repeat a phase, or write an adjustment artifact
when evidence shows the blueprint is no longer the right next step. This is a
required control mechanism, not an exceptional failure path.

Required adjustment triggers:

- review finds demo-only implementation, partial wiring, or behavior that does
  not exercise the real public benchmark path;
- `state.json`, root `blueprint.md`, root `config.json`, and phase artifacts
  disagree about the active phase or accepted evidence;
- a 30-case full-chain gate has no same-case explainable improvement and does
  not convert failures into a more precise downstream class;
- source grounding, retrieval/source metrics, or pass-to-fail movement regresses
  in a way that is not explained by the phase goal;
- a phase tries to advance from projected/no-LLM evidence for a quality claim;
- stale, killed, partial, or heartbeat artifacts are being treated as promotion
  evidence.

Allowed decisions:

- `repeat_phase`: keep the same phase and require a narrower implementation;
- `god_adjust`: amend the local blueprint or phase scope before continuing;
- `hold`: stop promotion or expansion because evidence is unsafe;
- `continue_targeted`: move to the next targeted phase only when the ACK gate is
  met and same-case evidence is explicit;
- `expand_eval`: run larger 30/50-case evidence only after the smaller gate has
  useful, explainable signal.

Every adjustment must write the reason, affected cases, stale artifacts to
ignore, and the next allowed gate into the phase-local `adjustment.md` or
`ack.json`.

## Phase 9 - Evidence Closure And Failure Replay

Target state: `failure-replay-ready`.

Purpose:
make every benchmark failure replayable from query to retrieval, context
selection, rendered evidence, answer, citation, and judge result.

Inputs:

- `.memoryos/evals/phase8_locomo50_20260522T151605Z_locomo.json`
- `.memoryos/evals/phase8_lme50_20260522T151605Z_longmemeval.json`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/diagnostic_report.py`

Allowed changes:

- diagnostic helpers;
- replay artifact writers;
- tests for failure class completeness;
- phase-local reports.

Not allowed:

- answer/retrieval behavior changes unless a failing diagnostic test proves the
  current report cannot classify real cases.

Required artifacts:

- `work/phase-9/failure_taxonomy.md`
- `work/phase-9/case_matrix.md`
- `work/phase-9/replay_schema.md`
- `work/phase-9/replay_cases/<case_id>.json` or one equivalent structured
  per-case replay artifact for each of the 20 LoCoMo phase8 failures;
- `work/phase-9/result.md`
- `work/phase-9/review_verdict.json`
- `work/phase-9/ack.json` or `work/phase-9/adjustment.md`

Required failure classes:

- retrieval miss;
- session localization miss;
- temporal/date miss;
- speaker/entity confusion;
- evidence retrieved but not selected;
- evidence selected but not rendered;
- evidence rendered but answer fails;
- unsupported citation;
- refusal despite evidence;
- judge questionable;
- diagnostic gap.

ACK gate:

- all 20 LoCoMo phase8 failures are classified;
- every one of the 20 LoCoMo phase8 failures has a replay row or artifact with
  case id, expected source ids, indexed source status, retrieved ids, selected
  ids, rendered ids, answer output, citation/source support, judge result, and
  final failure class;
- replay artifacts distinguish path-level patterns from case-level evidence;
- source metrics remain separate from judged answer metrics;
- `diagnostic_gap` cases are explicit and not hidden.

## Phase 10 - Recall Memory Reliability

Target state: `recall-evidence-reliable`.

Purpose:
make recall memory robust enough for LoCoMo dialogue, temporal, speaker, and
multi-hop questions without regressing LongMemEval.

Current implementation anchor:

- `RecallPipeline`
- `RecallMemorySearcher`
- episode backfill;
- BM25 direct hits;
- neighbor expansion;
- benchmark session guard.

Design direction:

Recall should return an evidence packet, not just a flat top-k list:

```text
anchor_turn
+ neighbor_turns
+ benchmark_session_id
+ benchmark_date
+ speaker/entity hints
+ rank features
+ selected because...
```

Potential targeted fixes:

- LoCoMo-aware same-session expansion when the expected source is near a weak
  lexical hit;
- speaker-aware expansion for questions naming Caroline/Melanie or equivalent
  participants;
- temporal/date-aware boost that distinguishes session date from message text;
- multi-anchor retrieval for questions requiring two dialogue turns;
- evidence packet diagnostics that show which anchor caused each neighbor.

Required tests:

- failing test for one real repeated LoCoMo failure class;
- fixed-slice test or diagnostic assertion covering the selected repeated
  LoCoMo failure cases that the phase claims to improve;
- regression test that unrelated session neighbors are not pulled in;
- LongMemEval guard where high LME retrieval remains stable.

Eval gate:

- focused pytest;
- LoCoMo fixed failure slice full-chain LLM judge;
- LoCoMo 30-case full-chain LLM judge as the recall milestone gate;
- LongMemEval 30-case full-chain LLM judge as the regression guard;
- same-case movement table for the fixed failure slice and the 30-case gate,
  with pass-to-fail, fail-to-pass, unchanged-fail, retrieval/source movement,
  and failure-class movement split out;
- optional LoCoMo 50-case confirmation only after LoCoMo 30 improves on
  same-case evidence or converts a repeated retrieval miss into a more precise
  downstream failure class.

ACK gate:

- at least one repeated LoCoMo retrieval/session failure class improves or is
  converted into a more precise downstream failure class;
- the LoCoMo 30-case gate has same-case explainable signal; if it has no
  explainable gain, God must choose `repeat_phase` or `god_adjust` instead of
  advancing;
- any pass-to-fail case is listed with a cause and either fixed, accepted with a
  documented tradeoff, or used to trigger `hold`;
- no material LongMemEval collapse;
- all new behavior is explained in `case_matrix.md`.

## Phase 11 - Evidence Handoff And Context Selection

Target state: `evidence-handoff-reliable`.

Purpose:
ensure retrieved evidence is not silently lost between recall, v3 composer,
legacy context package projection, answer evidence rendering, and public report
diagnostics.

Current implementation anchor:

- `V3ContextComposer`
- `ContextPackageV3`
- `_context_package_from_v3`
- `v3_final_context_trace`
- `case_diagnostics.selected_context_ids`
- `case_diagnostics.rendered_evidence_ids`

Design direction:

Every expected source should have a traceable status:

```text
indexed -> retrieved -> selected -> rendered -> cited -> judged
```

Required tests:

- retrieved expected source but dropped by budget;
- selected source missing from final context trace;
- rendered source not available to answerer;
- archival/recall source id projection mismatch.

Eval gate:

- focused pytest for context projection and diagnostics;
- LoCoMo 30-case full-chain LLM judge;
- LongMemEval 30-case full-chain LLM judge as regression guard;
- report failure-class movement for `retrieval_miss`,
  `context_missing_evidence`, and `evidence_hit_answer_fail` separately;
- optional LoCoMo 50 only if the 30-case run proves handoff improvement rather
  than only aggregate judge noise.

ACK gate:

- no selected expected evidence disappears without a diagnostic reason;
- `context_missing_evidence` is split into selected-drop vs render-drop;
- public reports expose enough fields for same-case diagnosis.

## Phase 12 - Archival/RAG Memory Unification

Target state: `archival-rag-usable`.

Purpose:
unify archival memory writes and archival passage retrieval into a complete
long-term RAG loop.

Current split:

- `archive_write` writes `ArchivalMemory`;
- v3 composer retrieves `ArchivalPassage`;
- documents/chunks/passages exist and are scope-gated;
- vector/hybrid modes currently fall back to lexical when vector is unavailable.

Design direction:

Archival memory should become retrievable evidence after write:

```text
agent/tool/user source
-> archival memory
-> passage/index representation
-> scoped retrieval
-> context item
-> cited answer
-> history/provenance
```

Required tests:

- `archive_write` creates memory with source refs;
- generated/bridged passage is eligible by session/archive scope;
- subsequent `build_context` can retrieve the written archival fact;
- delete/update history prevents stale archival evidence from being selected.

Eval gate:

- focused archival tests;
- no-LLM structural smoke for archive write -> retrieval;
- optional LLM judge only after structural path is green;
- run LoCoMo 30 and LongMemEval 30 only if archival changes affect the default
  v3 public benchmark context path.

ACK gate:

- archival write and archival retrieval are connected in one audited path;
- every archival context item has source refs;
- no sourceless archival mutation is accepted.

## Phase 13 - Core Memory Lifecycle

Target state: `core-memory-lifecycle-usable`.

Purpose:
turn core memory from manually managed blocks into source-backed, conflict-aware
stable memory.

Current capability:

- core blocks can be stored, rendered, updated, deleted, and history-tracked;
- v3 composer reads core blocks into the core layer;
- writes require source refs or approval.

Design direction:

Core memory should be promoted, not casually written:

```text
recall/archival evidence
-> promotion candidate
-> conflict check
-> approval/source-density gate
-> core update
-> history
-> rendered block
```

Required tests:

- repeated recall evidence can propose a core candidate;
- conflicting candidate does not overwrite silently;
- approved replacement records old value and source refs;
- read-only core blocks reject mutation;
- stale core facts can be deprecated without deletion from history.

Eval gate:

- focused core-memory lifecycle tests;
- no-LLM structural smoke proving core candidates render into v3 context only
  through approved/source-backed paths;
- run LoCoMo 30 and LongMemEval 30 only if core lifecycle changes alter default
  benchmark context composition.

ACK gate:

- core candidate lifecycle is source-backed and reviewable;
- rendered core memory stays within token budget;
- core updates do not bypass approval/provenance.

## Phase 14 - Agent Memory Loop

Target state: `agent-loop-memory-usable`.

Purpose:
make the opt-in kernel able to perform a complete, audited memory action loop.

Current capability:

- `SimpleAgentStepRunner`;
- tool policy;
- approval pending/granted;
- `archive_write`;
- trace events.

Design direction:

The agent loop should be allowed to operate on memory only under policy:

```text
observe context
-> decide memory action
-> request tool
-> policy decision
-> approval if required
-> execute
-> verify retrieval
-> trace result
```

Potential tools:

- `recall_search`;
- `archive_search`;
- `archive_write`;
- `core_memory_propose`;
- `core_memory_update`;
- `memory_deprecate`.

Required tests:

- opt-in kernel remains off by default;
- policy denies unsupported tools;
- approval replay cannot be tampered with;
- archive write can be verified by later retrieval;
- core proposal remains pending until approved.

Eval gate:

- focused kernel tests;
- default-kernel-off LoCoMo 30 and LongMemEval 30 if the agent-loop changes
  touch default context, retrieval, or public benchmark paths;
- opt-in kernel 5-case smoke for trace/control-plane verification;
- no 50-case kernel run unless default-kernel-off 30-case gates are stable and
  God explicitly records why larger kernel evidence is needed.

ACK gate:

- kernel default remains off;
- every mutation has policy, approval/source refs, and trace;
- at least one memory write can be retrieved in a later context build.

## Phase 15 - Benchmark Governance And Promotion

Target state: `governed-promotion-ready`.

Purpose:
prevent accidental promotion from noisy aggregate improvements.

Required gates:

- no-LLM structural smoke for wiring;
- full-chain LLM answer/judge for quality;
- LongMemEval 50 full-chain LLM judge;
- LoCoMo 50 full-chain LLM judge;
- same-case comparison;
- pass-to-fail list;
- fail-to-pass list;
- retrieval/source metrics separate from judged answer quality;
- invalid artifact quarantine;
- phase ACK only after review verdict passes.

Promotion decisions:

- `continue_targeted`: a layer-specific bottleneck remains.
- `expand_eval`: 30/50-case evidence is stable enough for larger samples.
- `hold`: aggregate improved but source grounding or regressions are unsafe.
- `promote_blueprint`: root blueprint/config should be updated after review.

ACK gate:

- LongMemEval and LoCoMo are both reported;
- LoCoMo is not hidden by LongMemEval;
- kernel default remains unchanged;
- v1 fallback remains explicit;
- next blueprint decision is backed by case-level evidence.

## Initial Next Step

Start with Phase 9, then Phase 10. Do not start with archival, core, or kernel
work until LoCoMo failure replay identifies whether recall/evidence reliability
is genuinely exhausted.

Recommended first fixed LoCoMo slice:

- retrieval/session misses:
  `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`,
  `conv-26_qa_011`, `conv-26_qa_019`, `conv-26_qa_020`,
  `conv-26_qa_025`, `conv-26_qa_050`.
- evidence-hit-answer-fail:
  `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_033`,
  `conv-26_qa_041`, `conv-26_qa_048`.

The first implementation should target the largest repeated failure class found
by replay, not the easiest code path.

## Adoption Rule

God may promote this candidate into root `.hermes-loop/blueprint.md` and
`.hermes-loop/config.json` only after:

1. phase-8 ACK is usable;
2. this candidate is reviewed;
3. config phase headings are synchronized with promoted headings;
4. stale sidecar drafts are removed or explicitly marked superseded;
5. the promoted blueprint preserves conservative benchmark language.
