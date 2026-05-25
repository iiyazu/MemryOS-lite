# feature: xmuse-error-knowledge

/goal

Implement the accepted feature plan for the worktree
`/home/iiyatu/projects/python/memoryOS-xmuse-error-knowledge`.

Allowed code and test paths:

- `xmuse/contracts/knowledge_maintainer_template.json`
- `xmuse/xmuse_error_knowledge.py`
- `xmuse/knowledge/**`
- `tests/test_xmuse_error_knowledge.py`
- `xmuse/work/features/xmuse-error-knowledge/*`

Required artifacts: `result.md`, focused verification evidence,
`execute_review.md`, `review_verdict.json`, `ack.json`, and updated
`slave_state.json`.

The implementation must be a real Xmuse-local knowledge maintainer path:
validate the dedicated contract, enforce bootstrap no-op boundaries, scan real
Xmuse control-plane artifacts, write versioned source-attributed knowledge
objects and indexes, preserve human-edited draft documents, and produce a
feature-local handoff. Demo-only, stub-only, and fixture-only completion is
forbidden.

Non-goals: do not write MemoryOS memory, change MemoryOS retrieval/runtime
behavior, edit Master state/status, edit Master review or approval artifacts,
modify active prompts, install or activate skills, merge, remove v1 fallback,
change the v3 default, or enable the agent kernel by default.

Benchmark scores are diagnostic evidence only, not goal constraints.

Max repair cycles: 3
