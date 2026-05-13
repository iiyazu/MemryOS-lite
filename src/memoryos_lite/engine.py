import time
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from memoryos_lite.budget import DynamicBudget
from memoryos_lite.config import Settings, get_settings
from memoryos_lite.conflict import ConflictDetector, _extract_implicit_value
from memoryos_lite.observability import (
    CONTEXT_BUDGET_USED_RATIO,
    CONTEXT_BUILD_SECONDS,
    CONTEXT_TOKENS,
    EMBEDDING_SECONDS,
    INGEST_TOTAL,
    PAGE_ERRORS_TOTAL,
    PAGE_TOTAL,
    RETRIEVAL_HITS,
)
from memoryos_lite.retrieval import (
    EmbeddingClient,
    EmbeddingSearcher,
    HybridSearcher,
    LexicalSearcher,
    LLMReranker,
    QueryRewriter,
    Searcher,
    SearchHit,
)
from memoryos_lite.retrieval.providers import OpenAIEmbeddingClient
from memoryos_lite.schemas import (
    ContextPackage,
    ContextPage,
    IngestResponse,
    MemoryPage,
    MemoryPageDraft,
    MemoryPatch,
    Message,
    MessageCreate,
    PageType,
    PatchOperation,
    Role,
    TraceEvent,
    utc_now,
)
from memoryos_lite.store import MemoryStore, create_store
from memoryos_lite.tokenizer import TokenEstimator

__all__ = [
    "ContextRotGuard",
    "MemoryOSService",
    "PagingAgent",
    "SearchHit",
]


class ContextRotGuard:
    def __init__(self, settings: Settings, tokenizer: TokenEstimator) -> None:
        self.settings = settings
        self.tokenizer = tokenizer

    def should_page(self, messages: list[Message]) -> bool:
        return sum(message.token_count for message in messages) >= self.settings.rot_safe_budget


class PageDraftClient(Protocol):
    def create_draft(self, messages: list[Message]) -> MemoryPageDraft:
        pass


class OpenAIPageDraftClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for llm paging mode")
        self.model = ChatOpenAI(
            model=settings.memoryos_model,
            api_key=SecretStr(settings.openai_api_key),
            base_url=settings.openai_base_url,
            temperature=0,
        ).with_structured_output(MemoryPageDraft)

    def create_draft(self, messages: list[Message]) -> MemoryPageDraft:
        transcript = "\n".join(
            f"{message.id} [{message.role.value}]: {message.content}" for message in messages
        )
        result = self.model.invoke(
            [
                SystemMessage(
                    content=(
                        "You are the Paging Agent for MemoryOS Lite. Convert the old "
                        "conversation segment into a concise memory page. Preserve source "
                        "message ids exactly. Do not invent facts."
                    )
                ),
                HumanMessage(content=transcript),
            ]
        )
        if not isinstance(result, MemoryPageDraft):
            raise TypeError("structured output did not return MemoryPageDraft")
        return result


# Markers the heuristic pager uses to identify messages that supersede prior
# state ("I've moved to …", "changed to …"). Kept at module scope so the
# intra-draft conflict sweep can prioritise these items when rebuilding
# ``page.summary`` after pruning.
_UPDATE_MARKERS: tuple[str, ...] = (
    "更新",
    "改为",
    "搬到",
    "不再",
    "已经搬",
    "不住",
    "替换",
    "纠正",
    "其实",
)


class PagingAgent:
    def __init__(
        self,
        settings: Settings,
        llm_client: PageDraftClient | None = None,
        llm_init_error: str | None = None,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.llm_init_error = llm_init_error
        # Used as a signal for "this fact looks structured" when ranking
        # which facts make it into ``page.summary``.
        from memoryos_lite.conflict import SlotExtractor

        self._slot_extractor = SlotExtractor()

    def create_draft(
        self,
        session_id: str,
        messages: list[Message],
    ) -> tuple[MemoryPageDraft | None, str, str | None]:
        if len(messages) <= self.settings.recent_message_limit:
            return None, "none", None
        page_messages = messages[: -self.settings.recent_message_limit]
        if not page_messages:
            return None, "none", None
        if len(page_messages) < 2:
            return None, "none", None
        if self.settings.memoryos_paging_mode == "llm" and self.llm_client is None:
            draft = self._heuristic_draft(session_id, page_messages)
            return draft, "heuristic_fallback", self.llm_init_error or "llm client unavailable"
        if self.settings.memoryos_paging_mode == "llm" and self.llm_client is not None:
            try:
                return self.llm_client.create_draft(page_messages), "llm", None
            except Exception as exc:
                draft = self._heuristic_draft(session_id, page_messages)
                return draft, "heuristic_fallback", str(exc)
        return self._heuristic_draft(session_id, page_messages), "heuristic", None

    def _heuristic_draft(
        self,
        session_id: str,
        page_messages: list[Message],
    ) -> MemoryPageDraft:
        facts: list[str] = []
        decisions: list[str] = []
        open_questions: list[str] = []
        tool_notes: list[str] = []
        updates: list[str] = []  # override/correction signals
        update_markers = _UPDATE_MARKERS
        for message in page_messages:
            compact = self._compact(message.content)
            if not compact:
                continue
            if message.role == Role.TOOL:
                tool_notes.append(compact)
            elif any(marker in compact for marker in update_markers):
                updates.append(compact)
                facts.append(compact)
            elif any(marker in compact for marker in ("决定", "选择", "不做", "不要", "最终")):
                decisions.append(compact)
            elif "?" in compact or "？" in compact or "如何" in compact:
                open_questions.append(compact)
            else:
                facts.append(compact)
        title = self._title(page_messages)
        # Summary prioritises: (a) overrides/updates (latest state wins),
        # (b) earliest facts (for continuity), (c) decisions, (d) tool notes.
        # This ensures "我已经搬到上海" beats "我住在北京" in summary visibility.
        summary_parts: list[str] = []
        seen: set[str] = set()

        def _add(text: str) -> None:
            if text and text not in seen:
                summary_parts.append(text)
                seen.add(text)

        for item in updates[-2:]:
            _add(item)

        # Rank facts by informativeness before the truncation slice.
        # A fact is "structured" — and earns priority placement — when
        # its text yields a ``subject+verb+value`` slot parse (e.g.
        # "我搬到上海", "我喜欢用 Vim"). Chit-chat like "已记录" and
        # unbounded-noise facts without a structured verb fall through
        # to the low-priority bucket. Ordering within each bucket is
        # preserved to keep the "earliest facts win" continuity
        # invariant.
        #
        # **Why slot-only (not colon-heuristic)**: labelled noise such
        # as "第 1 段无关长噪声：…" or "旧方向：Runbook…" also contains
        # a ``：`` but is precisely what the summary should NOT
        # surface. The slot extractor's verb allow-list is narrow
        # enough to keep those out while still catching moved-residence
        # / tool-choice updates.
        def _is_informative(text: str) -> bool:
            return bool(self._slot_extractor.extract(text))

        informative_facts = [f for f in facts if _is_informative(f)]
        other_facts = [f for f in facts if f not in informative_facts]
        ranked_facts = [*informative_facts, *other_facts]
        for item in ranked_facts[:3]:
            _add(item)
        for item in decisions[:3]:
            _add(item)
        for item in tool_notes[:2]:
            _add(item)
        summary = "；".join(summary_parts[:6]) if summary_parts else "历史会话片段摘要"
        page_type = (
            PageType.TOOL_OBSERVATION if tool_notes and not facts else PageType.SOURCE_SUMMARY
        )
        if decisions:
            page_type = PageType.DECISION
        elif self._looks_like_profile(facts):
            page_type = PageType.CORE_PROFILE
        return MemoryPageDraft(
            page_type=page_type,
            title=title,
            summary=summary,
            facts=facts[:8],
            decisions=decisions[:8],
            open_questions=open_questions[:5],
            discarded_noise=[],
            source_message_ids=[message.id for message in page_messages],
            confidence=0.78,
        )

    def _compact(self, text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if len(cleaned) > 180:
            return cleaned[:177] + "..."
        return cleaned

    @staticmethod
    def _looks_like_profile(facts: list[str]) -> bool:
        text = " ".join(facts)
        profile_markers = (
            "自我介绍",
            "我是一名",
            "我的职业",
            "职业背景",
            "技术栈",
            "我喜欢",
            "我偏好",
            "我习惯",
            "我住在",
            "我现在住",
            "I am ",
            "I'm ",
            "my role",
            "my background",
            "I prefer",
            "I like",
            "I live",
        )
        return any(marker in text for marker in profile_markers)

    def _title(self, messages: list[Message]) -> str:
        for message in messages:
            if message.role == Role.USER and message.content.strip():
                compact = self._compact(message.content)
                return compact[:40]
        return "Session memory page"


class PageVerifier:
    def verify(self, draft: MemoryPageDraft, messages: list[Message]) -> list[str]:
        errors: list[str] = []
        message_ids = {message.id for message in messages}
        if not draft.source_message_ids:
            errors.append("source_message_ids is required")
        missing = [
            source_id for source_id in draft.source_message_ids if source_id not in message_ids
        ]
        if missing:
            errors.append(f"unknown source refs: {', '.join(missing)}")
        if not draft.summary.strip():
            errors.append("summary is required")
        return errors


class PatchVerifier:
    protected_markers = ("DO NOT EDIT", "PROTECTED")

    def verify(
        self,
        patch: MemoryPatch,
        page: MemoryPage | None,
        source_messages: list[Message],
    ) -> MemoryPatch:
        errors: list[str] = []
        source_ids = {message.id for message in source_messages}
        missing_sources = [
            source_ref for source_ref in patch.source_refs if source_ref not in source_ids
        ]
        if missing_sources:
            errors.append(f"unknown source refs: {', '.join(missing_sources)}")
        if patch.operation in {PatchOperation.REPLACE, PatchOperation.DELETE}:
            if not patch.old_text:
                errors.append("old_text is required for replace/delete")
            elif page is None:
                errors.append("target page is required")
            else:
                searchable = "\n".join(
                    [page.summary] + page.facts + page.decisions + page.open_questions
                )
                if patch.old_text not in searchable:
                    errors.append("old_text does not exist in modifiable page fields")
        elif patch.operation == PatchOperation.ADD:
            if page is None:
                errors.append("target page is required")
            if not patch.new_text:
                errors.append("new_text is required for add")
        if patch.new_text and any(marker in patch.new_text for marker in self.protected_markers):
            errors.append("new_text attempts to modify protected memory block")
        patch.errors = errors
        patch.verified = not errors
        return patch


class ContextBuilder:
    def __init__(
        self,
        tokenizer: TokenEstimator,
        searcher: Searcher,
        settings: Settings,
    ) -> None:
        self.tokenizer = tokenizer
        self.searcher = searcher
        self.settings = settings

    def build(
        self,
        session_id: str,
        task: str,
        messages: list[Message],
        pages: list[MemoryPage],
        budget: int,
        retrieval_query: str | None = None,
    ) -> ContextPackage:
        query = retrieval_query or task
        recent_messages = messages[-self.settings.recent_message_limit :]
        task_tokens = self.tokenizer.count(task)
        used_tokens = task_tokens
        package = ContextPackage(
            session_id=session_id,
            task=task,
            task_tokens=task_tokens,
            task_truncated=False,
        )
        if task_tokens > budget:
            package.task_truncated = True
            package.dropped_recent_messages = [message.id for message in recent_messages]
            for page in pages:
                package.dropped_pages.append(
                    ContextPage(
                        page_id=page.id,
                        title=page.title,
                        reason="task_exceeds_budget",
                        estimated_tokens=self.tokenizer.count(page.summary),
                    )
                )
            package.estimated_tokens = task_tokens
            return package

        pinned_core_page_ids: set[str] = set()
        dropped_core_page_ids: set[str] = set()
        core_pages = [page for page in pages if page.page_type == PageType.CORE_PROFILE]
        for page in core_pages:
            text = page.summary
            page_tokens = self.tokenizer.count(text)
            if used_tokens + page_tokens <= budget:
                package.pinned_core.append(text)
                pinned_core_page_ids.add(page.id)
                used_tokens += page_tokens
            else:
                dropped_core_page_ids.add(page.id)
                package.dropped_pages.append(
                    ContextPage(
                        page_id=page.id,
                        title=page.title,
                        reason="core_profile_exceeds_budget",
                        estimated_tokens=page_tokens,
                    )
                )

        selected_recent: list[Message] = []
        for message in reversed(recent_messages):
            if used_tokens + message.token_count <= budget:
                selected_recent.append(message)
                used_tokens += message.token_count
            else:
                package.dropped_recent_messages.append(message.id)
        package.recent_messages = list(reversed(selected_recent))

        hits = self.searcher.search(pages, query=query, top_k=max(5, len(pages)))
        for hit in hits:
            if hit.page.id in pinned_core_page_ids or hit.page.id in dropped_core_page_ids:
                continue
            page_tokens = self.tokenizer.count(hit.page.summary)
            context_page = ContextPage(
                page_id=hit.page.id,
                title=hit.page.title,
                reason=hit.reason,
                estimated_tokens=page_tokens,
            )
            if used_tokens + page_tokens <= budget:
                if hit.page.page_type in {PageType.TASK_STATE, PageType.DECISION}:
                    package.active_task_pages.append(context_page)
                else:
                    package.retrieved_pages.append(context_page)
                used_tokens += page_tokens
            else:
                package.dropped_pages.append(context_page)
        package.estimated_tokens = used_tokens
        return package


class MemoryOSService:
    def __init__(
        self,
        store: MemoryStore | None = None,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or create_store(self.settings)
        self.tokenizer = TokenEstimator()
        self.rot_guard = ContextRotGuard(self.settings, self.tokenizer)
        llm_client: PageDraftClient | None = None
        llm_init_error: str | None = None
        if self.settings.memoryos_paging_mode == "llm":
            try:
                llm_client = OpenAIPageDraftClient(self.settings)
            except Exception as exc:
                llm_init_error = str(exc)
                llm_client = None
        self.paging_agent = PagingAgent(
            self.settings,
            llm_client=llm_client,
            llm_init_error=llm_init_error,
        )
        self.page_verifier = PageVerifier()
        self.patch_verifier = PatchVerifier()
        self.embedding_client = embedding_client or self._default_embedding_client()
        lexical = LexicalSearcher()
        embedding = (
            EmbeddingSearcher(self.store, self.embedding_client)
            if self.embedding_client is not None
            else None
        )
        query_rewriter = (
            QueryRewriter(
                model=self.settings.memoryos_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )
            if self.settings.memoryos_rewrite_enabled and self.settings.openai_api_key
            else None
        )
        reranker = (
            LLMReranker(
                model=self.settings.memoryos_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )
            if self.settings.memoryos_rerank_enabled and self.settings.openai_api_key
            else None
        )
        self.searcher: Searcher = HybridSearcher(
            lexical=lexical,
            embedding=embedding,
            query_rewriter=query_rewriter,
            reranker=reranker,
        )
        self.context_builder = ContextBuilder(self.tokenizer, self.searcher, self.settings)
        self.dynamic_budget = DynamicBudget(self.settings, self.tokenizer)
        self.conflict_detector = ConflictDetector(lexical)

    def _default_embedding_client(self) -> EmbeddingClient | None:
        if not self.settings.openai_api_key:
            return None
        try:
            return OpenAIEmbeddingClient(self.settings)
        except Exception:
            return None

    def create_session(self, title: str) -> Any:
        session = self.store.create_session(title)
        self.trace(session.id, "session_created", {"title": title})
        return session

    def ingest(self, session_id: str, request: MessageCreate) -> IngestResponse:
        self._require_session(session_id)
        INGEST_TOTAL.inc()
        message = Message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
            token_count=self.tokenizer.count(request.content),
        )
        self.store.add_message(message)
        token_count = self.store.session_token_count(session_id)
        should_page = token_count >= self.settings.rot_safe_budget
        self.trace(
            session_id,
            "message_ingested",
            {
                "message_id": message.id,
                "token_count": message.token_count,
                "should_page": should_page,
            },
        )
        return IngestResponse(
            message=message,
            should_page=should_page,
            session_token_count=token_count,
        )

    def maybe_page(self, session_id: str) -> MemoryPage | None:
        if self.store.session_token_count(session_id) < self.settings.rot_safe_budget:
            self.trace(session_id, "paging_skipped", {"reason": "below_rot_safe_budget"})
            return None
        return self.page(session_id)

    def page(self, session_id: str) -> MemoryPage | None:
        self._require_session(session_id)
        messages = self.store.list_messages(session_id)
        paged_source_ids = {
            source_id
            for page in self.store.list_pages(session_id)
            for source_id in page.source_message_ids
        }
        candidate_messages = [message for message in messages if message.id not in paged_source_ids]
        draft, paging_mode, paging_error = self.paging_agent.create_draft(
            session_id,
            candidate_messages,
        )
        if draft is None:
            self.trace(
                session_id,
                "paging_skipped",
                {"reason": "not_enough_messages", "paging_mode": paging_mode},
            )
            return None
        errors = self.page_verifier.verify(draft, messages)
        if errors:
            PAGE_ERRORS_TOTAL.labels(stage="verify").inc()
            self.trace(
                session_id,
                "paging_rejected",
                {"errors": errors, "paging_mode": paging_mode, "paging_error": paging_error},
            )
            return None
        dropped = self._drop_intra_draft_conflicts(draft)
        if dropped:
            self.trace(
                session_id,
                "intra_draft_conflicts_dropped",
                {"dropped": dropped, "paging_mode": paging_mode},
            )
        page = MemoryPage(session_id=session_id, **draft.model_dump())
        self.store.save_page(page)
        self._index_page_embedding(page)
        self._supersede_conflicting_pages(session_id, page)
        PAGE_TOTAL.labels(mode=paging_mode).inc()
        self.trace(
            session_id,
            "page_committed",
            {
                "page_id": page.id,
                "source_message_ids": page.source_message_ids,
                "paging_mode": paging_mode,
                "paging_error": paging_error,
            },
        )
        return page

    def _drop_intra_draft_conflicts(self, draft: MemoryPageDraft) -> list[str]:
        """Drop older slot-conflicting entries inside a single draft.

        When a conversation revises a fact ("数据库选 PostgreSQL" → later
        "数据库改用 MySQL") mid-window, both statements land in the same
        page draft and cancel each other out at retrieval time. We use the
        ConflictDetector's slot logic to find contradicting pairs inside
        the draft itself and drop whichever appears FIRST (the heuristic
        pager appends in message order, so index 0 is oldest).

        Returns the list of dropped statements for tracing.
        """
        slot_extractor = self.conflict_detector.slot_extractor
        dropped: list[str] = []
        # Track the OLD values that were replaced by a later statement. After
        # pruning direct contradictions we sweep surviving items once more to
        # drop any that still reference an obsolete value — e.g. "部署 Redis
        # cluster" after "缓存层切换到 Memcached" replaces the cache choice.
        superseded_values: set[str] = set()

        def _record_superseded(current: str, later_items: list[str]) -> None:
            """Stash OLD values so second-pass sweep can drop stragglers."""
            current_slots = slot_extractor.extract(current)
            if current_slots:
                for slot in current_slots:
                    if slot.value:
                        superseded_values.add(slot.value)
                return
            for later in later_items:
                later_slots = slot_extractor.extract(later)
                if not later_slots:
                    continue
                for core in (slot.subject for slot in later_slots):
                    val = _extract_implicit_value(current, core)
                    if val:
                        superseded_values.add(val)

        def _shadowed_by_later(current: str, later_items: list[str]) -> bool:
            """Does any later statement contradict ``current``?

            Checks both the verb-based slot path (both sides have a slot) and
            the implicit-value path (current is a verb-less ``subject value``
            statement like "预算 5 万美元" that is later overwritten).
            """
            current_slots = slot_extractor.extract(current)
            for later in later_items:
                later_slots = slot_extractor.extract(later)
                if not later_slots:
                    continue
                # Verb-based: current has its own slot and they contradict.
                if current_slots and any(
                    self.conflict_detector._slot_conflict([ls], cs)
                    for cs in current_slots
                    for ls in later_slots
                ):
                    return True
                # Implicit: current has no verb slot, but later's subject
                # locates a quantity inside current that differs.
                if (
                    not current_slots
                    and self.conflict_detector._implicit_value_conflict(later_slots, current)
                    is not None
                ):
                    return True
            return False

        def _prune(items: list[str]) -> list[str]:
            surviving: list[str] = []
            for i, current in enumerate(items):
                if _shadowed_by_later(current, items[i + 1 :]):
                    dropped.append(current)
                    _record_superseded(current, items[i + 1 :])
                else:
                    surviving.append(current)
            # Second pass: drop leftovers that still reference a replaced
            # value. Only triggers when a real supersession happened above,
            # and requires a non-trivial value (≥3 chars) to avoid matching
            # short common tokens.
            if not superseded_values:
                return surviving
            filtered: list[str] = []
            for item in surviving:
                stale = next(
                    (v for v in superseded_values if len(v) >= 3 and v in item),
                    None,
                )
                if stale is not None:
                    dropped.append(item)
                else:
                    filtered.append(item)
            return filtered

        draft.facts = _prune(draft.facts)
        draft.decisions = _prune(draft.decisions)
        if dropped:
            # Rebuild summary to mirror the heuristic pager's priority:
            # update-flagged facts first (latest state wins), then decisions,
            # then other facts. Without this prioritisation the old ``[:3]``
            # slice could omit the update itself when it landed after
            # filler messages, leaving the summary empty of the very fact
            # the user wanted remembered (ticket #3).
            separator = "；"
            updates_in_facts = [f for f in draft.facts if any(m in f for m in _UPDATE_MARKERS)]
            other_facts = [f for f in draft.facts if f not in updates_in_facts]
            parts: list[str] = []
            for item in (
                *updates_in_facts[-2:],
                *draft.decisions[:3],
                *other_facts[:3],
            ):
                if item and item not in parts:
                    parts.append(item)
            draft.summary = separator.join(parts[:6]) if parts else "历史会话片段摘要"
        return dropped

    def _supersede_conflicting_pages(self, session_id: str, new_page: MemoryPage) -> None:
        """Mark older pages superseded when ``new_page`` conflicts with them.

        Runs at the end of ``page()`` and is best-effort — detector errors
        never block paging. Each superseded page is persisted with
        ``superseded_by = new_page.id`` so that retrieval and context
        building can skip it, and a ``page_superseded`` trace event is
        emitted for observability.
        """
        existing = [
            p
            for p in self.store.list_pages(session_id)
            if p.id != new_page.id and p.superseded_by is None
        ]
        if not existing:
            return
        try:
            conflicts = self.conflict_detector.detect_page_conflicts(new_page, existing)
        except Exception as exc:  # pragma: no cover — defensive
            self.trace(
                session_id,
                "conflict_detection_failed",
                {"new_page_id": new_page.id, "error": str(exc)},
            )
            return
        superseded_ids: set[str] = set()
        for conflict in conflicts:
            if conflict.page_id in superseded_ids:
                continue
            updated = self.store.mark_page_superseded(conflict.page_id, new_page.id)
            if updated is None:
                continue
            superseded_ids.add(conflict.page_id)
            self.trace(
                session_id,
                "page_superseded",
                {
                    "old_page_id": conflict.page_id,
                    "new_page_id": new_page.id,
                    "conflicting_text": conflict.conflicting_text,
                    "reason": conflict.reason,
                },
            )

    def _index_page_embedding(self, page: MemoryPage) -> None:
        if self.embedding_client is None:
            return
        text = " ".join(
            filter(
                None,
                [
                    page.title,
                    page.summary,
                    *page.facts,
                    *page.decisions,
                    *page.open_questions,
                ],
            )
        )
        if not text.strip():
            return
        t0 = time.perf_counter()
        try:
            vector = self.embedding_client.embed(text)
            if not vector:
                return
            EMBEDDING_SECONDS.observe(time.perf_counter() - t0)
            self.store.set_page_embedding(page.id, vector)
        except Exception as exc:
            PAGE_ERRORS_TOTAL.labels(stage="embed").inc()
            self.trace(
                page.session_id,
                "embedding_failed",
                {"page_id": page.id, "error": str(exc)},
            )

    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int | None = None,
        retrieval_query: str | None = None,
        include_global_core: bool = False,
    ) -> ContextPackage:
        self._require_session(session_id)
        t0 = time.perf_counter()
        messages = self.store.list_messages(session_id)
        pages = [p for p in self.store.list_pages(session_id) if p.superseded_by is None]
        if include_global_core:
            global_cores = [
                p for p in self.store.list_global_core_pages() if p.superseded_by is None
            ]
            existing_ids = {p.id for p in pages}
            pages.extend(p for p in global_cores if p.id not in existing_ids)
        effective_budget = (
            min(budget, self.settings.hard_limit)
            if budget is not None
            else self.dynamic_budget.compute(messages, pages, task)
        )
        package = self.context_builder.build(
            session_id=session_id,
            task=task,
            messages=messages,
            pages=pages,
            budget=effective_budget,
            retrieval_query=retrieval_query,
        )
        elapsed = time.perf_counter() - t0
        CONTEXT_BUILD_SECONDS.observe(elapsed)
        CONTEXT_TOKENS.observe(package.estimated_tokens)
        if effective_budget > 0:
            CONTEXT_BUDGET_USED_RATIO.observe(package.estimated_tokens / effective_budget)
        self.trace(
            session_id,
            "context_built",
            {
                "task": task,
                "budget": effective_budget,
                "budget_source": "explicit" if budget is not None else "dynamic",
                "estimated_tokens": package.estimated_tokens,
                "task_tokens": package.task_tokens,
                "task_truncated": package.task_truncated,
                "pinned_core_count": len(package.pinned_core),
                "pinned_core_tokens": sum(
                    self.tokenizer.count(text) for text in package.pinned_core
                ),
                "active_task_pages": [page.model_dump() for page in package.active_task_pages],
                "retrieved_pages": [page.model_dump() for page in package.retrieved_pages],
                "dropped_recent_messages": package.dropped_recent_messages,
                "dropped_pages": [page.model_dump() for page in package.dropped_pages],
            },
        )
        return package

    def search(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        limit: int | None = None,
        include_superseded: bool = False,
    ) -> list[SearchHit]:
        if session_id is None and limit is None:
            limit = 500
        pages = self.store.list_pages(session_id, limit=limit)
        if not include_superseded:
            pages = [p for p in pages if p.superseded_by is None]
        hits = self.searcher.search(pages, query, top_k=top_k)
        RETRIEVAL_HITS.observe(len(hits))
        if session_id is not None:
            self.trace(
                session_id,
                "memory_searched",
                {
                    "query": query,
                    "hits": [{"page_id": hit.page.id, "score": hit.score} for hit in hits],
                },
            )
        return hits

    def commit_patch(self, session_id: str, patch: MemoryPatch) -> MemoryPatch:
        self._require_session(session_id)
        page = self.store.load_page(patch.target_page_id) if patch.target_page_id else None
        if page is not None and page.session_id != session_id:
            patch.errors = ["target page belongs to a different session"]
            patch.verified = False
            self.store.save_patch(patch)
            self.trace(
                session_id,
                "patch_rejected",
                {"patch_id": patch.id, "errors": patch.errors, "conflicts": []},
            )
            return patch
        messages = self.store.list_messages(session_id)
        pages = self.store.list_pages(session_id)
        conflicts = self.conflict_detector.detect(patch, pages)
        verified = self.patch_verifier.verify(patch, page, messages)
        if conflicts:
            conflict_msgs = [
                f"[{c.severity}] {c.reason}: '{c.conflicting_text}'" for c in conflicts
            ]
            verified.errors.extend(conflict_msgs)
            if any(c.severity == "error" for c in conflicts):
                verified.verified = False
        self.store.save_patch(verified)
        self.trace(
            session_id,
            "patch_verified" if verified.verified else "patch_rejected",
            {
                "patch_id": verified.id,
                "errors": verified.errors,
                "conflicts": [
                    {"page_id": c.page_id, "reason": c.reason, "severity": c.severity}
                    for c in conflicts
                ],
            },
        )
        return verified

    def apply_patch(self, session_id: str, patch: MemoryPatch) -> bool:
        """Apply a verified patch to the target page's content. Returns True on success."""
        if not patch.verified:
            return False
        if not patch.target_page_id:
            return False
        page = self.store.load_page(patch.target_page_id)
        if page is None:
            return False
        if page.session_id != session_id:
            return False
        old = patch.old_text or ""
        new = patch.new_text or ""
        if patch.operation in (PatchOperation.REPLACE, PatchOperation.DELETE) and not old:
            return False
        if patch.operation == PatchOperation.ADD and not new:
            return False
        if patch.operation == PatchOperation.REPLACE:
            page.summary = page.summary.replace(old, new)
            page.facts = [f.replace(old, new) for f in page.facts]
            page.decisions = [d.replace(old, new) for d in page.decisions]
            page.open_questions = [q.replace(old, new) for q in page.open_questions]
        elif patch.operation == PatchOperation.ADD:
            page.facts.append(new)
        elif patch.operation == PatchOperation.DELETE:
            page.facts = [f for f in page.facts if old not in f]
            page.decisions = [d for d in page.decisions if old not in d]
            page.open_questions = [q for q in page.open_questions if old not in q]
            page.summary = page.summary.replace(old, "")
        page.version += 1
        page.updated_at = utc_now()
        self.store.update_page(page)
        self._reindex_page_embedding(session_id, page)
        return True

    def _reindex_page_embedding(self, session_id: str, page: MemoryPage) -> None:
        """Recompute embedding for a page after mutation."""
        if self.embedding_client is None:
            return
        text = " ".join(
            [page.title, page.summary] + page.facts + page.decisions + page.open_questions
        )
        try:
            embedding = self.embedding_client.embed(text)
            self.store.set_page_embedding(page.id, embedding)
        except Exception as exc:
            PAGE_ERRORS_TOTAL.labels(stage="embed").inc()
            self.trace(session_id, "embedding_failed", {"page_id": page.id, "error": str(exc)})

    def trace(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.store.add_trace(
            TraceEvent(session_id=session_id, event_type=event_type, payload=payload)
        )

    def _require_session(self, session_id: str) -> None:
        if self.store.get_session(session_id) is None:
            raise ValueError(f"session not found: {session_id}")
