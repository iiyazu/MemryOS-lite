# MemoryOS v3 — Migration Glossary

## Schema Map

| v1/v2 | v3 | Notes |
|-------|-----|-------|
| `Message` | `Message` | Unchanged. Raw message storage. |
| `Episode` | `RecallMemoryEntry` | Temporary v2 retrieval unit promoted to formal recall layer. |
| `EpisodeSearcher` | `RecallMemorySearcher` | Renamed. |
| `RecallPipeline` | `RecallMemoryPipeline` | Absorbed into ContextComposer for v3 path. |
| `MemoryPage` | `ArchivalDocument` | Adapter input only. Page summary role → document. |
| `MemoryItem` | `ArchivalPassage` / `ArchivalMemory` | Semantic item split: passage (retrieval unit) vs memory (lifecycle item). |
| `ContextBuilder` | `ContextComposer` | Thin v1 builder replaced by layered composer. |
| `agent_graph` | `AgenticKernel` | LangGraph demo → formal control plane. |
| `memory_patches` | `ArchivalMemoryHistory` | Patch table → typed memory history. |

## Concept Map

| v1/v2 Concept | v3 Concept |
|---------------|-----------|
| page/item/recent-message path | Layered composer (core → recall → archival → recent) |
| v2 episode-first recall (opt-in) | Recall memory layer (always available) |
| page JSON debug mirror | Archival passages with citation |
| item candidate source IDs | Recall/archival source attribution |
| budget_dropped_relevant | Composer drop diagnostics per layer |

## File Map

| v1/v2 File | v3 Target |
|-----------|----------|
| `schemas.py` | Extended with v3 dataclasses |
| `store.py` | Extended with archival/core tables |
| `engine.py` | V3 routing alongside legacy paths |
| `retrieval/recall_pipeline.py` | `retrieval/recall_memory.py` |
| `retrieval/episode_searcher.py` | `retrieval/recall_searcher.py` |
| `retrieval/query_analyzer.py` | Kept, extended for recall queries |
| `public_benchmarks.py` | Extended with v3 diagnostics |
| `agent_graph.py` | `kernel/` directory |
