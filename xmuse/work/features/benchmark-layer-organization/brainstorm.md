# Brainstorm: benchmark-layer-organization

feature_id: benchmark-layer-organization

## Options Considered

1. Full Phase 1-3 implementation in one turn.
   - Pros: broader blueprint coverage.
   - Cons: high blast radius across retrieval, composer, public eval reporting, and LLM eval gates; unsuitable for bounded Slave turn.

2. Public diagnostics movement-only changes.
   - Pros: lower runtime cost and isolated reporting changes.
   - Cons: current code already separates most stage statuses and movement states; less useful than improving evidence packet traceability.

3. Phase 0/1 diagnostic precision slice for same-session packet neighbor offsets.
   - Pros: directly supports the blueprint requirement that same-session neighbor policy be explicit, testable, and visible in diagnostics; low leakage risk; focused tests can prove behavior.
   - Cons: does not claim benchmark score movement and does not complete all Phase 4 public eval gates.

## Selected Approach

Use option 3. Add RED tests first for signed packet member offsets and v3 trace propagation, then implement the minimal metadata addition in recall packet construction. This improves layer organization diagnostics without changing defaults or optimizing to benchmark scores.
