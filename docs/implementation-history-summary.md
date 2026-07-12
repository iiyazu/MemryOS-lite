# Implementation history summary

MemoryOS Lite began as an OS-style memory experiment for long-running Agents:
retain raw source messages, keep context below the model limit, derive compact
memory layers, and make retrieval decisions auditable.

The live implementation has since converged on these durable decisions:

- SQLite is the authority; filesystem mirrors, caches, vectors, and reports are derived.
- v3 layered composition and v2 episode-first recall are the defaults.
- v1 composer and recall paths remain explicit compatibility choices.
- Core and archival memory require source-backed contracts.
- Agent kernel, LangGraph, external LLMs, Redis, and Qdrant remain optional experiments.
- Retrieval/source diagnostics and answer-quality diagnostics are reported separately.

Earlier benchmarks, xmuse integration designs, control-plane experiments, and
implementation plans are historical evidence, not present product contracts.
Their detailed documents were removed from the live tree; Git history preserves
them when provenance is needed.

For current behavior, inspect `README.md`, `docs/source-guide.md`,
`docs/store-interface.md`, the service contract, implementation, and fresh test
or evaluation output.
