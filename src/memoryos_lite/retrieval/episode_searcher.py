from dataclasses import dataclass

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryKind
from memoryos_lite.schemas import Episode, Role


@dataclass(frozen=True)
class EpisodeHit:
    episode: Episode
    score: float
    reason: str
    source: str = "episode_bm25"


class EpisodeSearcher:
    def search(
        self,
        episodes: list[Episode],
        query: str,
        top_k: int = 5,
        analysis: QueryAnalysis | None = None,
    ) -> list[EpisodeHit]:
        query_tokens = tokenize(query)
        if not episodes or not query_tokens:
            return []
        corpus = [tokenize(episode.index_text) for episode in episodes]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        hits: list[EpisodeHit] = []
        for episode, score in zip(episodes, scores, strict=False):
            token_overlap = len(
                set(query_tokens) & set(tokenize(episode.index_text))
            )
            if token_overlap <= 0:
                continue
            adjusted = float(score) + token_overlap
            if (
                analysis is not None
                and analysis.kind == QueryKind.ASSISTANT_SOURCE
                and episode.role == Role.ASSISTANT
            ):
                adjusted += 6.0
            if adjusted <= 0:
                continue
            hits.append(
                EpisodeHit(
                    episode=episode,
                    score=adjusted,
                    reason=f"episode_bm25={adjusted:.4f} overlap={token_overlap}",
                )
            )
        return sorted(
            hits, key=lambda hit: (hit.score, -hit.episode.position), reverse=True
        )[:top_k]
