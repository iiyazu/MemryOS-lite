"""Conflict detection for memory patches.

Detects when a patch's new content contradicts existing facts or
decisions stored in other memory pages.
"""

from __future__ import annotations

from dataclasses import dataclass

from memoryos_lite.retrieval import LexicalSearcher
from memoryos_lite.schemas import MemoryPage, MemoryPatch, PatchOperation


@dataclass
class Conflict:
    """A detected conflict between a patch and an existing page."""

    page_id: str
    page_title: str
    conflicting_text: str
    reason: str
    severity: str  # "warning" or "error"


# Negation signals that suggest contradiction
_NEGATION_PATTERNS = (
    "不想",
    "不做",
    "不用",
    "取消",
    "放弃",
    "改为",
    "改做",
    "not",
    "don't",
    "won't",
    "cancel",
    "instead of",
    "no longer",
    "changed to",
    "switched to",
    "replaced by",
)


class ConflictDetector:
    """Detects conflicts between a patch and existing memory pages.

    Uses lexical search to find topically related pages, then checks
    for textual contradictions between the patch's new_text and
    existing facts/decisions.
    """

    def __init__(self, searcher: LexicalSearcher | None = None) -> None:
        self.searcher = searcher or LexicalSearcher()

    def detect(
        self,
        patch: MemoryPatch,
        pages: list[MemoryPage],
    ) -> list[Conflict]:
        """Return conflicts found between patch and existing pages."""
        if patch.operation == PatchOperation.ADD and not patch.new_text:
            return []
        if not pages:
            return []

        query = patch.new_text or patch.reason
        if not query.strip():
            return []

        # Find topically related pages via BM25
        target_pages = [p for p in pages if p.id != patch.target_page_id]
        if not target_pages:
            return []

        hits = self.searcher.search(target_pages, query, top_k=5)
        conflicts: list[Conflict] = []

        for hit in hits:
            page_conflicts = self._check_page_conflicts(patch, hit.page)
            conflicts.extend(page_conflicts)

        return conflicts

    def _check_page_conflicts(
        self,
        patch: MemoryPatch,
        page: MemoryPage,
    ) -> list[Conflict]:
        """Check if patch contradicts facts/decisions in a specific page."""
        conflicts: list[Conflict] = []
        new_text = (patch.new_text or "").lower()
        if not new_text:
            return []

        # Check against facts and decisions
        statements = [*page.facts, *page.decisions]
        for statement in statements:
            statement_lower = statement.lower()
            if self._is_contradiction(new_text, statement_lower):
                conflicts.append(
                    Conflict(
                        page_id=page.id,
                        page_title=page.title,
                        conflicting_text=statement,
                        reason=f"patch may contradict existing fact in page '{page.title}'",
                        severity="warning",
                    )
                )

        return conflicts

    def _is_contradiction(self, new_text: str, existing: str) -> bool:
        """Heuristic check for contradiction between two texts.

        Detects cases where:
        1. Both texts discuss the same entity/topic
        2. One contains negation patterns relative to the other
        """
        # Check if new_text contains negation of existing content
        for pattern in _NEGATION_PATTERNS:
            if pattern in new_text:
                # Extract the subject being negated — check if it overlaps with existing
                words_in_existing = set(existing.split())
                words_in_new = set(new_text.split())
                # Significant word overlap (>30%) suggests same topic
                if len(words_in_existing) < 2:
                    continue
                overlap = words_in_existing & words_in_new
                overlap_ratio = len(overlap) / len(words_in_existing)
                if overlap_ratio >= 0.3:
                    return True

        return False
