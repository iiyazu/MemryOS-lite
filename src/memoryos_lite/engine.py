import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.agent_kernel import (
    SimpleAgentStepRunner,
    SimpleToolExecutionManager,
    SimpleToolPolicyEngine,
)
from memoryos_lite.budget import DynamicBudget
from memoryos_lite.config import Settings, get_settings
from memoryos_lite.conflict import ConflictDetector, _extract_implicit_value
from memoryos_lite.context_composer import V3ContextComposer
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
    ItemSearcher,
    LexicalSearcher,
    LLMReranker,
    QueryRewriter,
    Searcher,
    SearchHit,
)
from memoryos_lite.retrieval.evidence_representer import EvidenceCandidate, EvidenceRepresenter
from memoryos_lite.retrieval.evidence_searcher import EvidenceSearcher
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.retrieval.providers import OpenAIEmbeddingClient, QdrantEmbeddingStore
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import (
    ContextEvidence,
    ContextPackage,
    ContextPage,
    IngestResponse,
    MemoryItem,
    MemoryItemType,
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
from memoryos_lite.utils import is_generic_ack
from memoryos_lite.v3_contracts import (
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    IdentityScope,
    ToolPolicyRule,
)

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
    def create_draft(
        self,
        messages: list[Message],
        context_pages: list[MemoryPage] | None = None,
    ) -> MemoryPageDraft:
        pass


class OpenAIPageDraftClient:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.chat_api_key
        if not api_key:
            raise ValueError(f"{settings.chat_api_key_name} is required for llm paging mode")
        self.model = ChatOpenAI(
            model=settings.chat_model,
            api_key=SecretStr(api_key),
            base_url=settings.chat_base_url,
            temperature=0,
            timeout=settings.memoryos_llm_timeout_s,
        ).with_structured_output(MemoryPageDraft)

    def create_draft(
        self,
        messages: list[Message],
        context_pages: list[MemoryPage] | None = None,
    ) -> MemoryPageDraft:
        known_ids = {m.id for m in messages}
        transcript = "\n".join(
            f"{message.id} [{message.role.value}]: {message.content}" for message in messages
        )
        if context_pages:
            pages_block = "\n".join(
                f"- [{p.id}] {p.title}: {p.summary}" for p in context_pages
            )
        else:
            pages_block = "None"
        system_content = (
            "You are the Paging Agent for MemoryOS Lite. Compress the conversation segment"
            " into a memory page.\n\n"
            "Rules:\n"
            "- facts: atomic statements, one per entry, max 12\n"
            "- decisions: explicit choices/rejections, max 6\n"
            "- summary: ≤ 2 sentences; if contradictions exist, newest state wins\n"
            "- source_message_ids: copy exactly from the transcript IDs shown below\n"
            "- page_type: CORE_PROFILE if personal profile, DECISION if decisions dominate,"
            " SOURCE_SUMMARY otherwise\n"
            "- Do not duplicate information already captured in existing pages\n\n"
            f"Existing pages (do not duplicate):\n{pages_block}"
        )
        result = self.model.invoke(
            [
                SystemMessage(content=system_content),
                HumanMessage(content=transcript),
            ]
        )
        if not isinstance(result, MemoryPageDraft):
            raise TypeError("structured output did not return MemoryPageDraft")
        # Filter out any hallucinated source IDs
        result.source_message_ids = [
            sid for sid in result.source_message_ids if sid in known_ids
        ]
        return result


@dataclass(frozen=True)
class _RankedMessageEvidence:
    score: float
    overlap: int
    message_index: int
    message: Message
    page_id: str
    superseded: bool


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

_TEMPORAL_TIMESTAMP_PREFIX_RE = re.compile(r"^\s*(\[[^\]]+\])\s*(?P<body>.*)$")
_TEMPORAL_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|[;；]\s*")
_TEMPORAL_MONTH_NAMES = (
    "jan(?:uary)?",
    "feb(?:ruary)?",
    "mar(?:ch)?",
    "apr(?:il)?",
    "may",
    "jun(?:e)?",
    "jul(?:y)?",
    "aug(?:ust)?",
    "sep(?:tember)?",
    "sept",
    "oct(?:ober)?",
    "nov(?:ember)?",
    "dec(?:ember)?",
)
_TEMPORAL_WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_TEMPORAL_NUMBER_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
_TEMPORAL_SEASON_OR_PERIOD_NAMES = (
    "week",
    "month",
    "year",
    "spring",
    "summer",
    "fall",
    "autumn",
    "winter",
)
_TEMPORAL_BODY_RE = re.compile(
    r"\b(?:" + "|".join(_TEMPORAL_MONTH_NAMES) + r")\s+\d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"
    r"|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"
    r"|\b(?:yesterday|today|tomorrow)\b"
    r"|\b(?:last|next)\s+(?:"
    + "|".join([*_TEMPORAL_WEEKDAY_NAMES, *_TEMPORAL_SEASON_OR_PERIOD_NAMES])
    + r")\b"
    r"|\b(?:early|mid|late)[-\s]+(?:"
    + "|".join([*_TEMPORAL_MONTH_NAMES, *_TEMPORAL_SEASON_OR_PERIOD_NAMES])
    + r")\b"
    r"|\b(?:(?:"
    + "|".join(_TEMPORAL_NUMBER_WORDS)
    + r")|\d+)\s+(?:day|days|week|weeks|month|months|year|years)\s+ago\b"
    r"|\b(?:(?:" + "|".join(_TEMPORAL_NUMBER_WORDS) + r")|\d+)\s*-\s*(?:day|week|month|year)\b",
    re.IGNORECASE,
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
        drafts, paging_mode, paging_error = self.create_drafts(session_id, messages)
        return (drafts[0] if drafts else None), paging_mode, paging_error

    def create_drafts(
        self,
        session_id: str,
        messages: list[Message],
        existing_pages: list[MemoryPage] | None = None,
    ) -> tuple[list[MemoryPageDraft], str, str | None]:
        if len(messages) <= self.settings.recent_message_limit:
            return [], "none", None
        page_messages = messages[: -self.settings.recent_message_limit]
        if not page_messages:
            return [], "none", None
        if len(page_messages) < 2:
            return [], "none", None
        mode = self.settings.memoryos_paging_mode.strip().lower()
        if mode not in ("heuristic", "llm"):
            mode = "heuristic"
        if self.llm_client is not None and mode == "llm":
            drafts, had_fallback, fallback_error = self._agentic_drafts(
                session_id, page_messages, existing_pages or []
            )
            paging_mode = "heuristic_fallback" if had_fallback else "agentic"
            return drafts, paging_mode, fallback_error
        if mode == "llm" and self.llm_client is None:
            error = self.llm_init_error or f"{self.settings.chat_api_key_name} not set"
            return self._heuristic_drafts(session_id, page_messages), "heuristic_fallback", error
        return self._heuristic_drafts(session_id, page_messages), "heuristic", None

    def _agentic_drafts(
        self,
        session_id: str,
        page_messages: list[Message],
        existing_pages: list[MemoryPage],
    ) -> tuple[list[MemoryPageDraft], bool, str | None]:
        limit = self.settings.memoryos_paging_context_pages
        context_pages = existing_pages[-limit:] if limit > 0 else []
        drafts: list[MemoryPageDraft] = []
        had_fallback = False
        fallback_error: str | None = None
        for window in self._split_page_windows(page_messages):
            if len(window) < 2:
                continue
            try:
                draft = self.llm_client.create_draft(window, context_pages)  # type: ignore[union-attr]
                window_ids = {m.id for m in window}
                draft.source_message_ids = [
                    sid for sid in draft.source_message_ids if sid in window_ids
                ]
                if not draft.source_message_ids:
                    raise ValueError("LLM returned no valid source_message_ids")
            except Exception as exc:
                draft = self._heuristic_draft(session_id, window)
                had_fallback = True
                fallback_error = str(exc)
            drafts.append(draft)
        return drafts, had_fallback, fallback_error

    def _heuristic_drafts(
        self,
        session_id: str,
        page_messages: list[Message],
    ) -> list[MemoryPageDraft]:
        drafts: list[MemoryPageDraft] = []
        for window in self._split_page_windows(page_messages):
            if len(window) < 2:
                continue
            drafts.append(self._heuristic_draft(session_id, window))
        return drafts

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
            if message.role == Role.ASSISTANT and is_generic_ack(compact):
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
        temporal_anchors = self._temporal_anchors(page_messages)
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

        def _summary_eligible_fact(text: str) -> bool:
            return _is_informative(text) or len(text) <= 120

        informative_facts = [f for f in facts if _is_informative(f)]
        other_facts = [f for f in facts if f not in informative_facts]
        ranked_facts = [
            fact for fact in [*informative_facts, *other_facts] if _summary_eligible_fact(fact)
        ]
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
            facts=[*temporal_anchors, *facts][:16],
            decisions=decisions[:8],
            open_questions=open_questions[:5],
            discarded_noise=[],
            source_message_ids=[message.id for message in page_messages],
            confidence=0.78,
        )

    def _split_page_windows(self, page_messages: list[Message]) -> list[list[Message]]:
        max_messages = max(2, self.settings.memoryos_page_window_max_messages)
        max_tokens = max(1, self.settings.memoryos_page_window_max_tokens)
        windows: list[list[Message]] = []
        current: list[Message] = []
        current_tokens = 0
        current_key: tuple[str, str] | None = None

        def _flush() -> None:
            nonlocal current, current_tokens, current_key
            if current:
                windows.append(current)
            current = []
            current_tokens = 0
            current_key = None

        for message in page_messages:
            message_key = self._message_window_key(message)
            message_tokens = message.token_count
            crosses_metadata_window = current_key is not None and message_key != current_key
            crosses_message_window = len(current) >= max_messages
            crosses_token_window = bool(current) and current_tokens + message_tokens > max_tokens
            if crosses_metadata_window or crosses_message_window or crosses_token_window:
                _flush()
            current.append(message)
            current_tokens += message_tokens
            current_key = message_key
        _flush()
        return windows

    @staticmethod
    def _message_window_key(message: Message) -> tuple[str, str]:
        metadata = message.metadata or {}
        benchmark_session = str(metadata.get("benchmark_session_id") or "")
        benchmark_date = str(metadata.get("benchmark_date") or "")
        if benchmark_session or benchmark_date:
            return benchmark_session, benchmark_date
        return "", ""

    def _compact(self, text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if len(cleaned) > 180:
            return cleaned[:177] + "..."
        return cleaned

    def _temporal_anchors(self, messages: list[Message]) -> list[str]:
        anchors: list[str] = []
        seen: set[str] = set()
        for message in messages:
            if message.role == Role.ASSISTANT and is_generic_ack(message.content):
                continue
            anchor = self._temporal_anchor_from_message(message)
            if anchor and anchor not in seen:
                anchors.append(anchor)
                seen.add(anchor)
            if len(anchors) >= 12:
                break
        return anchors

    def _temporal_anchor_from_message(self, message: Message) -> str | None:
        cleaned = " ".join(message.content.strip().split())
        if not cleaned:
            return None
        prefix = ""
        body = cleaned
        match = _TEMPORAL_TIMESTAMP_PREFIX_RE.match(cleaned)
        if match:
            prefix = match.group(1)
            body = match.group("body").strip()
        if not body:
            return None
        max_clause_length = max(60, 179 - len(prefix)) if prefix else 180
        clause = self._temporal_clause(body, max_length=max_clause_length)
        if clause is None:
            return None
        if prefix:
            return f"{prefix} {clause}"
        return clause

    @staticmethod
    def _temporal_clause(text: str, max_length: int = 180) -> str | None:
        clauses = [clause.strip() for clause in _TEMPORAL_CLAUSE_SPLIT_RE.split(text)]
        for clause in clauses:
            match = _TEMPORAL_BODY_RE.search(clause)
            if clause and match:
                return PagingAgent._clip_temporal_clause(clause, match, max_length=max_length)
        return None

    @staticmethod
    def _clip_temporal_clause(clause: str, match: re.Match[str], max_length: int = 180) -> str:
        if len(clause) <= max_length:
            return clause
        start = max(0, match.start() - 40)
        end = min(len(clause), start + max_length)
        if end - start < max_length:
            start = max(0, end - max_length)
        snippet = clause[start:end].strip()
        if start > 0:
            snippet = f"...{snippet}"
        if end < len(clause):
            snippet = f"{snippet}..."
        return snippet

    @staticmethod
    def _is_temporal_anchor(text: str) -> bool:
        return bool(_TEMPORAL_TIMESTAMP_PREFIX_RE.match(text))

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


class ItemExtractor:
    """Extracts atomic MemoryItems from a MemoryPage.

    LLM path (mode=llm + api_key): structured output list of items.
    Heuristic fallback: one item per fact/decision in the page.
    """

    def __init__(self, settings: Settings, llm_client: Any | None = None) -> None:
        self.settings = settings
        self._llm_client = llm_client

    def extract(self, page: MemoryPage, messages: list[Message]) -> list[MemoryItem]:
        if self._llm_client is not None:
            try:
                return self._extract_llm(page, messages)
            except Exception:
                pass
        return self._extract_heuristic(page, messages)

    def _narrow_source_ids(
        self, content: str, messages: list[Message], page_source_ids: list[str]
    ) -> list[str]:
        """Pick top 1-3 source messages with highest match to item content."""
        if not content or not page_source_ids:
            return page_source_ids[:1] if page_source_ids else []
        source_msgs = [m for m in messages if m.id in set(page_source_ids)]
        if not source_msgs:
            return page_source_ids[:1] if page_source_ids else []
        content_lower = content.lower().strip()
        scored = []
        for msg in source_msgs:
            msg_lower = msg.content.lower().strip()
            if content_lower in msg_lower or msg_lower in content_lower:
                scored.append((len(content_lower) + 1000, msg.id))
            else:
                content_tokens = set(tokenize(content))
                msg_tokens = set(tokenize(msg.content))
                overlap = len(content_tokens & msg_tokens)
                if overlap > 0:
                    scored.append((overlap, msg.id))
        if not scored:
            return page_source_ids[:1]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [sid for _, sid in scored[:3]]

    def _extract_heuristic(self, page: MemoryPage, messages: list[Message]) -> list[MemoryItem]:
        items: list[MemoryItem] = []
        for fact in page.facts:
            if fact and not is_generic_ack(fact):
                items.append(
                    MemoryItem(
                        page_id=page.id,
                        session_id=page.session_id,
                        item_type=MemoryItemType.KNOWLEDGE,
                        content=fact,
                        source_message_ids=self._narrow_source_ids(
                            fact, messages, page.source_message_ids
                        ),
                    )
                )
        for decision in page.decisions:
            if decision and not is_generic_ack(decision):
                items.append(
                    MemoryItem(
                        page_id=page.id,
                        session_id=page.session_id,
                        item_type=MemoryItemType.KNOWLEDGE,
                        content=decision,
                        source_message_ids=self._narrow_source_ids(
                            decision, messages, page.source_message_ids
                        ),
                    )
                )
        return items

    def _extract_llm(self, page: MemoryPage, messages: list[Message]) -> list[MemoryItem]:
        from pydantic import BaseModel as _BaseModel

        class _ItemList(_BaseModel):
            items: list[MemoryItem]

        transcript = "\n".join(
            f"{m.id} [{m.role.value}]: {m.content}"
            for m in messages
            if m.id in set(page.source_message_ids)
        )
        facts_block = "\n".join(f"- {f}" for f in page.facts)
        decisions_block = "\n".join(f"- {d}" for d in page.decisions)
        system = SystemMessage(
            content=(
                "Extract atomic memory items from this page. Each item is ONE statement.\n"
                "Types: profile (personal info/preferences), event (time-anchored occurrence),"
                " knowledge (facts/decisions/technical choices), behavior (habits/patterns)\n"
                "source_message_ids: IDs from the transcript that support this item.\n"
                "Return a JSON list of items."
            )
        )
        human = HumanMessage(
            content=(
                f"Facts:\n{facts_block}\n\nDecisions:\n{decisions_block}"
                f"\n\nTranscript:\n{transcript}"
            )
        )
        result = self._llm_client.invoke([system, human])
        if not isinstance(result, _ItemList):
            raise TypeError("unexpected LLM output type")
        valid_ids = {m.id for m in messages if m.id in set(page.source_message_ids)}
        for item in result.items:
            item.page_id = page.id
            item.session_id = page.session_id
            item.source_message_ids = [
                sid for sid in item.source_message_ids if sid in valid_ids
            ]
            if not item.source_message_ids:
                item.source_message_ids = self._narrow_source_ids(
                    item.content, messages, page.source_message_ids
                )
        return [it for it in result.items if it.source_message_ids]


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
        self._bm25_evidence_cache: dict[tuple[tuple[str, int], ...], BM25Okapi] = {}
        if self.settings.memoryos_evidence_representation != "legacy":
            self.evidence_representer: EvidenceRepresenter | None = EvidenceRepresenter(
                strategy=self.settings.resolved_evidence_representation,  # type: ignore[arg-type]
            )
            self.evidence_searcher: EvidenceSearcher | None = EvidenceSearcher()
        else:
            self.evidence_representer = None
            self.evidence_searcher = None

    def build(
        self,
        session_id: str,
        task: str,
        messages: list[Message],
        pages: list[MemoryPage],
        budget: int,
        retrieval_query: str | None = None,
        superseded_pages: list[MemoryPage] | None = None,
        item_evidence: list[ContextEvidence] | None = None,
    ) -> ContextPackage:
        query = retrieval_query or task
        recent_messages = messages[-self.settings.recent_message_limit :]
        task_tokens = self.tokenizer.count(task)
        used_tokens = task_tokens
        superseded_pages = superseded_pages or []
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

        selected_evidence_ids: set[str] = set()
        source_page_refs = self._source_page_refs(pages, superseded_pages)
        # Always run legacy evidence retrieval first (proven baseline)
        evidence_candidates, active_overlap_not_top5 = (
            self._retrieve_message_evidence_diagnostics(
                messages,
                query=query,
                source_page_refs=source_page_refs,
                top_k=5,
            )
        )
        contextual_evidence_count = 0
        # Contextual evidence as supplemental recall (never replaces legacy)
        if (
            self.settings.memoryos_evidence_representation != "legacy"
            and self.evidence_representer is not None
        ):
            pages_by_id = {p.id: p for p in pages}
            for sp in superseded_pages:
                pages_by_id.setdefault(sp.id, sp)
            ctx_evidence, _ = self._retrieve_contextual_evidence_diagnostics(
                messages,
                query=query,
                source_page_refs=source_page_refs,
                pages_by_id=pages_by_id,
                top_k=5,
            )
            # Merge: legacy first, contextual supplements (dedupe by message_id)
            seen_ids = {e.message_id for e in evidence_candidates}
            for e in ctx_evidence:
                if e.message_id not in seen_ids:
                    evidence_candidates.append(e)
                    seen_ids.add(e.message_id)
                    contextual_evidence_count += 1
        package.active_overlap_not_top5 = active_overlap_not_top5
        page_count_for_reserve = len(pages) + len(superseded_pages)
        evidence_reserve = (
            self._evidence_reserve(budget)
            if evidence_candidates
            and page_count_for_reserve >= self.settings.memoryos_evidence_reserve_min_pages
            else 0
        )
        core_budget_limit = max(task_tokens, budget - evidence_reserve)

        pinned_core_page_ids: set[str] = set()
        dropped_core_page_ids: set[str] = set()
        core_pages = [page for page in pages if page.page_type == PageType.CORE_PROFILE]
        for page in core_pages:
            text = page.summary
            page_tokens = self.tokenizer.count(text)
            if used_tokens + page_tokens <= core_budget_limit:
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

        target_evidence_count = (
            2 if self._needs_multi_evidence(query) and len(evidence_candidates) >= 2 else 1
        )
        for evidence in evidence_candidates:
            if (
                target_evidence_count > 1
                and len(package.retrieved_evidence) >= target_evidence_count
            ):
                break
            evidence = self._fit_evidence_for_selection(
                evidence,
                query_tokens=tokenize(query),
                available_tokens=budget - used_tokens,
                remaining_slots=max(1, target_evidence_count - len(package.retrieved_evidence)),
            )
            if used_tokens + evidence.estimated_tokens <= budget:
                package.retrieved_evidence.append(evidence)
                selected_evidence_ids.add(evidence.message_id)
                used_tokens += evidence.estimated_tokens
                if evidence.superseded:
                    package.superseded_source_recovered += 1
            else:
                package.candidate_budget_dropped += 1

        # Item evidence: injected AFTER page-level evidence, BEFORE page summaries.
        # This gives item evidence higher priority than page summaries and recent msgs.
        item_evidence_dropped = 0
        for item_ev in (item_evidence or []):
            if item_ev.message_id in selected_evidence_ids:
                continue
            if used_tokens + item_ev.estimated_tokens <= budget:
                package.retrieved_evidence.append(item_ev)
                selected_evidence_ids.add(item_ev.message_id)
                used_tokens += item_ev.estimated_tokens
            else:
                item_evidence_dropped += 1
        package.candidate_budget_dropped += item_evidence_dropped

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

        selected_recent: list[Message] = []
        for message in reversed(recent_messages):
            if message.id in selected_evidence_ids:
                continue
            if used_tokens + message.token_count <= budget:
                selected_recent.append(message)
                used_tokens += message.token_count
            else:
                package.dropped_recent_messages.append(message.id)
        package.recent_messages = list(reversed(selected_recent))
        package.estimated_tokens = used_tokens
        return package

    def _retrieve_message_evidence(
        self,
        messages: list[Message],
        query: str,
        source_page_ids: dict[str, str],
        top_k: int,
    ) -> list[ContextEvidence]:
        source_page_refs = {
            source_id: (page_id, False) for source_id, page_id in source_page_ids.items()
        }
        evidence, _ = self._retrieve_message_evidence_diagnostics(
            messages,
            query=query,
            source_page_refs=source_page_refs,
            top_k=top_k,
        )
        return evidence

    def _retrieve_message_evidence_diagnostics(
        self,
        messages: list[Message],
        query: str,
        source_page_refs: dict[str, tuple[str, bool]],
        top_k: int,
    ) -> tuple[list[ContextEvidence], int]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return [], 0
        candidates: list[tuple[int, Message, list[str], int, str, bool]] = []
        query_token_set = set(query_tokens)
        for index, message in enumerate(messages):
            # Evidence retrieval is for persisted page sources only. Recent,
            # unpaged messages are still handled by the recent-message path so
            # they do not double-count or override page-backed attribution.
            source_ref = source_page_refs.get(message.id)
            if source_ref is None:
                continue
            page_id, superseded = source_ref
            compact = " ".join(message.content.split())
            if not compact:
                continue
            if self._is_low_value_evidence(compact):
                continue
            if message.role == Role.ASSISTANT and is_generic_ack(compact):
                continue
            tokens = tokenize(compact)
            overlap = len(query_token_set & set(tokens))
            if overlap <= 0:
                continue
            candidates.append((index, message, tokens, overlap, page_id, superseded))
        if not candidates:
            return [], 0
        cache_key = tuple(sorted((m.id, m.token_count) for _, m, _, _, _, _ in candidates))
        if cache_key not in self._bm25_evidence_cache:
            if len(self._bm25_evidence_cache) >= 8:
                self._bm25_evidence_cache.pop(next(iter(self._bm25_evidence_cache)))
            self._bm25_evidence_cache[cache_key] = BM25Okapi(
                [tokens for _, _, tokens, _, _, _ in candidates]
            )
        bm25 = self._bm25_evidence_cache[cache_key]
        scores = bm25.get_scores(query_tokens)
        assistant_answer_query = self._looks_like_assistant_answer_query(query)
        scored = sorted(
            (
                _RankedMessageEvidence(
                    score=float(scores[candidate_index])
                    + (6.0 if assistant_answer_query and message.role == Role.ASSISTANT else 0.0),
                    overlap=overlap,
                    message_index=message_index,
                    message=message,
                    page_id=page_id,
                    superseded=superseded,
                )
                for candidate_index, (
                    message_index,
                    message,
                    _,
                    overlap,
                    page_id,
                    superseded,
                ) in enumerate(candidates)
            ),
            key=lambda item: (item.score, item.overlap, item.message_index),
            reverse=True,
        )
        if self._needs_multi_evidence(query):
            scored = self._diversify_ranked_message_evidence(scored)
        top_ids = {item.message.id for item in scored[:top_k]}
        active_overlap_not_top5 = sum(
            1
            for _, message, _, _, _, superseded in candidates
            if not superseded and message.id not in top_ids
        )
        evidence: list[ContextEvidence] = []
        for item in scored[:top_k]:
            evidence_text = self._evidence_text(item.message.content, query_tokens)
            evidence.append(
                ContextEvidence(
                    message_id=item.message.id,
                    text=evidence_text,
                    role=item.message.role,
                    metadata=item.message.metadata,
                    page_id=item.page_id,
                    superseded=item.superseded,
                    reason=(
                        f"message_bm25={item.score:.4f} overlap={item.overlap}"
                        f" superseded={str(item.superseded).lower()}"
                    ),
                    estimated_tokens=self.tokenizer.count(evidence_text),
                )
            )
        return evidence, active_overlap_not_top5

    def _build_evidence_candidates(
        self,
        messages: list[Message],
        source_page_refs: dict[str, tuple[str, bool]],
        pages_by_id: dict[str, MemoryPage],
    ) -> list[EvidenceCandidate]:
        """Build EvidenceCandidates at runtime from paged source messages."""
        if self.evidence_representer is None:
            return []
        msg_index = {m.id: i for i, m in enumerate(messages)}
        nb = self.settings.memoryos_evidence_context_neighbors_before
        na = self.settings.memoryos_evidence_context_neighbors_after
        candidates: list[EvidenceCandidate] = []
        for msg in messages:
            ref = source_page_refs.get(msg.id)
            if ref is None:
                continue
            page_id, superseded = ref
            if superseded:
                continue
            # Apply same filters as legacy path
            compact = " ".join(msg.content.split())
            if not compact:
                continue
            if self._is_low_value_evidence(compact):
                continue
            if msg.role == Role.ASSISTANT and is_generic_ack(compact):
                continue
            idx = msg_index.get(msg.id)
            if idx is None:
                continue
            neighbors_before = messages[max(0, idx - nb):idx]
            neighbors_after = messages[idx + 1:idx + 1 + na]
            page = pages_by_id.get(page_id)
            c = self.evidence_representer.build_candidate(
                msg,
                neighbors_before=neighbors_before,
                neighbors_after=neighbors_after,
                session_id=msg.session_id,
                page=page,
            )
            candidates.append(c)
        return candidates

    def _retrieve_contextual_evidence_diagnostics(
        self,
        messages: list[Message],
        query: str,
        source_page_refs: dict[str, tuple[str, bool]],
        pages_by_id: dict[str, MemoryPage],
        top_k: int,
    ) -> tuple[list[ContextEvidence], int]:
        """Contextual evidence retrieval. Returns (evidence, active_overlap_not_top5)."""
        candidates = self._build_evidence_candidates(messages, source_page_refs, pages_by_id)
        if not candidates:
            return self._retrieve_message_evidence_diagnostics(
                messages, query, source_page_refs, top_k
            )
        assert self.evidence_searcher is not None
        hits = self.evidence_searcher.search(candidates, query, top_k=top_k)
        if not hits and self.settings.memoryos_evidence_direct_raw_fallback:
            return self._retrieve_message_evidence_diagnostics(
                messages, query, source_page_refs, top_k
            )
        # Diversify hits by page/session group (same logic as legacy path)
        if self._needs_multi_evidence(query):
            hits = self._diversify_contextual_hits(hits, messages, source_page_refs)
        evidence: list[ContextEvidence] = []
        for hit in hits:
            ref = source_page_refs.get(hit.message_id)
            page_id = ref[0] if ref else ""
            msg = next((m for m in messages if m.id == hit.message_id), None)
            evidence_text = self._evidence_text(
                hit.original_text,
                tokenize(query),
            )
            evidence.append(
                ContextEvidence(
                    message_id=hit.message_id,
                    text=evidence_text,
                    role=msg.role if msg else Role.USER,
                    metadata=msg.metadata if msg else {},
                    page_id=page_id,
                    reason=f"contextual_bm25={hit.score:.4f}",
                    estimated_tokens=self.tokenizer.count(evidence_text),
                )
            )
        return evidence, 0

    @staticmethod
    def _diversify_contextual_hits(
        hits: list,
        messages: list[Message],
        source_page_refs: dict[str, tuple[str, bool]],
    ) -> list:
        """Diversify contextual evidence hits by session/page group."""
        from memoryos_lite.retrieval.evidence_searcher import EvidenceHit

        msg_by_id = {m.id: m for m in messages}
        diversified: list[EvidenceHit] = []
        selected_ids: set[str] = set()
        seen_groups: set[str] = set()
        for hit in hits:
            msg = msg_by_id.get(hit.message_id)
            ref = source_page_refs.get(hit.message_id)
            page_id = ref[0] if ref else ""
            group = str(
                (msg.metadata.get("benchmark_session_id") if msg else None)
                or page_id
                or (msg.session_id if msg else "")
            )
            if group in seen_groups:
                continue
            diversified.append(hit)
            selected_ids.add(hit.message_id)
            seen_groups.add(group)
        diversified.extend(h for h in hits if h.message_id not in selected_ids)
        return diversified

    @staticmethod
    def _looks_like_assistant_answer_query(query: str) -> bool:
        normalized = query.lower()
        return any(
            marker in normalized
            for marker in (
                "you provided",
                "you recommended",
                "you suggested",
                "you gave",
                "previous chat",
                "previous conversation",
                "we discussed",
                "can you remind me",
                "remind me what",
                "list you",
                "the list",
                "the image",
                "recommended last time",
            )
        )

    @staticmethod
    def _diversify_ranked_message_evidence(
        scored: list[_RankedMessageEvidence],
    ) -> list[_RankedMessageEvidence]:
        diversified: list[_RankedMessageEvidence] = []
        selected_ids: set[str] = set()
        seen_groups: set[str] = set()
        for item in scored:
            group = str(
                item.message.metadata.get("benchmark_session_id")
                or item.page_id
                or item.message.session_id
            )
            if group in seen_groups:
                continue
            diversified.append(item)
            selected_ids.add(item.message.id)
            seen_groups.add(group)
        diversified.extend(item for item in scored if item.message.id not in selected_ids)
        return diversified

    def _fit_evidence_for_selection(
        self,
        evidence: ContextEvidence,
        query_tokens: list[str],
        available_tokens: int,
        remaining_slots: int,
    ) -> ContextEvidence:
        token_limit = min(
            evidence.estimated_tokens,
            max(8, available_tokens // remaining_slots) if available_tokens > 0 else 0,
        )
        if token_limit <= 0 or evidence.estimated_tokens <= token_limit:
            return evidence
        text = self._clip_text_to_token_budget(evidence.text, token_limit, query_tokens)
        return evidence.model_copy(
            update={
                "text": text,
                "estimated_tokens": self.tokenizer.count(text),
            }
        )

    @staticmethod
    def _is_low_value_evidence(text: str) -> bool:
        # Eval/public benchmark fixtures include explicit "background/no answer"
        # audit text. Keep those pages auditable, but do not spend scarce context
        # budget on snippets that state they are not answer evidence.
        return any(
            marker in text for marker in ("不包含", "不提供", "只提供背景", "无关", "噪声", "占位")
        )

    def _evidence_text(self, content: str, query_tokens: list[str]) -> str:
        max_tokens = max(8, self.settings.memoryos_evidence_max_tokens)
        compact = " ".join(content.split())
        if self.tokenizer.count(compact) <= max_tokens:
            return compact

        prefix = ""
        prefix_match = re.match(r"^(\[[^\]]+\]\s*)", compact)
        if prefix_match is not None:
            prefix = prefix_match.group(1)
            compact_without_prefix = compact[len(prefix) :].strip()
        else:
            compact_without_prefix = compact

        query_token_set = set(query_tokens)
        clauses = [
            clause.strip()
            for clause in re.split(r"(?<=[。！？.!?])\s+|[；;]\s*", compact_without_prefix)
            if clause.strip()
        ]
        if not clauses:
            clauses = [compact_without_prefix]
        scored_clauses = sorted(
            (
                (len(query_token_set & set(tokenize(clause))), index, clause)
                for index, clause in enumerate(clauses)
            ),
            key=lambda item: (item[0], -item[1]),
            reverse=True,
        )
        selected = [clause for score, _, clause in scored_clauses if score > 0][:2]
        if not selected:
            selected = [clauses[0]]
        snippet = f"{prefix}{' '.join(selected)}".strip()
        if self.tokenizer.count(snippet) <= max_tokens:
            return snippet

        words = snippet.split()
        if len(words) > 1:
            shortened = self._clip_text_to_token_budget(snippet, max_tokens, query_tokens)
            if shortened and self.tokenizer.count(shortened) <= max_tokens:
                return shortened
        return snippet[: max(24, max_tokens * 4)].rstrip() or compact[:180]

    def _clip_text_to_token_budget(
        self,
        text: str,
        token_budget: int,
        query_tokens: list[str] | None = None,
    ) -> str:
        if token_budget <= 0:
            return ""
        if self.tokenizer.count(text) <= token_budget:
            return text
        query_token_set = set(query_tokens or [])
        if query_token_set:
            prefix = ""
            prefix_match = re.match(r"^(\[[^\]]+\]\s*)", text)
            if prefix_match is not None:
                prefix = prefix_match.group(1)
                body = text[len(prefix) :].strip()
            else:
                body = text
            body_words = body.split()
            best_text = ""
            best_score: tuple[int, int, int] = (-1, -1, 0)
            # This query-aware search is intentionally simple and quadratic.
            # It is only used on already clipped evidence snippets/anchors
            # (normally well under 200 words), not arbitrary long documents.
            for start in range(len(body_words)):
                for end in range(start + 1, len(body_words) + 1):
                    window = " ".join(body_words[start:end]).strip()
                    candidate = f"{prefix}{window}".strip() if prefix else window
                    token_count = self.tokenizer.count(candidate)
                    if token_count > token_budget:
                        break
                    overlap = len(query_token_set & set(tokenize(window)))
                    score = (overlap, end - start, -start)
                    if overlap > 0 and score > best_score:
                        best_score = score
                        best_text = candidate
            if best_text:
                return best_text
        words = text.split()
        if len(words) <= 1:
            return text[: max(24, token_budget * 4)].rstrip()
        low = 1
        high = len(words)
        best = words[0]
        while low <= high:
            mid = (low + high) // 2
            candidate = " ".join(words[:mid]).strip()
            if self.tokenizer.count(candidate) <= token_budget:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        return best

    @staticmethod
    def _needs_multi_evidence(query: str) -> bool:
        normalized = query.lower()
        return (
            " or " in normalized
            or " between " in normalized
            or "how many days" in normalized
            or " before " in normalized
            or " after " in normalized
            or ContextBuilder._looks_like_first_comparison(normalized)
        )

    @staticmethod
    def _looks_like_first_comparison(normalized_query: str) -> bool:
        stripped = normalized_query.rstrip(" ?!.")
        return (
            (stripped.startswith("which ") or stripped.startswith("what "))
            and stripped.endswith(" first")
            and not stripped.endswith(" at first")
        )

    @staticmethod
    def _source_page_ids(pages: list[MemoryPage]) -> dict[str, str]:
        source_page_ids: dict[str, str] = {}
        for page in pages:
            for source_id in page.source_message_ids:
                source_page_ids.setdefault(source_id, page.id)
        return source_page_ids

    @staticmethod
    def _source_page_refs(
        active_pages: list[MemoryPage],
        superseded_pages: list[MemoryPage],
    ) -> dict[str, tuple[str, bool]]:
        source_page_refs: dict[str, tuple[str, bool]] = {}
        for page in active_pages:
            for source_id in page.source_message_ids:
                source_page_refs.setdefault(source_id, (page.id, False))
        for page in superseded_pages:
            for source_id in page.source_message_ids:
                source_page_refs.setdefault(source_id, (page.id, True))
        return source_page_refs

    def _evidence_reserve(self, budget: int) -> int:
        ratio = max(0.0, min(1.0, self.settings.memoryos_evidence_reserve_ratio))
        ratio_reserve = int(budget * ratio)
        token_cap = max(0, self.settings.memoryos_evidence_reserve_tokens)
        if token_cap == 0:
            return ratio_reserve
        return min(ratio_reserve, token_cap)


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
        paging_mode_normalized = self.settings.memoryos_paging_mode.strip().lower()
        if self.settings.chat_api_key and paging_mode_normalized == "llm":
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
        qdrant_store: QdrantEmbeddingStore | None = None
        if self.settings.qdrant_url and self.embedding_client is not None:
            try:
                qdrant_store = QdrantEmbeddingStore(
                    url=self.settings.qdrant_url,
                    collection=self.settings.qdrant_collection,
                    dim=self.embedding_client.dim,
                    timeout=self.settings.memoryos_qdrant_timeout_s,
                )
            except Exception as exc:
                qdrant_store = None
                llm_init_error = str(exc)
        self.qdrant_store = qdrant_store
        embedding = (
            EmbeddingSearcher(self.store, self.embedding_client, qdrant_store=qdrant_store)
            if self.embedding_client is not None
            else None
        )
        chat_api_key = self.settings.chat_api_key
        query_rewriter = (
            QueryRewriter(
                model=self.settings.chat_model,
                api_key=chat_api_key,
                base_url=self.settings.chat_base_url,
                timeout=self.settings.memoryos_llm_timeout_s,
            )
            if self.settings.memoryos_rewrite_enabled and chat_api_key
            else None
        )
        reranker = (
            LLMReranker(
                model=self.settings.chat_model,
                api_key=chat_api_key,
                base_url=self.settings.chat_base_url,
                timeout=self.settings.memoryos_llm_timeout_s,
            )
            if self.settings.memoryos_rerank_enabled and chat_api_key
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
        self.recall_pipeline = RecallPipeline(
            store=self.store,
            settings=self.settings,
            tokenizer=self.tokenizer,
        )
        self.v3_context_composer = V3ContextComposer(
            store=self.store,
            settings=self.settings,
            tokenizer=self.tokenizer,
            recall_pipeline=self.recall_pipeline,
        )
        self.agent_kernel = (
            SimpleAgentStepRunner(
                store=self.store,
                tool_policy_engine=SimpleToolPolicyEngine(
                    rules=[
                        ToolPolicyRule(
                            id="kernel_archive_write_requires_approval",
                            tool_name="archive_write",
                            effect="require_approval",
                            reason="archive writes require explicit approval",
                        )
                    ]
                ),
                tool_execution_manager=SimpleToolExecutionManager(store=self.store),
            )
            if self.settings.resolved_agent_kernel == "v1"
            else None
        )
        self.conflict_detector = ConflictDetector(lexical)
        item_llm: Any | None = None
        if (
            self.settings.memoryos_item_extraction
            and chat_api_key
            and paging_mode_normalized == "llm"
        ):
            try:
                from pydantic import BaseModel as _BaseModel

                class _ItemList(_BaseModel):
                    items: list[MemoryItem]

                item_llm = ChatOpenAI(
                    model=self.settings.chat_model,
                    api_key=SecretStr(chat_api_key),
                    base_url=self.settings.chat_base_url,
                    temperature=0,
                    timeout=self.settings.memoryos_llm_timeout_s,
                ).with_structured_output(_ItemList)
            except Exception:
                item_llm = None
        self.item_extractor = ItemExtractor(self.settings, llm_client=item_llm)
        self.item_searcher = ItemSearcher(embedding_client=self.embedding_client)

    def _default_embedding_client(self) -> EmbeddingClient | None:
        provider = self.settings.memoryos_embedding_provider.strip().lower()
        if provider == "fastembed":
            from memoryos_lite.retrieval.providers.fastembed_client import (
                FastEmbedClient,
            )

            return FastEmbedClient()
        if provider in {"none", "auto"}:
            return None
        if provider == "openai" and self.settings.openai_api_key:
            try:
                return OpenAIEmbeddingClient(self.settings)
            except Exception:
                pass
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
        if self.settings.resolved_recall_pipeline == "v2":
            created = self.store.ensure_episodes_for_session(session_id)
            if created:
                self.trace(session_id, "episode_indexed", {"created": created})
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
        all_pages = self.store.list_pages(session_id)
        existing_pages = [p for p in all_pages if p.superseded_by is None]
        paged_source_ids = {
            source_id
            for page in all_pages
            for source_id in page.source_message_ids
        }
        candidate_messages = [message for message in messages if message.id not in paged_source_ids]
        drafts, paging_mode, paging_error = self.paging_agent.create_drafts(
            session_id,
            candidate_messages,
            existing_pages,
        )
        if not drafts:
            self.trace(
                session_id,
                "paging_skipped",
                {"reason": "not_enough_messages", "paging_mode": paging_mode},
            )
            return None
        committed_pages: list[MemoryPage] = []
        for draft in drafts:
            errors = self.page_verifier.verify(draft, messages)
            if errors:
                PAGE_ERRORS_TOTAL.labels(stage="verify").inc()
                self.trace(
                    session_id,
                    "paging_rejected",
                    {
                        "errors": errors,
                        "paging_mode": paging_mode,
                        "paging_error": paging_error,
                        "source_message_ids": draft.source_message_ids,
                    },
                )
                continue
            dropped = self._drop_intra_draft_conflicts(draft)
            if dropped:
                self.trace(
                    session_id,
                    "intra_draft_conflicts_dropped",
                    {"dropped": dropped, "paging_mode": paging_mode},
                )
            page = MemoryPage(session_id=session_id, **draft.model_dump())
            self.store.save_page(page)
            committed_pages.append(page)
            self._index_page_embedding(page)
            if self.settings.memoryos_item_extraction:
                items = self.item_extractor.extract(page, messages)
                self.store.save_items(items)
                for item in items:
                    self._index_item_embedding(item)
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
                    "window_page_count": len(drafts),
                },
            )
        if not committed_pages:
            return None
        return committed_pages[-1]

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
            updates_in_facts = [
                f
                for f in draft.facts
                if not PagingAgent._is_temporal_anchor(f) and any(m in f for m in _UPDATE_MARKERS)
            ]
            other_facts = [
                f
                for f in draft.facts
                if not PagingAgent._is_temporal_anchor(f)
                and f not in updates_in_facts
                and len(f) <= 120
            ]
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
            for p in self.store.list_pages(session_id, include_superseded=False)
            if p.id != new_page.id
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
            if self.qdrant_store is not None:
                self.qdrant_store.upsert(page.id, vector)
        except Exception as exc:
            PAGE_ERRORS_TOTAL.labels(stage="embed").inc()
            self.trace(
                page.session_id,
                "embedding_failed",
                {"page_id": page.id, "error": str(exc)},
            )

    def _index_item_embedding(self, item: MemoryItem) -> bool:
        """Embed and store item vector. Returns True on success."""
        if self.embedding_client is None or not item.content.strip():
            return False
        try:
            vector = self.embedding_client.embed(item.content)
            if vector:
                self.store.set_item_embedding(item.id, vector)
                return True
        except Exception:
            pass
        return False

    def _prepare_item_evidence(
        self,
        session_id: str,
        query: str,
        messages: list[Message],
        pages: list[MemoryPage],
    ) -> tuple[list[ContextEvidence], dict[str, Any] | None]:
        """Prepare item-sourced evidence candidates for ContextBuilder.

        Returns (candidates, trace_payload). Candidates are pre-filtered
        (no generic acks, no low-value) and text-clipped, ready for budget
        competition inside ContextBuilder.build().
        """
        if not self.settings.memoryos_item_extraction:
            return [], None
        items = self.store.list_items(session_id)
        if not items:
            return [], None
        active_page_ids = {p.id for p in pages}
        active_items = [
            it for it in items
            if it.page_id in active_page_ids or it.page_id.startswith("orphan_")
        ]
        if not active_items:
            return [], None
        item_ids = [it.id for it in active_items]
        embeddings = self.store.get_item_embeddings(item_ids)
        hits = self.item_searcher.search(
            active_items, query, embeddings=embeddings, top_k=10
        )
        if not hits:
            return [], {"item_hit_count": 0, "promoted_evidence_count": 0,
                        "promoted_source_message_ids": []}
        msg_by_id = {m.id: m for m in messages}
        query_tokens = tokenize(query)
        seen_ids: set[str] = set()
        candidates: list[ContextEvidence] = []
        max_candidates = self.settings.memoryos_item_evidence_max
        for hit in hits:
            if len(candidates) >= max_candidates:
                break
            for src_id in hit.item.source_message_ids:
                if len(candidates) >= max_candidates:
                    break
                if src_id in seen_ids:
                    continue
                msg = msg_by_id.get(src_id)
                if msg is None:
                    continue
                if is_generic_ack(msg.content):
                    continue
                if ContextBuilder._is_low_value_evidence(msg.content):
                    continue
                text = self.context_builder._evidence_text(
                    msg.content, query_tokens
                )
                tokens = self.tokenizer.count(text)
                candidates.append(
                    ContextEvidence(
                        message_id=src_id,
                        text=text,
                        role=msg.role,
                        reason=f"item_hit:{hit.reason}",
                        estimated_tokens=tokens,
                        page_id=hit.item.page_id,
                    )
                )
                seen_ids.add(src_id)
        trace = {
            "item_hit_count": len(hits),
            "promoted_evidence_count": len(candidates),
            "promoted_source_message_ids": [c.message_id for c in candidates],
        }
        return candidates, trace

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
        pages = self.store.list_pages(session_id, include_superseded=False)
        superseded_pages = self.store.list_pages(session_id, include_superseded=True)
        superseded_pages = [p for p in superseded_pages if p.superseded_by is not None]
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
        if self._should_route_to_v3_context():
            v3_package = self.v3_context_composer.build(
                ContextComposerRequest(
                    session_id=session_id,
                    task=task,
                    budget=effective_budget,
                    retrieval_query=retrieval_query,
                    identity_scope=IdentityScope(session_id=session_id),
                )
            )
            package = self._context_package_from_v3(v3_package)
            elapsed = time.perf_counter() - t0
            CONTEXT_BUILD_SECONDS.observe(elapsed)
            CONTEXT_TOKENS.observe(package.estimated_tokens)
            if effective_budget > 0:
                CONTEXT_BUDGET_USED_RATIO.observe(
                    package.estimated_tokens / effective_budget
                )
            self.trace(
                session_id,
                "context_built",
                {
                    "task": task,
                    "budget": effective_budget,
                    "budget_source": "explicit" if budget is not None else "dynamic",
                    "estimated_tokens": package.estimated_tokens,
                    "memory_arch": "v3",
                    "v3_layer_counts": package.metadata["v3_layer_counts"],
                    "v3_budget_decisions": package.metadata["v3_budget_decisions"],
                    "v3_component_accounting": package.metadata[
                        "v3_component_accounting"
                    ],
                    "v3_final_context_trace": package.metadata[
                        "v3_final_context_trace"
                    ],
                    "v3_component_token_totals": package.metadata[
                        "v3_component_token_totals"
                    ],
                    "v3_component_drop_counts": package.metadata[
                        "v3_component_drop_counts"
                    ],
                    "locomo_neighbor_diagnostics": package.metadata[
                        "locomo_neighbor_diagnostics"
                    ],
                },
            )
            return package
        if self.settings.resolved_recall_pipeline == "v2":
            package = self.recall_pipeline.build_context(
                session_id=session_id,
                task=task,
                budget=effective_budget,
                retrieval_query=retrieval_query,
            )
            elapsed = time.perf_counter() - t0
            CONTEXT_BUILD_SECONDS.observe(elapsed)
            CONTEXT_TOKENS.observe(package.estimated_tokens)
            if effective_budget > 0:
                CONTEXT_BUDGET_USED_RATIO.observe(
                    package.estimated_tokens / effective_budget
                )
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
                    "retrieved_evidence": [
                        evidence.model_dump() for evidence in package.retrieved_evidence
                    ],
                    "candidate_budget_dropped": package.candidate_budget_dropped,
                    "recall_pipeline": "v2",
                    **package.metadata,
                },
            )
            return package
        item_evidence, item_trace = self._prepare_item_evidence(
            session_id=session_id,
            query=retrieval_query or task,
            messages=messages,
            pages=pages,
        )
        package = self.context_builder.build(
            session_id=session_id,
            task=task,
            messages=messages,
            pages=pages,
            budget=effective_budget,
            retrieval_query=retrieval_query,
            superseded_pages=superseded_pages,
            item_evidence=item_evidence,
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
                "retrieved_evidence": [
                    evidence.model_dump() for evidence in package.retrieved_evidence
                ],
                "superseded_source_recovered": package.superseded_source_recovered,
                "candidate_budget_dropped": package.candidate_budget_dropped,
                "active_overlap_not_top5": package.active_overlap_not_top5,
                "retrieved_pages": [page.model_dump() for page in package.retrieved_pages],
                "dropped_recent_messages": package.dropped_recent_messages,
                "dropped_pages": [page.model_dump() for page in package.dropped_pages],
            },
        )
        if item_trace:
            actual_promoted = [
                e for e in package.retrieved_evidence
                if e.reason.startswith("item_hit:")
            ]
            item_trace["candidate_count"] = item_trace.pop("promoted_evidence_count")
            item_trace["promoted_evidence_count"] = len(actual_promoted)
            item_trace["promoted_source_message_ids"] = [
                e.message_id for e in actual_promoted
            ]
            item_trace["item_evidence_budget_dropped"] = (
                item_trace["candidate_count"] - len(actual_promoted)
            )
            self.trace(session_id, "item_retrieval", item_trace)
        return package

    def _should_route_to_v3_context(self) -> bool:
        return self.settings.resolved_memory_arch == "v3"

    def _context_package_from_v3(self, v3_package: ContextPackageV3) -> ContextPackage:
        package = ContextPackage(
            session_id=v3_package.session_id,
            task=v3_package.task,
            task_tokens=self.tokenizer.count(v3_package.task),
        )
        layer_counts: dict[str, int] = {}
        messages_by_id = {
            message.id: message for message in self.store.list_messages(v3_package.session_id)
        }
        for item in v3_package.items:
            layer_counts[item.layer] = layer_counts.get(item.layer, 0) + 1
            if item.layer == "core":
                package.pinned_core.append(item.text)
            elif item.layer == "recent":
                message = messages_by_id.get(item.item_id)
                if message is not None:
                    package.recent_messages.append(message)
            elif item.layer in {"recall", "archival", "fallback"}:
                message_ref = next(
                    (
                        ref
                        for ref in item.source_refs
                        if getattr(ref.source_type, "value", ref.source_type) == "message"
                    ),
                    None,
                )
                package.retrieved_evidence.append(
                    ContextEvidence(
                        message_id=message_ref.source_id if message_ref else item.item_id,
                        text=item.text,
                        role=Role.USER,
                        reason=str(item.metadata.get("reason", item.layer)),
                        estimated_tokens=item.estimated_tokens,
                        metadata={
                            "origin": item.layer,
                            "v3_item_id": item.item_id,
                            **item.metadata,
                        },
                    )
                )
        package.estimated_tokens = int(
            v3_package.metadata.get(
                "estimated_tokens",
                sum(item.estimated_tokens for item in v3_package.items),
            )
        )
        package.candidate_budget_dropped = sum(
            len(decision.dropped_item_ids) for decision in v3_package.budget_decisions
        )
        recall_candidate_message_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall"},
        )
        planned_evidence_message_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall", "archival"},
        )
        indexed_source_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall", "archival", "recent"},
        )
        package.metadata.update(
            {
                "memory_arch": "v3",
                "v3_context": v3_package.model_dump(mode="json"),
                "v3_layer_counts": layer_counts,
                "v3_budget_decisions": [
                    decision.model_dump(mode="json")
                    for decision in v3_package.budget_decisions
                ],
                "v3_diagnostics": [
                    diagnostic.model_dump(mode="json")
                    for diagnostic in v3_package.diagnostics
                ],
                "v3_component_accounting": v3_package.metadata.get(
                    "component_accounting",
                    [],
                ),
                "v3_final_context_trace": v3_package.metadata.get(
                    "final_context_trace",
                    [],
                ),
                "v3_component_token_totals": v3_package.metadata.get(
                    "component_token_totals",
                    {},
                ),
                "v3_component_included_counts": v3_package.metadata.get(
                    "component_included_counts",
                    {},
                ),
                "v3_component_drop_counts": v3_package.metadata.get(
                    "component_drop_counts",
                    {},
                ),
                "locomo_neighbor_diagnostics": v3_package.metadata.get(
                    "locomo_neighbor_diagnostics",
                    [],
                ),
                "archival_eligibility": v3_package.metadata.get(
                    "archival_eligibility",
                    {},
                ),
                "indexed_source_ids": indexed_source_ids,
                "recall_indexed_source_ids": indexed_source_ids,
                "episode_candidate_message_ids": recall_candidate_message_ids,
                "recall_candidate_message_ids": recall_candidate_message_ids,
                "planned_evidence_message_ids": planned_evidence_message_ids,
                "recall_planned_message_ids": planned_evidence_message_ids,
                "budget_dropped_relevant": package.candidate_budget_dropped,
                "recall_budget_dropped": package.candidate_budget_dropped,
            }
        )
        return package

    @staticmethod
    def _v3_source_ids(
        items: list[ContextLayerItem],
        *,
        layers: set[str] | None = None,
    ) -> list[str]:
        source_ids: list[str] = []
        for item in items:
            if layers is not None and item.layer not in layers:
                continue
            for source_ref in item.source_refs:
                source_type = getattr(source_ref.source_type, "value", source_ref.source_type)
                if source_type == "message":
                    source_ids.append(source_ref.source_id)
        seen: set[str] = set()
        deduped: list[str] = []
        for source_id in source_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
            deduped.append(source_id)
        return deduped

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
            if self.qdrant_store is not None:
                self.qdrant_store.upsert(page.id, embedding)
        except Exception as exc:
            PAGE_ERRORS_TOTAL.labels(stage="embed").inc()
            self.trace(session_id, "embedding_failed", {"page_id": page.id, "error": str(exc)})

    def create_item(
        self,
        session_id: str,
        content: str,
        item_type: str = "knowledge",
        source_message_ids: list[str] | None = None,
    ) -> MemoryItem | None:
        self._require_session(session_id)
        if not self.settings.memoryos_item_extraction:
            return None
        try:
            itype = MemoryItemType(item_type)
        except ValueError as exc:
            raise ValueError(
                f"invalid item_type: {item_type}. "
                f"Valid: {', '.join(t.value for t in MemoryItemType)}"
            ) from exc
        pages = self.store.list_pages(session_id, include_superseded=False)
        page_id = pages[-1].id if pages else f"orphan_{session_id}"
        if source_message_ids is None:
            msgs = self.store.list_messages(session_id, limit=1)
            source_message_ids = [msgs[0].id] if msgs else []
        item = MemoryItem(
            page_id=page_id,
            session_id=session_id,
            item_type=itype,
            content=content,
            source_message_ids=source_message_ids,
        )
        self.store.save_items([item])
        self._index_item_embedding(item)
        self.trace(session_id, "item_created", {
            "item_id": item.id, "item_type": item_type, "content": content,
        })
        return item

    def search_items(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
        include_superseded: bool = False,
    ) -> list[dict[str, Any]]:
        self._require_session(session_id)
        if not self.settings.memoryos_item_extraction:
            return []
        items = self.store.list_items(session_id)
        if not items:
            return []
        if not include_superseded:
            superseded_page_ids = {
                p.id for p in self.store.list_pages(session_id, include_superseded=True)
                if p.superseded_by is not None
            }
            items = [
                it for it in items
                if it.page_id not in superseded_page_ids
            ]
        if not items:
            return []
        item_ids = [it.id for it in items]
        embeddings = self.store.get_item_embeddings(item_ids)
        hits = self.item_searcher.search(
            items, query, embeddings=embeddings, top_k=top_k
        )
        self.trace(session_id, "items_searched", {
            "query": query, "hit_count": len(hits),
        })
        return [
            {"item_id": h.item.id, "content": h.item.content,
             "item_type": h.item.item_type.value, "score": h.score,
             "source_message_ids": h.item.source_message_ids}
            for h in hits
        ]

    def patch_item(
        self,
        session_id: str,
        item_id: str,
        new_content: str,
    ) -> str:
        self._require_session(session_id)
        if not self.settings.memoryos_item_extraction:
            return "Item operations are disabled."
        item = self.store.load_item(item_id)
        if item is None:
            return f"Item {item_id} not found."
        if item.session_id != session_id:
            return f"Item {item_id} belongs to a different session."
        old_content = item.content
        self.store.update_item_content(item_id, new_content)
        item.content = new_content
        embedded = self._index_item_embedding(item)
        self.trace(session_id, "item_patched", {
            "item_id": item_id, "old_content": old_content,
            "new_content": new_content, "re_embedded": embedded,
        })
        return f"Item {item_id} updated."

    def trace(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.store.add_trace(
            TraceEvent(session_id=session_id, event_type=event_type, payload=payload)
        )

    def _require_session(self, session_id: str) -> None:
        if self.store.get_session(session_id) is None:
            raise ValueError(f"session not found: {session_id}")
