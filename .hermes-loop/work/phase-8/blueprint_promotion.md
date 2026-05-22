# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Promotion decision:

Promote `work/phase-8/next_blueprint_candidate.md` into the root Hermes control
surface after review and hardening.

Promoted files:

- `.hermes-loop/blueprint.md`
- `.hermes-loop/config.json`
- `.hermes-loop/state.json`

Accepted evidence:

- Phase 8 ACK: `work/phase-8/ack.json`
- Decision: `adjust_blueprint` / `continue_targeted`
- LongMemEval 50 full-chain LLM judge: `47/50`
- LoCoMo 50 full-chain LLM judge: `30/50`
- Kernel default unchanged
- v1 fallback preserved

Invalid evidence to ignore:

- `phase8_lme50_hb_20260522T160637Z`
- `phase8_locomo50_hb_20260522T160637Z`

Reason:

The root controller was still parked at phase 8 while the reviewed candidate
defined the required phase 9-15 reliability loop. Promotion removes the
candidate/root/config/state drift and starts the next loop at phase 9.

Next active phase:

`phase-9` / `Evidence Closure And Failure Replay`

Required first action:

God must write `work/phase-9/context_bundle.md`, then dispatch Phase 9 as a
diagnostic-first replay phase. Phase 9 must classify all 20 LoCoMo phase8
failures with per-case replay artifacts before Phase 10 changes retrieval.
