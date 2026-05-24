from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, RecallMemorySearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer
from memoryos_lite.schemas import ContextEvidence, ContextPackage
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import DiagnosticEvent, episode_to_recall_entry


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
        self.recall_searcher = RecallMemorySearcher()

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
        recall_entries = [episode_to_recall_entry(episode) for episode in episodes]
        analysis = self.query_analyzer.analyze(query)
        preserve_session_neighbors = any(
            "benchmark_session_id" in entry.temporal_scope for entry in recall_entries
        )
        hits = self.recall_searcher.search(
            recall_entries,
            query,
            top_k=10,
            analysis=analysis,
            neighbors_before=self.settings.memoryos_evidence_context_neighbors_before,
            neighbors_after=self.settings.memoryos_evidence_context_neighbors_after,
            preserve_neighbors=preserve_session_neighbors,
        )
        package = ContextPackage(
            session_id=session_id,
            task=task,
            task_tokens=self.tokenizer.count(task),
        )
        used = package.task_tokens
        candidate_ids = [hit.episode.message_id for hit in hits]
        candidate_session_ids = self._session_ids_from_hits(hits)
        indexed_source_ids = sorted(
            {
                source_id
                for episode in recall_entries
                for source_id in episode.source_message_ids
            }
        )
        recall_diagnostics = self._serialize_diagnostics(hits)
        if package.task_tokens > budget:
            dropped = len(hits)
            package.task_truncated = True
            package.estimated_tokens = package.task_tokens
            package.candidate_budget_dropped = dropped
            recall_diagnostics.extend(
                self._budget_drop_diagnostics(hits, budget_tokens=package.task_tokens)
            )
            package.metadata.update(
                {
                    "episode_backfilled": created,
                    "item_candidate_source_ids": [],
                    "recall_candidate_message_ids": candidate_ids,
                    "recall_candidate_session_ids": candidate_session_ids,
                    "indexed_source_ids": indexed_source_ids,
                    "recall_indexed_source_ids": indexed_source_ids,
                    "episode_candidate_message_ids": candidate_ids,
                    "recall_planned_message_ids": [],
                    "planned_evidence_message_ids": [],
                    "recall_planned_session_ids": [],
                    "recall_evidence_packets": [],
                    "planned_evidence_origins": [],
                    "recall_budget_dropped": dropped,
                    "budget_dropped_relevant": dropped,
                    "recall_diagnostics": recall_diagnostics,
                }
            )
            return package

        planned_ids: list[str] = []
        planned_hits: list[EpisodeHit] = []
        dropped = 0
        planned_diagnostics: list[dict[str, object]] = list(recall_diagnostics)
        for hit in hits:
            text = " ".join(hit.episode.text.split())
            tokens = self.tokenizer.count(text)
            if used + tokens > budget:
                dropped += 1
                planned_diagnostics.extend(
                    self._budget_drop_diagnostics([hit], budget_tokens=tokens)
                )
                continue
            evidence_metadata = {
                "origin": "episode",
                "score": hit.score,
                "neighbor_of": hit.neighbor_of,
                "neighbor_offset": hit.rank_features.get("neighbor_offset"),
                "benchmark_session_id": hit.episode.temporal_scope.get(
                    "benchmark_session_id"
                ),
                "benchmark_date": hit.episode.temporal_scope.get("benchmark_date"),
                "rank_features": dict(hit.rank_features),
            }
            evidence_metadata.update(hit.packet_metadata)
            package.retrieved_evidence.append(
                ContextEvidence(
                    message_id=hit.episode.message_id,
                    text=text,
                    role=hit.episode.role,
                    reason=hit.reason,
                    estimated_tokens=tokens,
                    metadata=evidence_metadata,
                )
            )
            planned_ids.append(hit.episode.message_id)
            planned_hits.append(hit)
            used += tokens
        package.estimated_tokens = used
        package.candidate_budget_dropped = dropped
        package.metadata.update(
            {
                "episode_backfilled": created,
                "item_candidate_source_ids": [],
                "recall_candidate_message_ids": candidate_ids,
                "recall_candidate_session_ids": candidate_session_ids,
                "indexed_source_ids": indexed_source_ids,
                "recall_indexed_source_ids": indexed_source_ids,
                "episode_candidate_message_ids": candidate_ids,
                "recall_planned_message_ids": planned_ids,
                "planned_evidence_message_ids": planned_ids,
                "recall_planned_session_ids": self._session_ids_from_hits(planned_hits),
                "recall_evidence_packets": self._packet_summaries(planned_hits),
                "planned_evidence_origins": ["episode" for _ in planned_ids],
                "recall_budget_dropped": dropped,
                "budget_dropped_relevant": dropped,
                "recall_diagnostics": planned_diagnostics,
            }
        )
        return package

    def _serialize_diagnostics(
        self,
        hits: list,
    ) -> list[dict[str, object]]:
        return [event for hit in hits for event in self._dump_hit_diagnostics(hit)]

    def _dump_hit_diagnostics(self, hit) -> list[dict[str, object]]:
        return [diagnostic.model_dump(mode="json") for diagnostic in hit.diagnostics]

    def _budget_drop_diagnostics(
        self,
        hits: list,
        *,
        budget_tokens: int,
    ) -> list[dict[str, object]]:
        diagnostics: list[dict[str, object]] = []
        for hit in hits:
            metadata = {
                "reason": hit.reason,
                "source": hit.source,
                "neighbor_of": hit.neighbor_of,
                "neighbor_offset": hit.rank_features.get("neighbor_offset"),
                "benchmark_session_id": hit.episode.temporal_scope.get(
                    "benchmark_session_id"
                ),
                "benchmark_date": hit.episode.temporal_scope.get("benchmark_date"),
                "rank_features": dict(hit.rank_features),
            }
            metadata.update(hit.packet_metadata)
            diagnostics.append(
                DiagnosticEvent(
                    layer="recall",
                    event_type="budget",
                    item_id=hit.episode.message_id,
                    reason_code="budget_drop",
                    score=hit.score,
                    included=False,
                    dropped=True,
                    budget_tokens=budget_tokens,
                    source_refs=list(getattr(hit.episode, "source_refs", [])),
                    metadata=metadata,
                ).model_dump(mode="json")
            )
        return diagnostics

    @staticmethod
    def _session_ids_from_hits(hits: list[EpisodeHit]) -> list[str]:
        seen: set[str] = set()
        session_ids: list[str] = []
        for hit in hits:
            session_id = hit.episode.temporal_scope.get("benchmark_session_id")
            if session_id is None:
                continue
            value = str(session_id)
            if value in seen:
                continue
            seen.add(value)
            session_ids.append(value)
        return session_ids

    @staticmethod
    def _packet_summaries(hits: list[EpisodeHit]) -> list[dict[str, object]]:
        seen: set[str] = set()
        packets: list[dict[str, object]] = []
        for hit in hits:
            packet_id = hit.packet_metadata.get("evidence_packet_id")
            if not packet_id:
                continue
            packet_id_text = str(packet_id)
            if packet_id_text in seen:
                continue
            seen.add(packet_id_text)
            packets.append(
                {
                    "evidence_packet_id": packet_id_text,
                    "packet_anchor_message_id": hit.packet_metadata.get(
                        "packet_anchor_message_id"
                    ),
                    "packet_session_id": hit.packet_metadata.get("packet_session_id"),
                    "packet_member_message_ids": list(
                        hit.packet_metadata.get("packet_member_message_ids", [])
                    ),
                    "packet_member_neighbor_offsets": list(
                        hit.packet_metadata.get("packet_member_neighbor_offsets", [])
                    ),
                    "packet_member_source_ids": list(
                        hit.packet_metadata.get("packet_member_source_ids", [])
                    ),
                    "packet_reason": hit.packet_metadata.get("packet_reason"),
                    "packet_rank": hit.packet_metadata.get("packet_rank"),
                    "score": hit.score,
                    "rank_features": dict(hit.rank_features),
                }
            )
        return packets
