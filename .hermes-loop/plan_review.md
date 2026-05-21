# PLAN_SELF_REVIEW

## Verdict: FAIL on first pass, then repaired to PASS

### Issues found

1. The draft plan changed `EpisodeHit.source` to `recall_memory` without preserving the legacy `EpisodeSearcher` compatibility surface. That would break the existing `tests/test_episode_retrieval.py` expectation that `EpisodeSearcher().search(...).source == "episode_bm25"`.
2. The draft plan asked execute-time workers to create git commits. That conflicts with the current state machine, where commit/archival happens in `GOD_ADVANCE` after ACK, not during `EXECUTE`.
3. The eval mapping draft used truthiness fallback for `recall_budget_dropped`. That would mis-handle a valid `0` recall value and fall back to the legacy field incorrectly.
4. The draft did not explicitly cover budget-drop diagnostics for the branch where task tokens already exceed budget.

### Repair applied

- Keep `RecallMemorySearcher` as the new recall-native surface.
- Preserve `EpisodeSearcher` as a legacy wrapper with the old `episode_bm25` source label.
- Remove all commit steps from the execution plan.
- Use key-presence-aware metadata preference helpers for recall-vs-legacy fields.
- Emit recall budget-drop diagnostics in both evidence overflow and task-truncation paths.

### Result

The revised plan is compatible with the current repo tests, the state machine, and the phase-2 acceptance criteria.
