from dataclasses import dataclass, field, replace

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryKind
from memoryos_lite.schemas import Episode, Role
from memoryos_lite.v3_contracts import (
    DiagnosticEvent,
    RecallMemoryEntry,
    SourceRef,
    SourceType,
)

_ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
}


def _content_tokens(tokens: list[str]) -> set[str]:
    return {token for token in tokens if token not in _ENGLISH_STOPWORDS}


def _entry_source_refs(entry: Episode | RecallMemoryEntry) -> list[SourceRef]:
    if isinstance(entry, RecallMemoryEntry) and entry.source_refs:
        return entry.source_refs
    return [
        SourceRef(
            source_type=SourceType.MESSAGE,
            source_id=source_id,
            session_id=entry.session_id,
        )
        for source_id in entry.source_message_ids
    ]


def _to_recall_entry(entry: Episode | RecallMemoryEntry) -> RecallMemoryEntry:
    if isinstance(entry, RecallMemoryEntry):
        return entry
    temporal_scope = {
        key: value
        for key, value in {
            "benchmark_session_id": entry.benchmark_session_id,
            "benchmark_date": entry.benchmark_date,
        }.items()
        if value is not None
    }
    return RecallMemoryEntry(
        id=entry.id,
        session_id=entry.session_id,
        message_id=entry.message_id,
        role=entry.role,
        text=entry.text,
        index_text=entry.index_text,
        position=entry.position,
        source_message_ids=entry.source_message_ids,
        source_refs=_entry_source_refs(entry),
        temporal_scope=temporal_scope,
        created_at=entry.created_at,
    )


def _diagnostic(
    entry: Episode | RecallMemoryEntry,
    reason_code: str,
    score: float | None,
    included: bool,
    metadata: dict[str, object] | None = None,
) -> DiagnosticEvent:
    return DiagnosticEvent(
        layer="recall",
        event_type="candidate",
        item_id=entry.message_id,
        reason_code=reason_code,
        score=score,
        included=included,
        source_refs=_entry_source_refs(entry),
        metadata=metadata or {},
    )


@dataclass(frozen=True)
class EpisodeHit:
    episode: Episode | RecallMemoryEntry
    score: float
    reason: str
    source: str = "recall_memory"
    diagnostics: tuple[DiagnosticEvent, ...] = ()
    rank_features: dict[str, float] = field(default_factory=dict)
    neighbor_of: str | None = None


class RecallMemorySearcher:
    def search(
        self,
        episodes: list[Episode | RecallMemoryEntry],
        query: str,
        top_k: int = 5,
        analysis: QueryAnalysis | None = None,
        neighbor_window: int = 1,
        neighbors_before: int | None = None,
        neighbors_after: int | None = None,
        preserve_neighbors: bool = False,
    ) -> list[EpisodeHit]:
        query_tokens = tokenize(query)
        query_content_tokens = _content_tokens(query_tokens)
        if not episodes or not query_content_tokens:
            return []
        before_window = neighbor_window if neighbors_before is None else max(0, neighbors_before)
        after_window = neighbor_window if neighbors_after is None else max(0, neighbors_after)

        entries = [_to_recall_entry(episode) for episode in episodes]
        corpus = [tokenize(entry.index_text) for entry in entries]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        by_session_and_position = {
            (entry.session_id, entry.position): entry for entry in entries
        }
        direct_hits: list[EpisodeHit] = []
        for entry, entry_tokens, score in zip(entries, corpus, scores, strict=False):
            token_overlap = len(query_content_tokens & _content_tokens(entry_tokens))
            if token_overlap <= 0:
                continue
            role_boost = 0.0
            if (
                analysis is not None
                and analysis.kind == QueryKind.ASSISTANT_SOURCE
                and entry.role == Role.ASSISTANT
            ):
                role_boost = 6.0
            temporal_boost = 0.0
            if (
                analysis is not None
                and analysis.kind == QueryKind.TEMPORAL
                and entry.temporal_scope
            ):
                temporal_boost = 1.5
            session_boost = 0.0
            if (
                analysis is not None
                and analysis.kind == QueryKind.MULTI_SESSION
                and entry.temporal_scope
            ):
                session_boost = 1.0
            adjusted = float(score) + token_overlap + role_boost + temporal_boost + session_boost
            if adjusted <= 0:
                continue
            features = {
                "token_overlap": float(token_overlap),
                "bm25_score": float(score),
                "role_boost": role_boost,
                "temporal_boost": temporal_boost,
                "session_boost": session_boost,
                "adjusted_score": adjusted,
            }
            diagnostics = [
                _diagnostic(entry, "direct_hit", adjusted, True, features),
                _diagnostic(entry, "rank", adjusted, True, {"rank_features": features}),
            ]
            if role_boost > 0:
                diagnostics.append(
                    _diagnostic(entry, "role_match", adjusted, True, {"role": entry.role.value})
                )
            if temporal_boost > 0:
                diagnostics.append(
                    _diagnostic(
                        entry,
                        "temporal_match",
                        adjusted,
                        True,
                        dict(entry.temporal_scope),
                    )
                )
            if session_boost > 0:
                diagnostics.append(
                    _diagnostic(
                        entry,
                        "session_match",
                        adjusted,
                        True,
                        dict(entry.temporal_scope),
                    )
                )
            direct_hits.append(
                EpisodeHit(
                    episode=entry,
                    score=adjusted,
                    reason=f"recall_memory={adjusted:.4f} overlap={token_overlap}",
                    diagnostics=tuple(diagnostics),
                    rank_features=features,
                )
            )

        direct_hits.sort(key=lambda hit: (hit.score, -hit.episode.position), reverse=True)
        selected: list[EpisodeHit] = []
        seen_message_ids: set[str] = set()
        hit_by_message_id: dict[str, int] = {}

        for hit in direct_hits:
            if len(selected) >= top_k:
                break
            if hit.episode.message_id in seen_message_ids:
                selected = self._append_dedupe(selected, hit.episode.message_id, hit)
                continue
            selected.append(hit)
            hit_by_message_id[hit.episode.message_id] = len(selected) - 1
            seen_message_ids.add(hit.episode.message_id)

        direct_selected = list(selected)
        expandable_session_ids: set[object] = set()
        if preserve_neighbors:
            if len(direct_selected) < top_k:
                for hit in direct_selected:
                    benchmark_session_id = hit.episode.temporal_scope.get(
                        "benchmark_session_id"
                    )
                    if benchmark_session_id is not None:
                        expandable_session_ids.add(benchmark_session_id)
            else:
                direct_session_counts: dict[object, int] = {}
                for hit in direct_selected:
                    benchmark_session_id = hit.episode.temporal_scope.get(
                        "benchmark_session_id"
                    )
                    if benchmark_session_id is None:
                        continue
                    direct_session_counts[benchmark_session_id] = (
                        direct_session_counts.get(benchmark_session_id, 0) + 1
                    )
                expandable_session_ids = {
                    session_id
                    for session_id, count in direct_session_counts.items()
                    if count >= 2
                }
        neighbor_limit = (
            top_k
            if not preserve_neighbors
            else top_k + top_k * (before_window + after_window)
        )
        for hit in direct_selected:
            if len(selected) >= neighbor_limit:
                break
            if preserve_neighbors:
                benchmark_session_id = hit.episode.temporal_scope.get(
                    "benchmark_session_id"
                )
                if benchmark_session_id not in expandable_session_ids:
                    continue
            self._add_neighbors(
                selected,
                seen_message_ids,
                hit_by_message_id,
                by_session_and_position,
                hit,
                neighbor_limit,
                before_window,
                after_window,
            )

        return selected if preserve_neighbors else selected[:top_k]

    def _add_neighbors(
        self,
        selected: list[EpisodeHit],
        seen_message_ids: set[str],
        hit_by_message_id: dict[str, int],
        by_session_and_position: dict[tuple[str, int], RecallMemoryEntry],
        hit: EpisodeHit,
        limit: int,
        neighbors_before: int,
        neighbors_after: int,
    ) -> None:
        for offset in range(1, max(neighbors_before, neighbors_after) + 1):
            if len(selected) >= limit:
                return
            positions: list[int] = []
            if offset <= neighbors_before:
                positions.append(hit.episode.position - offset)
            if offset <= neighbors_after:
                positions.append(hit.episode.position + offset)
            for position in positions:
                neighbor = by_session_and_position.get((hit.episode.session_id, position))
                if neighbor is None:
                    continue
                hit_benchmark_session = hit.episode.temporal_scope.get(
                    "benchmark_session_id"
                )
                neighbor_benchmark_session = neighbor.temporal_scope.get(
                    "benchmark_session_id"
                )
                if (
                    hit_benchmark_session is not None
                    and neighbor_benchmark_session is not None
                    and hit_benchmark_session != neighbor_benchmark_session
                ):
                    continue
                if neighbor.message_id in seen_message_ids:
                    self._append_existing_dedupe(selected, hit_by_message_id, neighbor, hit)
                    continue
                neighbor_metadata = {
                    "neighbor_of": hit.episode.message_id,
                    "neighbor_offset": offset,
                    **neighbor.temporal_scope,
                }
                diagnostics = (
                    _diagnostic(
                        neighbor,
                        "neighbor",
                        hit.score,
                        True,
                        neighbor_metadata,
                    ),
                    _diagnostic(
                        neighbor,
                        "rank",
                        hit.score,
                        True,
                        {
                            "neighbor_of": hit.episode.message_id,
                            "neighbor_offset": float(offset),
                            "neighbor_rank": hit.score,
                            "rank_features": {
                                "neighbor_of_rank": hit.score,
                                "neighbor_offset": float(offset),
                            },
                            **neighbor.temporal_scope,
                        },
                    ),
                )
                selected.append(
                    EpisodeHit(
                        episode=neighbor,
                        score=max(hit.score - 0.1 * offset, 0.0),
                        reason=f"neighbor_of={hit.episode.message_id}",
                        diagnostics=diagnostics,
                        rank_features={
                            "neighbor_of_rank": hit.score,
                            "neighbor_offset": float(offset),
                        },
                        neighbor_of=hit.episode.message_id,
                    )
                )
                hit_by_message_id[neighbor.message_id] = len(selected) - 1
                seen_message_ids.add(neighbor.message_id)
                if len(selected) >= limit:
                    return

    def _append_existing_dedupe(
        self,
        selected: list[EpisodeHit],
        hit_by_message_id: dict[str, int],
        duplicate: RecallMemoryEntry,
        hit: EpisodeHit,
    ) -> None:
        index = hit_by_message_id.get(duplicate.message_id)
        if index is None:
            return
        selected[index] = replace(
            selected[index],
            diagnostics=selected[index].diagnostics
            + (
                _diagnostic(
                    duplicate,
                    "dedupe",
                    hit.score,
                    False,
                    {"duplicate_of": hit.episode.message_id},
                ),
            ),
        )

    def _append_dedupe(
        self,
        selected: list[EpisodeHit],
        message_id: str,
        hit: EpisodeHit,
    ) -> list[EpisodeHit]:
        for index, existing in enumerate(selected):
            if existing.episode.message_id != message_id:
                continue
            selected[index] = replace(
                existing,
                diagnostics=existing.diagnostics
                + (
                    _diagnostic(
                        existing.episode,
                        "dedupe",
                        hit.score,
                        False,
                        {"duplicate_of": hit.episode.message_id},
                    ),
                ),
            )
            break
        return selected


class EpisodeSearcher:
    def __init__(self) -> None:
        self._searcher = RecallMemorySearcher()

    def search(
        self,
        episodes: list[Episode],
        query: str,
        top_k: int = 5,
        analysis: QueryAnalysis | None = None,
    ) -> list[EpisodeHit]:
        hits = self._searcher.search(episodes, query, top_k=top_k, analysis=analysis)
        return [
            replace(
                hit,
                source="episode_bm25",
                reason=hit.reason.replace("recall_memory", "episode_bm25"),
            )
            for hit in hits
        ]
