# phase: phase-4

# Review: Phase 4 - Archival Memory Store

PASS.

## Notes
- The archival model now has distinct document / chunk / passage / memory / history / attachment contracts.
- The store persists those tables and keeps legacy page/item paths as adapters only.
- Passage search stays passage-level and does not feed default recall paths.
- No regression was found in the legacy pytest suite.

