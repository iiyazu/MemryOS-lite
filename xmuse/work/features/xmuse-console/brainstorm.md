# xmuse-console Brainstorm

feature_id: xmuse-console

The Master blueprint is treated as the approved design source because the lane is running in autonomous mode.

## Considered Approaches

1. Full frontend toolchain plus backend adapter.
   - Pros: richer UI tests and future extensibility.
   - Cons: adds package management and build surface not present in the repo.

2. Backend adapter/API first, with a static console shell.
   - Pros: completes the riskiest read-only/local-only contract, keeps tests hermetic, avoids toolchain churn.
   - Cons: frontend verification is lighter than a full component test suite.

3. Reporter reuse only.
   - Pros: fastest.
   - Cons: exposes reporter internals instead of stable xmuse DTOs and does not satisfy the blueprint.

## Decision

Use approach 2. Implement the stable DTO read path and opt-in API with fixture-driven tests, then add a static local console shell that consumes `/xmuse/snapshot` and `/xmuse/lanes/{feature_id}` only.

## Non-goals

- No write operations.
- No production authentication or public network posture.
- No benchmark optimization or score claims.
- No changes to memory architecture, recall pipeline, kernel, store authority, or eval behavior.

