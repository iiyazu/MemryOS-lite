"""Legacy paging system (v1/v2).

This module contains the page/item architecture that is being superseded by
the v3 core-recall-archive + kernel agent system. Preserved as optional
fallback when memoryos_paging_mode != "off".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from memoryos_lite.config import Settings
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.schemas import (
    MemoryItem,
    MemoryItemType,
    MemoryPage,
    MemoryPageDraft,
    Message,
    PageType,
    Role,
)
from memoryos_lite.utils import is_generic_ack


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
        self._use_structured = settings.resolved_llm_provider != "deepseek"
        base_model = ChatOpenAI(
            model=settings.chat_model,
            api_key=SecretStr(api_key),
            base_url=settings.chat_base_url,
            temperature=0,
            timeout=settings.memoryos_llm_timeout_s,
        )
        if self._use_structured:
            self.model = base_model.with_structured_output(MemoryPageDraft)
        else:
            self.model = base_model

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
            pages_block = "\n".join(f"- [{p.id}] {p.title}: {p.summary}" for p in context_pages)
        else:
            pages_block = "None"
        json_instruction = ""
        if not self._use_structured:
            json_instruction = (
                "\n\nRespond with ONLY a JSON object (no markdown fencing) with these fields:\n"
                '{"page_type": "source_summary_page"|"core_profile_page"|"decision_page",'
                ' "title": "...", "summary": "...", "facts": [...], "decisions": [...],'
                ' "open_questions": [...], "discarded_noise": [...],'
                ' "source_message_ids": [...], "confidence": 0.8}\n'
            )
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
            f"{json_instruction}"
        )
        result = self.model.invoke(
            [
                SystemMessage(content=system_content),
                HumanMessage(content=transcript),
            ]
        )
        if self._use_structured:
            if not isinstance(result, MemoryPageDraft):
                raise TypeError("structured output did not return MemoryPageDraft")
        else:
            import json as _json

            raw = result.content if hasattr(result, "content") else str(result)
            data = _json.loads(raw)
            result = MemoryPageDraft(**data)
        # Filter out any hallucinated source IDs
        result.source_message_ids = [sid for sid in result.source_message_ids if sid in known_ids]
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
        recent_limit = max(0, self.settings.recent_message_limit)
        page_messages = (
            messages[:-recent_limit] if recent_limit and len(messages) > recent_limit else messages
        )
        if not page_messages:
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
            if not window:
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

        llm_client = self._llm_client
        if llm_client is None:
            raise RuntimeError("LLM item extraction requires an LLM client")

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
        result = llm_client.invoke([system, human])
        if not isinstance(result, _ItemList):
            raise TypeError("unexpected LLM output type")
        valid_ids = {m.id for m in messages if m.id in set(page.source_message_ids)}
        for item in result.items:
            item.page_id = page.id
            item.session_id = page.session_id
            item.source_message_ids = [sid for sid in item.source_message_ids if sid in valid_ids]
            if not item.source_message_ids:
                item.source_message_ids = self._narrow_source_ids(
                    item.content, messages, page.source_message_ids
                )
        return [it for it in result.items if it.source_message_ids]
