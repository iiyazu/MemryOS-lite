from hashlib import sha256
from typing import Any, cast

from pydantic import ValidationError

from memoryos_lite.cache import (
    MemoryCache,
    NoopMemoryCache,
    build_cache_key,
    create_memory_cache,
)
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, RecallMemorySearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryAnalyzer, QueryKind
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
        cache: MemoryCache | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.tokenizer = tokenizer or TokenEstimator()
        self.query_analyzer = QueryAnalyzer()
        self.recall_searcher = RecallMemorySearcher()
        self.cache = cache if cache is not None else self._default_cache(settings)

    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int,
        retrieval_query: str | None = None,
    ) -> ContextPackage:
        query = retrieval_query or task
        created = self.store.ensure_episodes_for_session(session_id)
        memory_watermark = self.store.session_memory_watermark(session_id)
        recall_cache_status = self._recall_cache_status("disabled")
        recall_cache_key: str | None = None
        if self.settings.memoryos_recall_cache_enabled:
            recall_cache_key = build_cache_key(
                scope="recall_candidates",
                settings=self.settings,
                session_id=session_id,
                query=query,
                memory_watermark=memory_watermark,
                parameters={
                    "budget": budget,
                    "task_sha256": self._hash_text(task),
                },
            )
            cached = self.cache.get_json(recall_cache_key)
            recall_cache_status = self._recall_cache_status(
                cached.status,
                reason=cached.reason,
            )
            if cached.status == "hit" and cached.value is not None:
                package = self._package_from_cache(cached.value)
                if package is not None:
                    package.metadata["episode_backfilled"] = created
                    package.metadata["recall_cache"] = recall_cache_status
                    package.metadata["query_analysis_cache"] = self._query_cache_status(
                        "skipped",
                        reason="recall_candidates_hit",
                    )
                    package.metadata["recall_memory_watermark"] = memory_watermark
                    return package
                recall_cache_status = self._recall_cache_status(
                    "corrupt",
                    reason="cached recall package failed validation",
                )
        episodes = self.store.list_episodes(session_id)
        recall_entries = [episode_to_recall_entry(episode) for episode in episodes]
        analysis, query_cache_status = self._analyze_query(query)
        preserve_session_neighbors = any(
            "benchmark_session_id" in entry.temporal_scope for entry in recall_entries
        )
        hits = self.recall_searcher.search(
            cast(Any, recall_entries),
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
                    "recall_cache": recall_cache_status,
                    "query_analysis_cache": query_cache_status,
                    "recall_memory_watermark": memory_watermark,
                }
            )
            self._store_recall_package(recall_cache_key, package)
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
            temporal_scope = self._hit_temporal_scope(hit)
            evidence_metadata = {
                "origin": "episode",
                "score": hit.score,
                "neighbor_of": hit.neighbor_of,
                "neighbor_offset": hit.rank_features.get("neighbor_offset"),
                "benchmark_session_id": temporal_scope.get("benchmark_session_id"),
                "benchmark_date": temporal_scope.get("benchmark_date"),
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
                "recall_cache": recall_cache_status,
                "query_analysis_cache": query_cache_status,
                "recall_memory_watermark": memory_watermark,
            }
        )
        self._store_recall_package(recall_cache_key, package)
        return package

    def _analyze_query(self, query: str) -> tuple[QueryAnalysis, dict[str, object]]:
        if not self.settings.memoryos_recall_cache_enabled:
            return self.query_analyzer.analyze(query), self._query_cache_status("disabled")

        key = build_cache_key(
            scope="query_analysis",
            settings=self.settings,
            query=query,
        )
        cached = self.cache.get_json(key)
        if cached.status == "hit" and cached.value is not None:
            try:
                analysis = QueryAnalysis(QueryKind(str(cached.value["kind"])))
                return analysis, self._query_cache_status("hit")
            except (KeyError, ValueError, TypeError):
                status = self._query_cache_status(
                    "corrupt",
                    reason="cached query analysis failed validation",
                )
        else:
            status = self._query_cache_status(cached.status, reason=cached.reason)

        analysis = self.query_analyzer.analyze(query)
        write = self.cache.set_json(key, {"kind": analysis.kind.value})
        status["write_status"] = write.status
        if write.reason:
            status["write_reason"] = write.reason
        return analysis, status

    def _store_recall_package(
        self,
        recall_cache_key: str | None,
        package: ContextPackage,
    ) -> None:
        if not self.settings.memoryos_recall_cache_enabled or recall_cache_key is None:
            return
        write = self.cache.set_json(
            recall_cache_key,
            {"package": package.model_dump(mode="json")},
        )
        recall_cache = package.metadata.get("recall_cache")
        if isinstance(recall_cache, dict):
            recall_cache["write_status"] = write.status
            if write.reason:
                recall_cache["write_reason"] = write.reason

    @staticmethod
    def _package_from_cache(value: dict[str, Any]) -> ContextPackage | None:
        package_value = value.get("package")
        if not isinstance(package_value, dict):
            return None
        try:
            return ContextPackage.model_validate(package_value)
        except ValidationError:
            return None

    def _recall_cache_status(
        self,
        status: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        return self._cache_status(
            scope="recall_candidates",
            status=status,
            reason=reason,
        )

    def _query_cache_status(
        self,
        status: str,
        *,
        reason: str | None = None,
    ) -> dict[str, object]:
        return self._cache_status(
            scope="query_analysis",
            status=status,
            reason=reason,
        )

    def _cache_status(
        self,
        *,
        scope: str,
        status: str,
        reason: str | None = None,
    ) -> dict[str, object]:
        diagnostics: dict[str, object] = {
            "enabled": self.settings.memoryos_recall_cache_enabled,
            "scope": scope,
            "status": status,
            "namespace": self.settings.memoryos_cache_namespace.strip(":"),
        }
        if reason:
            diagnostics["fallback_reason"] = reason
        return diagnostics

    @staticmethod
    def _hash_text(text: str) -> str:
        normalized = " ".join(text.split())
        return sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _default_cache(settings: Settings) -> MemoryCache:
        if not settings.memoryos_recall_cache_enabled:
            return NoopMemoryCache()
        return create_memory_cache(settings)

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
            temporal_scope = self._hit_temporal_scope(hit)
            metadata = {
                "reason": hit.reason,
                "source": hit.source,
                "neighbor_of": hit.neighbor_of,
                "neighbor_offset": hit.rank_features.get("neighbor_offset"),
                "benchmark_session_id": temporal_scope.get("benchmark_session_id"),
                "benchmark_date": temporal_scope.get("benchmark_date"),
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
            session_id = RecallPipeline._hit_temporal_scope(hit).get(
                "benchmark_session_id"
            )
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
                    "packet_member_message_ids": RecallPipeline._metadata_list(
                        hit.packet_metadata,
                        "packet_member_message_ids",
                    ),
                    "packet_member_source_ids": RecallPipeline._metadata_list(
                        hit.packet_metadata,
                        "packet_member_source_ids",
                    ),
                    "packet_reason": hit.packet_metadata.get("packet_reason"),
                    "packet_rank": hit.packet_metadata.get("packet_rank"),
                    "score": hit.score,
                    "rank_features": dict(hit.rank_features),
                }
            )
        return packets

    @staticmethod
    def _hit_temporal_scope(hit: EpisodeHit) -> dict[str, object]:
        scope = getattr(hit.episode, "temporal_scope", {})
        return scope if isinstance(scope, dict) else {}

    @staticmethod
    def _metadata_list(metadata: dict[str, object], key: str) -> list[object]:
        value = metadata.get(key, [])
        if isinstance(value, list | tuple):
            return list(value)
        return []
