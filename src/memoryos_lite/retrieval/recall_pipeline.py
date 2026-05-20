from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import EpisodeSearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer
from memoryos_lite.schemas import ContextEvidence, ContextPackage
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator


class RecallPipeline:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings,
        tokenizer: TokenEstimator | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.tokenizer = tokenizer or TokenEstimator()
        self.query_analyzer = QueryAnalyzer()
        self.episode_searcher = EpisodeSearcher()

    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int,
        retrieval_query: str | None = None,
    ) -> ContextPackage:
        query = retrieval_query or task
        created = self.store.ensure_episodes_for_session(session_id)
        episodes = self.store.list_episodes(session_id)
        analysis = self.query_analyzer.analyze(query)
        hits = self.episode_searcher.search(episodes, query, top_k=10, analysis=analysis)
        package = ContextPackage(
            session_id=session_id,
            task=task,
            task_tokens=self.tokenizer.count(task),
        )
        used = package.task_tokens
        candidate_ids = [hit.episode.message_id for hit in hits]
        indexed_source_ids = sorted(
            {
                source_id
                for episode in episodes
                for source_id in episode.source_message_ids
            }
        )
        planned_ids: list[str] = []
        dropped = 0
        for hit in hits:
            text = " ".join(hit.episode.text.split())
            tokens = self.tokenizer.count(text)
            if used + tokens > budget:
                dropped += 1
                continue
            package.retrieved_evidence.append(
                ContextEvidence(
                    message_id=hit.episode.message_id,
                    text=text,
                    role=hit.episode.role,
                    reason=hit.reason,
                    estimated_tokens=tokens,
                    metadata={
                        "origin": "episode",
                        "score": hit.score,
                        "benchmark_session_id": hit.episode.benchmark_session_id,
                        "benchmark_date": hit.episode.benchmark_date,
                    },
                )
            )
            planned_ids.append(hit.episode.message_id)
            used += tokens
        package.estimated_tokens = used
        package.candidate_budget_dropped = dropped
        package.metadata.update(
            {
                "episode_backfilled": created,
                "item_candidate_source_ids": [],
                "indexed_source_ids": indexed_source_ids,
                "episode_candidate_message_ids": candidate_ids,
                "planned_evidence_message_ids": planned_ids,
                "planned_evidence_origins": ["episode" for _ in planned_ids],
                "budget_dropped_relevant": dropped,
            }
        )
        return package
