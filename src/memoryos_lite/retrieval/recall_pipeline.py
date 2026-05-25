from hashlib import sha256
from typing import Any, cast

from pydantic import ValidationError

from memoryos_lite.cache import (
    CACHE_ENTRY_VERSION,
    CacheEntry,
    CacheFingerprint,
    CacheKeyBuilder,
    CachePayloadType,
    CacheReadResult,
    CacheScope,
    CacheStatus,
    CacheWriteResult,
    DerivedCache,
    NoopDerivedCache,
    create_derived_cache,
)
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, RecallMemorySearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryAnalyzer, QueryKind
from memoryos_lite.schemas import ContextEvidence, ContextPackage, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    DiagnosticEvent,
    RecallMemoryEntry,
    episode_to_recall_entry,
)


class RecallPipeline:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings,
        tokenizer: TokenEstimator | None = None,
        cache: DerivedCache | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.tokenizer = tokenizer or TokenEstimator()
        self.query_analyzer = QueryAnalyzer()
        self.recall_searcher = RecallMemorySearcher()
        self.cache = cache if cache is not None else self._default_cache(settings)
        self.cache_key_builder = CacheKeyBuilder(
            namespace=settings.memoryos_cache_namespace
        )

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
        top_k = 10
        neighbors_before = self.settings.memoryos_evidence_context_neighbors_before
        neighbors_after = self.settings.memoryos_evidence_context_neighbors_after
        recall_cache_status = self._cache_status(
            CacheScope.RECALL_CONTEXT_PACKAGE,
            CacheStatus.DISABLED,
        )
        query_cache_status = self._cache_status(
            CacheScope.QUERY_ANALYSIS,
            CacheStatus.DISABLED,
        )
        recall_candidate_cache_status = self._cache_status(
            CacheScope.RECALL_CANDIDATES,
            CacheStatus.DISABLED,
        )
        recall_cache_key: str | None = None
        recall_fingerprint: CacheFingerprint | None = None
        if self.settings.memoryos_recall_cache_enabled:
            recall_parameters = {
                "budget": budget,
                "task_sha256": self._hash_text(task),
                "top_k": top_k,
                "neighbors_before": neighbors_before,
                "neighbors_after": neighbors_after,
            }
            recall_fingerprint = self.cache_key_builder.build_fingerprint(
                scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                settings=self.settings,
                session_id=session_id,
                query=query,
                watermark=memory_watermark,
                parameters=recall_parameters,
            )
            recall_cache_key = self.cache_key_builder.build_key(
                scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                settings=self.settings,
                session_id=session_id,
                query=query,
                watermark=memory_watermark,
                parameters=recall_parameters,
            )
            cached = self.cache.get(recall_cache_key)
            recall_cache_status = self._cache_status(
                CacheScope.RECALL_CONTEXT_PACKAGE,
                cached.status,
                reason=cached.reason,
                result=cached,
                watermark_hash=recall_fingerprint.watermark_hash,
            )
            if cached.status == CacheStatus.HIT and cached.entry is not None:
                if not self._entry_matches(
                    cached.entry,
                    fingerprint=recall_fingerprint,
                    scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                    payload_type=CachePayloadType.CONTEXT_PACKAGE,
                ):
                    recall_cache_status = self._cache_status(
                        CacheScope.RECALL_CONTEXT_PACKAGE,
                        CacheStatus.STALE,
                        reason="cached recall package fingerprint mismatch",
                        result=cached,
                        watermark_hash=recall_fingerprint.watermark_hash,
                    )
                    package = None
                else:
                    package = self._package_from_cache(
                        cached.entry,
                        fingerprint=recall_fingerprint,
                        scope=CacheScope.RECALL_CONTEXT_PACKAGE,
                        payload_type=CachePayloadType.CONTEXT_PACKAGE,
                    )
                if package is not None:
                    package.metadata["episode_backfilled"] = created
                    package.metadata["cache"] = recall_cache_status
                    package.metadata["recall_cache"] = recall_cache_status
                    package.metadata["query_analysis_cache"] = self._cache_status(
                        CacheScope.QUERY_ANALYSIS,
                        CacheStatus.DISABLED,
                        reason="recall_context_package_hit",
                    )
                    package.metadata["recall_candidate_cache"] = self._cache_status(
                        CacheScope.RECALL_CANDIDATES,
                        CacheStatus.DISABLED,
                        reason="recall_context_package_hit",
                    )
                    package.metadata["recall_memory_watermark"] = memory_watermark
                    return package
                if recall_cache_status["status"] != CacheStatus.STALE.value:
                    recall_cache_status = self._cache_status(
                        CacheScope.RECALL_CONTEXT_PACKAGE,
                        CacheStatus.CORRUPT,
                        reason="cached recall package failed validation",
                        result=cached,
                        watermark_hash=recall_fingerprint.watermark_hash,
                    )
        episodes = self.store.list_episodes(session_id)
        recall_entries: list[RecallMemoryEntry] = [
            episode_to_recall_entry(episode) for episode in episodes
        ]
        analysis, query_cache_status = self._analyze_query(query)
        preserve_session_neighbors = any(
            "benchmark_session_id" in entry.temporal_scope for entry in recall_entries
        )
        hits, recall_candidate_cache_status = self._recall_candidates(
            session_id,
            recall_entries,
            query,
            analysis=analysis,
            memory_watermark=memory_watermark,
            top_k=top_k,
            neighbors_before=neighbors_before,
            neighbors_after=neighbors_after,
            preserve_session_neighbors=preserve_session_neighbors,
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
                    "cache": recall_cache_status,
                    "recall_cache": recall_cache_status,
                    "query_analysis_cache": query_cache_status,
                    "recall_candidate_cache": recall_candidate_cache_status,
                    "recall_memory_watermark": memory_watermark,
                }
            )
            self._store_recall_package(recall_cache_key, recall_fingerprint, package)
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
                "cache": recall_cache_status,
                "recall_cache": recall_cache_status,
                "query_analysis_cache": query_cache_status,
                "recall_candidate_cache": recall_candidate_cache_status,
                "recall_memory_watermark": memory_watermark,
            }
        )
        self._store_recall_package(recall_cache_key, recall_fingerprint, package)
        return package

    def _analyze_query(self, query: str) -> tuple[QueryAnalysis, dict[str, object]]:
        if not self.settings.memoryos_recall_cache_enabled:
            return self.query_analyzer.analyze(query), self._cache_status(
                CacheScope.QUERY_ANALYSIS,
                CacheStatus.DISABLED,
            )

        fingerprint = self.cache_key_builder.build_fingerprint(
            scope=CacheScope.QUERY_ANALYSIS,
            settings=self.settings,
            query=query,
        )
        key = self.cache_key_builder.build_key(
            scope=CacheScope.QUERY_ANALYSIS,
            settings=self.settings,
            query=query,
        )
        cached = self.cache.get(key)
        if cached.status == CacheStatus.HIT and cached.entry is not None:
            if not self._entry_matches(
                cached.entry,
                fingerprint=fingerprint,
                scope=CacheScope.QUERY_ANALYSIS,
                payload_type=CachePayloadType.QUERY_ANALYSIS,
            ):
                status = self._cache_status(
                    CacheScope.QUERY_ANALYSIS,
                    CacheStatus.STALE,
                    reason="cached query analysis fingerprint mismatch",
                    result=cached,
                    watermark_hash=fingerprint.watermark_hash,
                )
            else:
                try:
                    analysis = QueryAnalysis(QueryKind(str(cached.entry.payload["kind"])))
                    return analysis, self._cache_status(
                        CacheScope.QUERY_ANALYSIS,
                        CacheStatus.HIT,
                        result=cached,
                        watermark_hash=fingerprint.watermark_hash,
                    )
                except (KeyError, ValueError, TypeError):
                    status = self._cache_status(
                        CacheScope.QUERY_ANALYSIS,
                        CacheStatus.CORRUPT,
                        reason="cached query analysis failed validation",
                        result=cached,
                        watermark_hash=fingerprint.watermark_hash,
                    )
        else:
            status = self._cache_status(
                CacheScope.QUERY_ANALYSIS,
                cached.status,
                reason=cached.reason,
                result=cached,
                watermark_hash=fingerprint.watermark_hash,
            )

        analysis = self.query_analyzer.analyze(query)
        entry = CacheEntry(
            scope=CacheScope.QUERY_ANALYSIS,
            payload_type=CachePayloadType.QUERY_ANALYSIS,
            fingerprint=fingerprint,
            payload={"kind": analysis.kind.value},
            created_at=utc_now(),
            ttl_s=self.settings.memoryos_cache_query_analysis_ttl_s,
        )
        write = self.cache.set(
            key,
            entry,
            ttl_s=self.settings.memoryos_cache_query_analysis_ttl_s,
        )
        self._record_write_status(status, write)
        return analysis, status

    def _recall_candidates(
        self,
        session_id: str,
        recall_entries: list[RecallMemoryEntry],
        query: str,
        *,
        analysis: QueryAnalysis,
        memory_watermark: str,
        top_k: int,
        neighbors_before: int,
        neighbors_after: int,
        preserve_session_neighbors: bool,
    ) -> tuple[list[EpisodeHit], dict[str, object]]:
        if not self.settings.memoryos_recall_cache_enabled:
            hits = self._search_recall_candidates(
                recall_entries,
                query,
                analysis=analysis,
                top_k=top_k,
                neighbors_before=neighbors_before,
                neighbors_after=neighbors_after,
                preserve_session_neighbors=preserve_session_neighbors,
            )
            return hits, self._cache_status(
                CacheScope.RECALL_CANDIDATES,
                CacheStatus.DISABLED,
            )

        parameters = {
            "top_k": top_k,
            "neighbors_before": neighbors_before,
            "neighbors_after": neighbors_after,
            "preserve_session_neighbors": preserve_session_neighbors,
        }
        fingerprint = self.cache_key_builder.build_fingerprint(
            scope=CacheScope.RECALL_CANDIDATES,
            settings=self.settings,
            session_id=session_id,
            query=query,
            watermark=memory_watermark,
            parameters=parameters,
        )
        key = self.cache_key_builder.build_key(
            scope=CacheScope.RECALL_CANDIDATES,
            settings=self.settings,
            session_id=session_id,
            query=query,
            watermark=memory_watermark,
            parameters=parameters,
        )
        cached = self.cache.get(key)
        if cached.status == CacheStatus.HIT and cached.entry is not None:
            if not self._entry_matches(
                cached.entry,
                fingerprint=fingerprint,
                scope=CacheScope.RECALL_CANDIDATES,
                payload_type=CachePayloadType.RECALL_CANDIDATES,
            ):
                status = self._cache_status(
                    CacheScope.RECALL_CANDIDATES,
                    CacheStatus.STALE,
                    reason="cached recall candidates fingerprint mismatch",
                    result=cached,
                    watermark_hash=fingerprint.watermark_hash,
                )
            else:
                cached_hits = self._candidate_hits_from_cache(
                    cached.entry,
                    recall_entries,
                    fingerprint=fingerprint,
                )
                if cached_hits is not None:
                    return cached_hits, self._cache_status(
                        CacheScope.RECALL_CANDIDATES,
                        CacheStatus.HIT,
                        result=cached,
                        watermark_hash=fingerprint.watermark_hash,
                    )
                status = self._cache_status(
                    CacheScope.RECALL_CANDIDATES,
                    CacheStatus.CORRUPT,
                    reason="cached recall candidates failed validation",
                    result=cached,
                    watermark_hash=fingerprint.watermark_hash,
                )
        else:
            status = self._cache_status(
                CacheScope.RECALL_CANDIDATES,
                cached.status,
                reason=cached.reason,
                result=cached,
                watermark_hash=fingerprint.watermark_hash,
            )

        hits = self._search_recall_candidates(
            recall_entries,
            query,
            analysis=analysis,
            top_k=top_k,
            neighbors_before=neighbors_before,
            neighbors_after=neighbors_after,
            preserve_session_neighbors=preserve_session_neighbors,
        )
        entry = CacheEntry(
            scope=CacheScope.RECALL_CANDIDATES,
            payload_type=CachePayloadType.RECALL_CANDIDATES,
            fingerprint=fingerprint,
            payload={"hits": [self._candidate_hit_to_cache(hit) for hit in hits]},
            created_at=utc_now(),
            ttl_s=self.settings.memoryos_cache_recall_candidates_ttl_s,
        )
        write = self.cache.set(
            key,
            entry,
            ttl_s=self.settings.memoryos_cache_recall_candidates_ttl_s,
        )
        self._record_write_status(status, write)
        return hits, status

    def _search_recall_candidates(
        self,
        recall_entries: list[RecallMemoryEntry],
        query: str,
        *,
        analysis: QueryAnalysis,
        top_k: int,
        neighbors_before: int,
        neighbors_after: int,
        preserve_session_neighbors: bool,
    ) -> list[EpisodeHit]:
        return self.recall_searcher.search(
            cast(Any, recall_entries),
            query,
            top_k=top_k,
            analysis=analysis,
            neighbors_before=neighbors_before,
            neighbors_after=neighbors_after,
            preserve_neighbors=preserve_session_neighbors,
        )

    def _store_recall_package(
        self,
        recall_cache_key: str | None,
        recall_fingerprint: CacheFingerprint | None,
        package: ContextPackage,
    ) -> None:
        if (
            not self.settings.memoryos_recall_cache_enabled
            or recall_cache_key is None
            or recall_fingerprint is None
        ):
            return
        entry = CacheEntry(
            scope=CacheScope.RECALL_CONTEXT_PACKAGE,
            payload_type=CachePayloadType.CONTEXT_PACKAGE,
            fingerprint=recall_fingerprint,
            payload={"package": package.model_dump(mode="json")},
            created_at=utc_now(),
            ttl_s=self.settings.memoryos_cache_context_package_ttl_s,
        )
        write = self.cache.set(
            recall_cache_key,
            entry,
            ttl_s=self.settings.memoryos_cache_context_package_ttl_s,
        )
        for metadata_key in ("cache", "recall_cache"):
            cache_metadata = package.metadata.get(metadata_key)
            if isinstance(cache_metadata, dict):
                self._record_write_status(cache_metadata, write)

    @staticmethod
    def _package_from_cache(
        entry: CacheEntry,
        *,
        fingerprint: CacheFingerprint,
        scope: CacheScope,
        payload_type: CachePayloadType,
    ) -> ContextPackage | None:
        if not RecallPipeline._entry_matches(
            entry,
            fingerprint=fingerprint,
            scope=scope,
            payload_type=payload_type,
        ):
            return None
        package_value = entry.payload.get("package")
        if not isinstance(package_value, dict):
            return None
        try:
            return ContextPackage.model_validate(package_value)
        except ValidationError:
            return None

    @staticmethod
    def _candidate_hit_to_cache(hit: EpisodeHit) -> dict[str, object]:
        return {
            "message_id": hit.episode.message_id,
            "score": hit.score,
            "reason": hit.reason,
            "source": hit.source,
            "rank_features": dict(hit.rank_features),
            "neighbor_of": hit.neighbor_of,
            "packet_metadata": dict(hit.packet_metadata),
            "diagnostics": [
                diagnostic.model_dump(mode="json") for diagnostic in hit.diagnostics
            ],
        }

    @staticmethod
    def _candidate_hits_from_cache(
        entry: CacheEntry,
        recall_entries: list[RecallMemoryEntry],
        *,
        fingerprint: CacheFingerprint,
    ) -> list[EpisodeHit] | None:
        if not RecallPipeline._entry_matches(
            entry,
            fingerprint=fingerprint,
            scope=CacheScope.RECALL_CANDIDATES,
            payload_type=CachePayloadType.RECALL_CANDIDATES,
        ):
            return None
        raw_hits = entry.payload.get("hits")
        if not isinstance(raw_hits, list):
            return None
        entries_by_message_id = {entry.message_id: entry for entry in recall_entries}
        hits: list[EpisodeHit] = []
        try:
            for raw_hit in raw_hits:
                if not isinstance(raw_hit, dict):
                    return None
                message_id = raw_hit["message_id"]
                if not isinstance(message_id, str):
                    return None
                recall_entry = entries_by_message_id.get(message_id)
                if recall_entry is None:
                    return None
                rank_features = raw_hit.get("rank_features", {})
                packet_metadata = raw_hit.get("packet_metadata", {})
                diagnostics = raw_hit.get("diagnostics", [])
                if not isinstance(rank_features, dict):
                    return None
                if not isinstance(packet_metadata, dict):
                    return None
                if not isinstance(diagnostics, list):
                    return None
                hits.append(
                    EpisodeHit(
                        episode=recall_entry,
                        score=float(raw_hit["score"]),
                        reason=str(raw_hit["reason"]),
                        source=str(raw_hit.get("source", "recall_memory")),
                        diagnostics=tuple(
                            DiagnosticEvent.model_validate(diagnostic)
                            for diagnostic in diagnostics
                        ),
                        rank_features={
                            str(key): float(value)
                            for key, value in rank_features.items()
                        },
                        neighbor_of=(
                            str(raw_hit["neighbor_of"])
                            if raw_hit.get("neighbor_of") is not None
                            else None
                        ),
                        packet_metadata=dict(packet_metadata),
                    )
                )
        except (KeyError, TypeError, ValueError, ValidationError):
            return None
        return hits

    @staticmethod
    def _entry_matches(
        entry: CacheEntry,
        *,
        fingerprint: CacheFingerprint,
        scope: CacheScope,
        payload_type: CachePayloadType,
    ) -> bool:
        return (
            entry.scope == scope
            and entry.payload_type == payload_type
            and entry.fingerprint == fingerprint
        )

    def _cache_status(
        self,
        scope: CacheScope,
        status: CacheStatus,
        *,
        reason: str | None = None,
        result: CacheReadResult | CacheWriteResult | None = None,
        watermark_hash: str | None = None,
    ) -> dict[str, object]:
        diagnostics: dict[str, object] = {
            "enabled": self.settings.memoryos_recall_cache_enabled,
            "backend": self.cache.backend_name,
            "scope": scope.value,
            "status": status.value,
            "key_version": CACHE_ENTRY_VERSION,
        }
        if watermark_hash is not None:
            diagnostics["watermark_hash"] = watermark_hash
        fallback_reason = reason
        if fallback_reason is None and result is not None:
            fallback_reason = result.reason
        if fallback_reason:
            diagnostics["fallback_reason"] = fallback_reason
        if result is not None:
            latency_ms = result.diagnostics.get("latency_ms")
            if latency_ms is not None:
                diagnostics["latency_ms"] = latency_ms
        return diagnostics

    @staticmethod
    def _record_write_status(
        status: dict[str, object],
        write: CacheWriteResult,
    ) -> None:
        status["write_status"] = write.status.value
        if write.reason:
            status["write_reason"] = write.reason

    @staticmethod
    def _hash_text(text: str) -> str:
        normalized = " ".join(text.split())
        return sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _default_cache(settings: Settings) -> DerivedCache:
        if not settings.memoryos_recall_cache_enabled:
            return NoopDerivedCache()
        return create_derived_cache(settings)

    def _serialize_diagnostics(
        self,
        hits: list[EpisodeHit],
    ) -> list[dict[str, object]]:
        return [event for hit in hits for event in self._dump_hit_diagnostics(hit)]

    def _dump_hit_diagnostics(self, hit: EpisodeHit) -> list[dict[str, object]]:
        return [diagnostic.model_dump(mode="json") for diagnostic in hit.diagnostics]

    def _budget_drop_diagnostics(
        self,
        hits: list[EpisodeHit],
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

    def _packet_summaries(self, hits: list[EpisodeHit]) -> list[dict[str, object]]:
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
                    "packet_member_message_ids": self._metadata_list(
                        hit.packet_metadata,
                        "packet_member_message_ids",
                    ),
                    "packet_member_neighbor_offsets": self._metadata_list(
                        hit.packet_metadata,
                        "packet_member_neighbor_offsets",
                    ),
                    "packet_member_source_ids": self._metadata_list(
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
