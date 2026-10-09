"""Slot extractor + page-supersession integration tests (M10 #2).

- ``TestSlotExtractor`` pins the public behavior of ``SlotExtractor``:
  positive extractions, boundary skipping, and no-match returns.
- ``TestImplicitValueFallback`` covers the verb-less path that catches
  "预算 5 万美元" / "预算调整到 3 万欧元" style swaps.
- ``TestPagingSupersedes`` exercises the end-to-end paging hook: a
  conflicting second page marks the first page ``superseded_by`` and the
  retrieval layer stops returning it.
"""

from __future__ import annotations

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.conflict import (
    ConflictDetector,
    SlotExtractor,
    _extract_implicit_value,
    _subjects_match,
    _values_differ,
)
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import (
    MemoryPage,
    MemoryPatch,
    PageType,
    PatchOperation,
)
from memoryos_lite.store import create_store


class TestSlotExtractor:
    def test_chinese_short_verb(self):
        slots = SlotExtractor().extract("数据库选 PostgreSQL")
        assert any(s.subject == "数据库" and s.value == "PostgreSQL" for s in slots), slots

    def test_chinese_multi_char_verb(self):
        slots = SlotExtractor().extract("压测后缓存层切换到 Memcached")
        assert any(s.subject.endswith("缓存层") and s.value == "Memcached" for s in slots), slots

    def test_verb_precedence_longest_first(self):
        """``最终确定`` must beat its prefix ``确定``."""
        slots = SlotExtractor().extract("技术栈最终确定 Rust")
        assert any(s.verb == "最终确定" and s.value == "Rust" for s in slots), slots
        # And the shorter ``定`` shouldn't steal the match downstream either.
        assert not any(s.verb == "定" and s.subject == "技术栈最终确" for s in slots)

    def test_english_verb(self):
        slots = SlotExtractor().extract("The team picked Kotlin for services")
        assert any(s.verb == "picked" and s.value.startswith("Kotlin") for s in slots), slots

    def test_punctuation_stops_subject_scan(self):
        slots = SlotExtractor().extract("综合评估后，技术栈确定 Rust")
        # Subject must start AFTER the comma, not include prior prose.
        assert any(s.subject == "技术栈" and s.value == "Rust" for s in slots), slots

    def test_empty_text_returns_empty(self):
        assert SlotExtractor().extract("") == []

    def test_no_verb_returns_empty(self):
        assert SlotExtractor().extract("这是一段没有任何决策动词的描述文字。") == []


class TestImplicitValueFallback:
    def test_numeric_value_extracted(self):
        assert _extract_implicit_value("预算 5 万美元", "预算") == "5 万美元"

    def test_colon_value_extracted(self):
        assert _extract_implicit_value("预算：10 万美元", "预算") == "10 万美元"

    def test_generic_cjk_prose_returns_none(self):
        """Implicit extraction must NOT fire for arbitrary CJK prose — only
        for values that start with a digit or ASCII letter."""
        assert _extract_implicit_value("预算 经过审批同意", "预算") is None

    def test_missing_core_returns_none(self):
        assert _extract_implicit_value("hello world", "预算") is None

    def test_budget_swap_end_to_end(self):
        detector = ConflictDetector()
        page = MemoryPage(
            session_id="s1",
            page_type=PageType.SOURCE_SUMMARY,
            title="budget",
            summary="",
            facts=["客户初步报价：预算 5 万美元"],
        )
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=None,
            new_text="客户把预算调整到 3 万欧元",
            reason="update",
            source_refs=[],
        )
        conflicts = detector.detect(patch, [page])
        assert len(conflicts) == 1
        assert "预算" in conflicts[0].reason


class TestMatchingHelpers:
    def test_subjects_match_on_cjk_substring(self):
        assert _subjects_match("客户把预算", "初步报价：预算")
        assert _subjects_match("缓存层最终", "缓存层初步")

    def test_subjects_differ(self):
        assert not _subjects_match("数据库", "缓存层")
        assert not _subjects_match("Python", "Rust")

    def test_subjects_match_on_english_word(self):
        assert _subjects_match("prefer Java", "chose Java")

    def test_values_same_not_a_conflict(self):
        assert not _values_differ("PostgreSQL", "PostgreSQL")

    def test_values_refinement_not_a_conflict(self):
        # A longer refinement should not be flagged against its prefix.
        assert not _values_differ("PostgreSQL", "PostgreSQL 15")

    def test_values_differ_on_distinct_tokens(self):
        assert _values_differ("PostgreSQL", "MySQL")
        assert _values_differ("5 万美元", "3 万欧元")


class TestConflictDetectorDoesNotRegress:
    """The slot path must not break the original negation heuristic."""

    def test_existing_chinese_negation_still_detected(self):
        detector = ConflictDetector()
        page = MemoryPage(
            session_id="s1",
            page_type=PageType.SOURCE_SUMMARY,
            title="t",
            summary="",
            facts=["用户想做 Runbook Oncall Agent"],
        )
        patch = MemoryPatch(
            operation=PatchOperation.REPLACE,
            target_page_id=None,
            new_text="用户不想做 Runbook Oncall Agent",
            reason="user changed mind",
            source_refs=[],
        )
        assert detector.detect(patch, [page])


@pytest.fixture()
def supersede_service(tmp_path):
    # Paging supersede semantics require the heuristic pager.
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=6,
        recent_message_limit=1,
        memoryos_paging_mode="heuristic",
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)
