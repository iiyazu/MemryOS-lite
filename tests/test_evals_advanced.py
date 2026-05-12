"""Tests for advanced eval cases and cross-session support."""

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import _materialize_messages, _run_baseline, _score
from memoryos_lite.evals_advanced import advanced_cases
from memoryos_lite.schemas import MemoryPage, PageType
from memoryos_lite.store import MemoryStore


class TestAdvancedCases:
    def test_cases_load(self):
        cases = advanced_cases()
        assert len(cases) == 16  # 4 categories * 4 each
        ids = [c.case_id for c in cases]
        assert any("fact_override" in i for i in ids)
        assert any("long_conv_early_recall" in i for i in ids)
        assert any("cross_session_profile" in i for i in ids)
        assert any("fact_accumulation" in i for i in ids)

    def test_fact_override_has_forbidden(self):
        cases = advanced_cases()
        override_cases = [c for c in cases if "fact_override" in c.case_id]
        for case in override_cases:
            assert "北京海淀" in case.forbidden_facts
            assert "上海浦东" in case.expected_facts

    def test_cross_session_cases_are_marked_as_new_session_queries(self):
        cases = advanced_cases()
        cross_session_cases = [c for c in cases if c.case_id.startswith("cross_session_profile")]
        assert cross_session_cases
        for case in cross_session_cases:
            assert case.query_in_new_session is True
            assert case.include_global_core is True


class TestCrossSessionCore:
    def test_list_global_core_pages_empty(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        assert store.list_global_core_pages() == []

    def test_list_global_core_pages_returns_core_profiles(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        s1 = store.create_session("session1")
        s2 = store.create_session("session2")
        store.save_page(
            MemoryPage(
                id="global_core_1",
                session_id=s1.id,
                page_type=PageType.CORE_PROFILE,
                title="Profile 1",
                summary="我是后端工程师。",
            )
        )
        store.save_page(
            MemoryPage(
                id="global_core_2",
                session_id=s2.id,
                page_type=PageType.CORE_PROFILE,
                title="Profile 2",
                summary="我专注分布式系统。",
            )
        )
        store.save_page(
            MemoryPage(
                id="not_global_core",
                session_id=s2.id,
                page_type=PageType.SOURCE_SUMMARY,
                title="Source",
                summary="普通摘要。",
            )
        )

        cores = store.list_global_core_pages()
        assert {page.id for page in cores} == {"global_core_1", "global_core_2"}

    def test_build_context_with_global_core(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        s1 = service.create_session("session1")
        s2 = service.create_session("session2")
        summary = "用户职业背景是后端工程师，专注分布式系统。"
        service.store.save_page(
            MemoryPage(
                session_id=s1.id,
                page_type=PageType.CORE_PROFILE,
                title="Global profile",
                summary=summary,
            )
        )
        ctx = service.build_context(s2.id, task="我的职业背景是什么？", include_global_core=True)
        assert ctx.pinned_core == [summary]

    def test_memoryos_cross_session_eval_uses_global_core_sources(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        case = next(c for c in advanced_cases() if c.case_id == "cross_session_profile_001")
        messages = _materialize_messages(case)

        output = _run_baseline("memoryos_lite", case, messages, service, settings)
        result = _score(case, "memoryos_lite", output, latency_ms=0)

        assert "后端工程师" in output.answer
        assert "分布式系统" in output.answer
        assert result.source_accuracy == 1.0

    def test_stateless_baselines_do_not_see_previous_session_context(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        case = next(c for c in advanced_cases() if c.case_id == "cross_session_profile_001")
        messages = _materialize_messages(case)

        output = _run_baseline("sliding_window", case, messages, service, settings)

        assert output.answer == "未找到相关记忆"
        assert output.sources == {}
