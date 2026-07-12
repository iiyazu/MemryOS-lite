"""Conflict detection for memory patches.

Detects when a patch's new content contradicts existing facts or decisions
stored in other memory pages. Two detection paths run in order:

1. **Slot extraction** — parses ``{subject}{transition_verb}{value}`` templates
   (数据库选 PostgreSQL / 数据库改用 MySQL, "user picks Java" / "user picks
   Kotlin" …). If two statements share a subject but have different values,
   they contradict — no negation word required. This is what lets the detector
   catch "PostgreSQL → MySQL" swaps that the old negation heuristic missed.

2. **Negation heuristic** — fallback for explicit "X no longer does Y" style
   updates (e.g. "用户不想做 Runbook Oncall Agent" against "用户想做 Runbook
   Oncall Agent"). Kept for backward compatibility with existing callers.
"""

from __future__ import annotations

import re
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


# Negation signals that suggest contradiction.
_NEGATION_PATTERNS: tuple[str, ...] = (
    "不想",
    "不做",
    "不用",
    "取消",
    "放弃",
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


# Transition verbs that mark "{subject} {verb} {value}" — a slot assignment.
# Ordered longest-first so greedy matching picks specific multi-char forms
# ("切换到" before "切", "改用" before "用") and short single-char verbs
# only fire when no longer form applies.
_TRANSITION_VERBS: tuple[str, ...] = (
    # Chinese — multi-char
    "最终确定",
    "最终换",
    "切换到",
    "切换成",
    "调整到",
    "调整为",
    "升级到",
    "升级为",
    "迁移到",
    "搬到",
    "搬去",
    "搬往",
    "住在",
    "位于",
    "改用",
    "改为",
    "改成",
    "换成",
    "换为",
    "选用",
    "选择",
    "采用",
    "定为",
    "定在",
    "降到",
    "降为",
    "升到",
    "升为",
    "确定",
    "选",
    "用",
    "换",
    # English
    "switched to",
    "changed to",
    "moved to",
    "upgraded to",
    "downgraded to",
    "picked",
    "chose",
    "selected",
    "adopted",
    "prefer",
)


# Characters that terminate a subject when scanning backward from a verb,
# or a value when scanning forward. Mixes Chinese and ASCII punctuation.
_BOUNDARY_CHARS: frozenset[str] = frozenset("\n\t，。；：、,.!?;:()（）「」【】[]{}<>《》\"'`")


def _strip_punct(text: str) -> str:
    return "".join(ch for ch in text if ch not in _BOUNDARY_CHARS).strip()


def _is_cjk_char(ch: str) -> bool:
    return "一" <= ch <= "鿿"


@dataclass(frozen=True)
class Slot:
    """One extracted ``{subject}{verb}{value}`` slot from a sentence."""

    subject: str
    verb: str
    value: str


class SlotExtractor:
    """Pulls ``(subject, value)`` pairs out of Chinese/English decision text.

    The extractor is intentionally shallow — it looks for a known transition
    verb, then takes the token immediately before as the subject and the
    token immediately after as the value, stopping at punctuation on either
    side. This works for the decision-log style that dominates planning
    conversations ("数据库改用 MySQL", "RPC 框架采用 Thrift") without needing
    a tokenizer or model.
    """

    def __init__(self, verbs: tuple[str, ...] = _TRANSITION_VERBS) -> None:
        self._verbs = verbs

    def extract(self, text: str) -> list[Slot]:
        """Return all slots found in ``text``. Empty list when no verb fires."""
        if not text:
            return []
        slots: list[Slot] = []
        taken_spans: list[tuple[int, int]] = []  # avoid double-counting nested verbs
        for verb in self._verbs:
            start = 0
            while True:
                idx = text.find(verb, start)
                if idx == -1:
                    break
                end = idx + len(verb)
                # Skip if this span overlaps one already claimed by a longer verb.
                if any(s <= idx < e or s < end <= e for s, e in taken_spans):
                    start = end
                    continue
                subject = self._scan_backward(text, idx)
                value = self._scan_forward(text, end)
                if subject and value:
                    slots.append(Slot(subject=subject, verb=verb, value=value))
                    taken_spans.append((idx, end))
                start = end
        return slots

    @staticmethod
    def _scan_backward(text: str, end: int) -> str:
        i = end
        while i > 0 and text[i - 1] not in _BOUNDARY_CHARS:
            i -= 1
        return _strip_punct(text[i:end])

    @staticmethod
    def _scan_forward(text: str, start: int) -> str:
        i = start
        # Skip a single leading space after English verbs like "picked ".
        while i < len(text) and text[i] in " 　":
            i += 1
        j = i
        while j < len(text) and text[j] not in _BOUNDARY_CHARS:
            j += 1
        return _strip_punct(text[i:j])


def _subjects_match(s1: str, s2: str) -> bool:
    """Two subjects match if they share a CJK substring of length ≥2
    or a significant English word (≥3 chars, case-insensitive).

    **Personal-pronoun rescue**: Chinese personal pronouns (``我 / 你 /
    他 / 她 / 咱``) are single CJK chars that would fall below the
    substring-length floor. For personal-fact sentences like
    ``我现在住在北京`` vs ``我已经搬到上海`` we DO want them to match —
    but only when both subjects look like ``pronoun + temporal adverb``
    (or just the bare pronoun). Otherwise pronoun-only matching would
    conflate ``我喜欢`` (I like) with ``我习惯`` (I'm used to), which
    describe different preferences and must not supersede each other.
    """
    a = _strip_punct(s1).lower()
    b = _strip_punct(s2).lower()
    if not a or not b:
        return False
    if a == b:
        return True
    _PRONOUNS = ("我", "你", "他", "她", "咱")
    _TEMPORAL_ADVERBS = (
        "现在",
        "已经",
        "以前",
        "最近",
        "目前",
        "原来",
        "从前",
        "之前",
    )

    def _is_pronoun_with_temporal(subject: str, pronoun: str) -> bool:
        """True if ``subject`` is ``pronoun`` followed by a recognised
        temporal adverb. Temporal anchors ("现在" / "已经" / "以前" …)
        are the signal that distinguishes a supersession ("我现在住在 X"
        → "我已经搬到 Y") from a simple new preference ("我喜欢 X" vs
        "我习惯 Y"). Without the adverb we refuse to rescue — otherwise
        bare-pronoun matches would shadow unrelated preferences that
        happen to share the same ``我`` prefix.
        """
        if not subject.startswith(pronoun):
            return False
        tail = subject[len(pronoun) :]
        if not tail:
            return False
        return any(adv in tail for adv in _TEMPORAL_ADVERBS)

    for pronoun in _PRONOUNS:
        if _is_pronoun_with_temporal(a, pronoun) and _is_pronoun_with_temporal(b, pronoun):
            return True
    # CJK substring of length ≥ 2
    for i in range(len(a) - 1):
        for j in range(i + 2, len(a) + 1):
            sub = a[i:j]
            if all(_is_cjk_char(ch) for ch in sub) and sub in b:
                return True
    # English word overlap
    words_a = set(re.findall(r"[a-zA-Z]{3,}", a))
    words_b = set(re.findall(r"[a-zA-Z]{3,}", b))
    return bool(words_a & words_b)


def _values_differ(v1: str, v2: str) -> bool:
    """Return True when the two values contradict (neither contains the other)."""
    a = _strip_punct(v1).lower().strip()
    b = _strip_punct(v2).lower().strip()
    if not a or not b:
        return False
    if a == b:
        return False
    # If one value is a prefix/extension of the other we treat it as a
    # refinement, not a contradiction ("PostgreSQL" vs "PostgreSQL 15").
    if a in b or b in a:
        return False
    return True


def _cjk_cores(subject: str) -> list[str]:
    """Return CJK substrings of length ≥2 from ``subject``, longest first.

    Used to locate the "slot noun" inside a free-form OLD statement when that
    statement doesn't contain a transition verb. For example the NEW slot
    subject "客户把预算" yields cores ["客户把预算", ..., "预算"]; the shortest
    (but still ≥2) of those is most likely to be found inside the OLD fact
    "客户初步报价：预算 5 万美元".
    """
    cores: list[str] = []
    s = _strip_punct(subject)
    for start in range(len(s)):
        for end in range(len(s), start + 1, -1):
            sub = s[start:end]
            if len(sub) >= 2 and all(_is_cjk_char(ch) for ch in sub):
                cores.append(sub)
    # dedupe, keep longest-first ordering
    seen: set[str] = set()
    uniq: list[str] = []
    for core in sorted(cores, key=len, reverse=True):
        if core not in seen:
            seen.add(core)
            uniq.append(core)
    return uniq


def _extract_implicit_value(text: str, core: str) -> str | None:
    """Find ``core`` in ``text`` and return the value token that follows.

    Only returns a value when the following token starts with a digit or an
    ASCII letter — this keeps us from treating generic CJK prose that
    happens to sit next to a slot noun as an assignment. So
    "预算 5 万美元" yields "5 万美元", but "预算 经过审批" returns None.
    """
    idx = text.find(core)
    if idx < 0:
        return None
    after = idx + len(core)
    while after < len(text) and text[after] in " 　:：是为":
        after += 1
    end = after
    while end < len(text) and text[end] not in _BOUNDARY_CHARS:
        end += 1
    candidate = _strip_punct(text[after:end])
    if not candidate:
        return None
    first = candidate[0]
    if first.isdigit() or (first.isascii() and first.isalpha()):
        return candidate
    return None


class ConflictDetector:
    """Detects conflicts between a patch and existing memory pages.

    Runs slot-based detection first (catches "PostgreSQL → MySQL" style
    swaps without negation words). Falls back to the legacy lexical +
    negation heuristic when no slot pair matches — that path still catches
    explicit cancellations like "用户不想做 Runbook Oncall Agent".
    """

    def __init__(
        self,
        searcher: LexicalSearcher | None = None,
        slot_extractor: SlotExtractor | None = None,
    ) -> None:
        self.searcher = searcher or LexicalSearcher()
        self.slot_extractor = slot_extractor or SlotExtractor()

    def detect(
        self,
        patch: MemoryPatch,
        pages: list[MemoryPage],
    ) -> list[Conflict]:
        """Return conflicts found between ``patch`` and existing pages."""
        if patch.operation == PatchOperation.ADD and not patch.new_text:
            return []
        if not pages:
            return []

        query = patch.new_text or patch.reason
        if not query.strip():
            return []

        target_pages = [p for p in pages if p.id != patch.target_page_id]
        if not target_pages:
            return []

        # Slot-based detection runs across ALL target pages (not just
        # lexically-ranked ones) because slot similarity is structural —
        # BM25 can easily miss a Chinese fact if the two statements share
        # a short slot noun but no other tokens.
        new_slots = self.slot_extractor.extract(patch.new_text or "")
        conflicts: list[Conflict] = []
        seen_page_statements: set[tuple[str, str]] = set()

        if new_slots:
            for page in target_pages:
                for statement in (*page.facts, *page.decisions):
                    existing_slots = self.slot_extractor.extract(statement)
                    for existing_slot in existing_slots:
                        if self._slot_conflict(new_slots, existing_slot):
                            key = (page.id, statement)
                            if key in seen_page_statements:
                                continue
                            seen_page_statements.add(key)
                            conflicts.append(
                                Conflict(
                                    page_id=page.id,
                                    page_title=page.title,
                                    conflicting_text=statement,
                                    reason=(
                                        f"slot '{existing_slot.subject}' reassigned: "
                                        f"'{existing_slot.value}' → new value"
                                    ),
                                    severity="warning",
                                )
                            )
                    # Implicit-value fallback: statements like "预算 5 万美元"
                    # carry no verb, so verb-based extraction yields nothing.
                    # When a NEW slot's subject core appears in the statement
                    # and the token following it is a quantity that differs
                    # from the NEW value, flag the swap.
                    if existing_slots:
                        continue
                    implicit_hit = self._implicit_value_conflict(new_slots, statement)
                    if implicit_hit is None:
                        continue
                    new_slot, old_value = implicit_hit
                    key = (page.id, statement)
                    if key in seen_page_statements:
                        continue
                    seen_page_statements.add(key)
                    conflicts.append(
                        Conflict(
                            page_id=page.id,
                            page_title=page.title,
                            conflicting_text=statement,
                            reason=(
                                f"slot '{new_slot.subject}' implicit value "
                                f"'{old_value}' ≠ new value '{new_slot.value}'"
                            ),
                            severity="warning",
                        )
                    )

        # Negation fallback — lexical retrieval so we don't slow commit_patch
        # down by comparing against every single page.
        hits = self.searcher.search(target_pages, query, top_k=5)
        for hit in hits:
            for statement in (*hit.page.facts, *hit.page.decisions):
                if (hit.page.id, statement) in seen_page_statements:
                    continue
                if self._negation_conflict(patch.new_text or "", statement):
                    conflicts.append(
                        Conflict(
                            page_id=hit.page.id,
                            page_title=hit.page.title,
                            conflicting_text=statement,
                            reason=(
                                f"patch may contradict existing fact in page '{hit.page.title}'"
                            ),
                            severity="warning",
                        )
                    )
                    seen_page_statements.add((hit.page.id, statement))
        return conflicts

    @staticmethod
    def _slot_conflict(new_slots: list[Slot], existing_slot: Slot) -> bool:
        for new_slot in new_slots:
            if _subjects_match(new_slot.subject, existing_slot.subject) and _values_differ(
                new_slot.value, existing_slot.value
            ):
                return True
        return False

    @staticmethod
    def _implicit_value_conflict(new_slots: list[Slot], statement: str) -> tuple[Slot, str] | None:
        """Match NEW slot subject against a verb-less statement.

        Returns ``(new_slot, old_value)`` on conflict, ``None`` otherwise.
        """
        for new_slot in new_slots:
            for core in _cjk_cores(new_slot.subject):
                old_value = _extract_implicit_value(statement, core)
                if old_value is None:
                    continue
                if _values_differ(new_slot.value, old_value):
                    return new_slot, old_value
                # Found a matching core with equal/overlapping value — no
                # conflict for this slot, stop looking at shorter cores
                # for this slot to avoid spurious matches.
                break
        return None

    @staticmethod
    def _negation_conflict(new_text: str, existing: str) -> bool:
        new_lower = new_text.lower()
        existing_lower = existing.lower()
        for pattern in _NEGATION_PATTERNS:
            if pattern not in new_lower:
                continue
            words_in_existing = set(existing_lower.split())
            words_in_new = set(new_lower.split())
            if len(words_in_existing) < 2:
                continue
            overlap = words_in_existing & words_in_new
            if len(overlap) / len(words_in_existing) >= 0.3:
                return True
        return False

    def detect_page_conflicts(
        self,
        new_page: MemoryPage,
        existing_pages: list[MemoryPage],
    ) -> list[Conflict]:
        """Detect conflicts between ``new_page``'s facts/decisions and
        existing pages. Used during paging to mark superseded pages.

        Each fact or decision in ``new_page`` is treated as a synthetic
        ``REPLACE`` patch; the regular ``detect`` machinery handles the rest.
        Pages already marked ``superseded_by`` are skipped — once a page is
        superseded we do not want its contents to generate further conflicts.
        """
        target_pages = [
            p for p in existing_pages if p.id != new_page.id and p.superseded_by is None
        ]
        if not target_pages:
            return []
        aggregated: list[Conflict] = []
        seen: set[tuple[str, str]] = set()
        for statement in (*new_page.facts, *new_page.decisions):
            if not statement.strip():
                continue
            synthetic = MemoryPatch(
                operation=PatchOperation.REPLACE,
                target_page_id=new_page.id,
                new_text=statement,
                reason=f"page {new_page.id} facts/decisions",
                source_refs=[],
            )
            for conflict in self.detect(synthetic, target_pages):
                key = (conflict.page_id, conflict.conflicting_text)
                if key in seen:
                    continue
                seen.add(key)
                aggregated.append(conflict)
        return aggregated
