from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memoryos_lite.schemas import MemoryPage, Message

EvidenceStrategy = Literal["raw", "deterministic_context", "page_context_plus_raw"]
NEIGHBOR_TRUNCATE = 100


@dataclass(frozen=True)
class EvidenceCandidate:
    message_id: str
    original_text: str
    index_text: str
    display_text: str
    page_id: str | None = None
    metadata: dict | None = None


class EvidenceRepresenter:
    def __init__(self, strategy: EvidenceStrategy = "deterministic_context") -> None:
        valid: set[str] = {"raw", "deterministic_context", "page_context_plus_raw"}
        if strategy not in valid:
            raise ValueError(f"Unknown evidence strategy {strategy!r}. Valid: {sorted(valid)}")
        self._strategy = strategy

    @property
    def strategy(self) -> EvidenceStrategy:
        return self._strategy

    def build_candidate(
        self,
        message: Message,
        neighbors_before: list[Message],
        neighbors_after: list[Message],
        session_id: str = "",
        page: MemoryPage | None = None,
    ) -> EvidenceCandidate:
        original = message.content
        if self._strategy == "raw":
            index_text = original
        elif self._strategy == "deterministic_context":
            index_text = self._deterministic(
                message, neighbors_before, neighbors_after, session_id, page
            )
        elif self._strategy == "page_context_plus_raw":
            index_text = self._page_context_plus_raw(message, page)
        else:
            index_text = original
        return EvidenceCandidate(
            message_id=message.id,
            original_text=original,
            index_text=index_text,
            display_text=original,
            page_id=page.id if page else None,
        )

    def _deterministic(self, message, neighbors_before, neighbors_after, session_id, page):
        parts: list[str] = []
        header = f"[session={session_id}, speaker={message.role.value}"
        if page:
            header += f", page={page.title}"
        header += "]"
        parts.append(header)
        if neighbors_before:
            prev_texts = [m.content[:NEIGHBOR_TRUNCATE] for m in neighbors_before[-2:]]
            parts.append("Previous: " + " | ".join(prev_texts))
        parts.append("Current: " + message.content)
        if neighbors_after:
            next_texts = [m.content[:NEIGHBOR_TRUNCATE] for m in neighbors_after[:1]]
            parts.append("Next: " + " | ".join(next_texts))
        return "\n".join(parts)

    def _page_context_plus_raw(self, message, page):
        parts: list[str] = []
        if page:
            parts.append(f"[page={page.title}]")
            parts.append(page.summary[:200])
        parts.append(message.content)
        return "\n".join(parts)
