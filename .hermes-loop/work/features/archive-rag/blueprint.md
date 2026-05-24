# feature: archive-rag

## Purpose

Design and implement a MemoryOS-owned archive RAG boundary that can reuse
external parser, splitter, embedder, vector-index, and reranker components
without letting an external RAG framework own MemoryOS memory semantics.

## Initial Scope

- Keep SQLite as authoritative store.
- Preserve `ArchivalDocument`, `ArchivalChunk`, `ArchivalPassage`,
  `ArchivalMemory`, `SourceRef`, `ArchiveAttachment`, and scope eligibility.
- Introduce adapter-style retrieval/indexing boundaries only after design
  review.
- Do not bypass v3 composer diagnostics.
- Do not claim benchmark improvement from this feature until clean held-out or
  milestone evidence exists.

## Status

Planned slave feature. No implementation has started in the main worktree.
