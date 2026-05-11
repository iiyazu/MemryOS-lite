from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from memoryos_lite.config import Settings, get_settings
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
)
from memoryos_lite.store import MemoryStore, create_store
from memoryos_lite.tokenizer import TokenEstimator


@dataclass(frozen=True)
class SearchHit:
    page: MemoryPage
    score: float
    reason: str


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
        for message in page_messages:
            compact = self._compact(message.content)
            if not compact:
                continue
            if message.role == Role.TOOL:
                tool_notes.append(compact)
            elif any(marker in compact for marker in ("决定", "选择", "不做", "不要", "最终")):
                decisions.append(compact)
            elif "?" in compact or "？" in compact or "如何" in compact:
                open_questions.append(compact)
            else:
                facts.append(compact)
        title = self._title(page_messages)
        summary_parts = facts[:3] + decisions[:3] + tool_notes[:2]
        summary = "；".join(summary_parts) if summary_parts else "历史会话片段摘要"
        page_type = (
            PageType.TOOL_OBSERVATION if tool_notes and not facts else PageType.SOURCE_SUMMARY
        )
        if decisions:
            page_type = PageType.DECISION
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
            if page is None:
                errors.append("target page is required")
            elif patch.old_text and patch.old_text not in page.model_dump_json():
                errors.append("old_text does not exist in target page")
        if patch.new_text and any(marker in patch.new_text for marker in self.protected_markers):
            errors.append("new_text attempts to modify protected memory block")
        patch.errors = errors
        patch.verified = not errors
        return patch


class MemorySearcher:
    def __init__(self, tokenizer: TokenEstimator) -> None:
        self.tokenizer = tokenizer

    def search(self, pages: list[MemoryPage], query: str, top_k: int = 5) -> list[SearchHit]:
        query_terms = self._terms(query)
        hits: list[SearchHit] = []
        for page in pages:
            haystack = self._page_text(page)
            page_terms = self._terms(haystack)
            overlap = len(query_terms & page_terms)
            source_bonus = 0.25 if any(term in page.title.lower() for term in query_terms) else 0
            score = overlap + source_bonus
            if score > 0:
                hits.append(SearchHit(page=page, score=score, reason=f"lexical_overlap={overlap}"))
        hits.sort(
            key=lambda hit: (hit.score, hit.page.confidence, hit.page.created_at),
            reverse=True,
        )
        return hits[:top_k]

    def _terms(self, text: str) -> set[str]:
        normalized = text.replace("/", " ").lower()
        terms = {term.strip() for term in normalized.split() if term.strip()}
        cjk_chars = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
        terms.update(cjk_chars)
        terms.update("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:], strict=False))
        return terms

    def _page_text(self, page: MemoryPage) -> str:
        return " ".join(
            [
                page.title,
                page.summary,
                *page.facts,
                *page.decisions,
                *page.open_questions,
            ]
        )


class ContextBuilder:
    def __init__(
        self,
        tokenizer: TokenEstimator,
        searcher: MemorySearcher,
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
    def __init__(self, store: MemoryStore | None = None, settings: Settings | None = None) -> None:
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
        self.searcher = MemorySearcher(self.tokenizer)
        self.context_builder = ContextBuilder(self.tokenizer, self.searcher, self.settings)

    def create_session(self, title: str) -> Any:
        session = self.store.create_session(title)
        self.trace(session.id, "session_created", {"title": title})
        return session

    def ingest(self, session_id: str, request: MessageCreate) -> IngestResponse:
        self._require_session(session_id)
        message = Message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
            token_count=self.tokenizer.count(request.content),
        )
        self.store.add_message(message)
        messages = self.store.list_messages(session_id)
        token_count = sum(item.token_count for item in messages)
        should_page = self.rot_guard.should_page(messages)
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
        messages = self.store.list_messages(session_id)
        if not self.rot_guard.should_page(messages):
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
            self.trace(
                session_id,
                "paging_rejected",
                {"errors": errors, "paging_mode": paging_mode, "paging_error": paging_error},
            )
            return None
        page = MemoryPage(session_id=session_id, **draft.model_dump())
        self.store.save_page(page)
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

    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int,
        retrieval_query: str | None = None,
    ) -> ContextPackage:
        self._require_session(session_id)
        messages = self.store.list_messages(session_id)
        pages = self.store.list_pages(session_id)
        package = self.context_builder.build(
            session_id=session_id,
            task=task,
            messages=messages,
            pages=pages,
            budget=budget,
            retrieval_query=retrieval_query,
        )
        self.trace(
            session_id,
            "context_built",
            {
                "task": task,
                "budget": budget,
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

    def search(self, query: str, top_k: int = 5, session_id: str | None = None) -> list[SearchHit]:
        pages = self.store.list_pages(session_id)
        hits = self.searcher.search(pages, query, top_k=top_k)
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
        messages = self.store.list_messages(session_id)
        verified = self.patch_verifier.verify(patch, page, messages)
        self.store.save_patch(verified)
        self.trace(
            session_id,
            "patch_verified" if verified.verified else "patch_rejected",
            {"patch_id": verified.id, "errors": verified.errors},
        )
        return verified

    def trace(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.store.add_trace(
            TraceEvent(session_id=session_id, event_type=event_type, payload=payload)
        )

    def _require_session(self, session_id: str) -> None:
        if self.store.get_session(session_id) is None:
            raise ValueError(f"session not found: {session_id}")
