# phase: phase-14

## Research Focus

The agent loop needs to be audited end to end, but the kernel must remain opt-in. The question is not whether the loop can call tools; it is whether the loop can make memory actions legible, approved, and verifiable.

## What the current loop already has

- a step runner;
- tool policy;
- approval pending / granted tracing;
- `archive_write`;
- trace events.

## What still looks weak

- unsupported tool handling may be too narrow for a broader memory-action loop;
- verification after tool execution is not yet the main contract;
- replay integrity needs to stay explicit if approvals can be repeated;
- the loop should not become a hidden benchmark-tuning path.

## Recommended framing

Treat phase 14 as a loop contract audit, not a feature dump.

Minimum contract:

```text
observe -> choose action -> request tool -> policy -> approve -> execute -> verify -> trace
```

## Dependencies on phase 13

Phase 14 should not try to solve core-memory promotion first.
If phase 13 does not establish a source-backed lifecycle, phase 14 will inherit a weak mutation surface.

## Immediate follow-up questions for implementation

- Which memory actions must remain unsupported?
- Which actions need approval replay protection?
- Which retrieval checks should prove the action actually took effect?
- Which trace fields are required to audit the loop without claiming benchmark improvement?

