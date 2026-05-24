# phase: phase-16

# Phase 16 Reflection

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Usable Completion

Yes. Phase 16 completed the active goal slice at usable level for K3, not for benchmark-quality improvement. The accepted slice was structural: opened Level 1 kernel maintenance tools through registry, policy, approval replay, named services, verification, traces, and focused tests while preserving default-off kernel behavior.

Evidence supporting usable completion:

- Review verdict: `PASS`; ACK level: `usable`; decision: `advance`.
- Opened executable tools: `archive_write`, `archive_attach`, `core_promotion_request`.
- Closed by design: `recall_search`, `archive_search`, `core_memory_append`, `core_memory_replace`, destructive tools, and unknown tools.
- Verification: focused kernel/store/context/public tests passed, full suite passed with `520 passed, 1 warning`, and `ruff` passed.
- Public smoke remained structural only: LoCoMo limit-5 no-LLM projected reports stayed `5 fail / 0 pass`; default-off traces were empty, opt-in traces were present.
- Current diff stat is consistent with the structural slice: kernel, selection, store/lifecycle, engine, migration-facing tests, and focused kernel tests changed; no blueprint change is required by the diff shape.

## Blueprint Adjustment: no

Rationale: Phase 17 already says the next step is K4 LoCoMo maintenance repair measurement, using a fixed LoCoMo slice, diagnostic planner proposals from model-visible fields only, approved maintenance writes in an isolated repair-smoke store, same-slice rerun, then clean held-out validation before any quality claim. That matches the evidence gap left by Phase 16. Phase 18 already contains the governance and promotion rules needed to avoid promoting from same-slice repair smoke.

No blueprint adjustment is needed before Phase 17, but Phase 17 should interpret the blueprint strictly: same-slice movement can only satisfy repair-smoke evidence, not promotion evidence.

## Carry Forward

Phase 17 should carry these findings forward:

- The kernel tool surface is no longer proposal-only for Level 1 mutating tools.
- `archive_attach` and `core_promotion_request` are covered by focused tests, but the Phase 16 public opt-in structural smoke exercised only `archive_write`.
- Durable pending promotion candidates now exist, but pending candidates must not be counted as visible core memory unless later approved through the proper core-memory path.
- `archive_attach` visibility must continue to be proven through session/scope eligibility and v3 composer behavior, not through direct passage or context mutation.
- Malformed approved replay for registered tools was a real repaired risk; Phase 17 should preserve the fail-closed containment evidence.
- Level 2 read-only search tools remain closed. Phase 17 must not assume `recall_search` or `archive_search` are executable unless it explicitly opens and verifies them under a new reviewed slice.
- Kernel default remains off; all repair-smoke kernel behavior must be opt-in with `MEMORYOS_AGENT_KERNEL=v1`.

## Evidence Phase 17 Must Produce

Phase 17 should produce:

- Baseline fixed LoCoMo 10-case full-chain LLM answer/judge evidence before maintenance writes.
- Same fixed LoCoMo 10-case rerun after approved kernel-created maintenance writes in an isolated repair-smoke store.
- Case-level `pass_to_fail`, `fail_to_pass`, `retrieval_miss`, `evidence_hit_answer_fail`, and source-miss judge-pass lists.
- Separate source metrics: `source_hit`, `planned_evidence_source_hit_at_5`, and `episode_source_hit_at_10`.
- Trace evidence that maintenance artifacts were created only from model-visible fields and approved tool calls, with no benchmark gold fields used as executable inputs.
- v3 context evidence that any improvement comes through eligible archive attachments or approved lifecycle artifacts, not direct context injection.
- Clean held-out or clean-store LoCoMo validation before any benchmark-quality claim.
- LongMemEval 30-case regression guard if Phase 17 changes default v3 context selection, retrieval, answer projection, or non-kernel public behavior.

## Stale Or Invalid Evidence To Avoid

- Do not use Phase 16 LoCoMo limit-5 no-LLM reports as quality evidence; they are structural default-off/opt-in smoke only.
- Do not use Phase 15 proposal-only planner artifacts as proof that maintenance writes improve retrieval or answer quality.
- Do not use same-slice repair movement as promotion evidence.
- Do not use aggregate scores without case-level regression lists.
- Do not cite invalid Phase 8 retry run ids `phase8_lme50_hb_20260522T160637Z` or `phase8_locomo50_hb_20260522T160637Z`.
- Do not rely on the task-4 timeout or `.hermes-loop/active_job.json` process state as evidence.
- Do not claim Level 2 search tools or Level 3 core edit tools are opened in Phase 16.
