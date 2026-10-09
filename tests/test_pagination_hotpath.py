"""Hot-path pagination tests (M10 #4)."""

import time

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.store import create_store


@pytest.fixture()
def perf_service(tmp_path):
    """Service tuned to never page during ingest, so we isolate list_messages cost."""
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=10**9,
        recent_message_limit=2,
        memoryos_paging_mode="heuristic",  # TestListPagesLimit needs real paging
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


class TestListMessagesLimit:
    def test_limit_returns_last_n_in_chronological_order(self, perf_service):
        session = perf_service.create_session("limit test")
        for i in range(20):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"msg {i}"))
        last5 = perf_service.store.list_messages(session.id, limit=5)
        assert len(last5) == 5
        contents = [m.content for m in last5]
        assert contents == [f"msg {i}" for i in range(15, 20)]

    def test_limit_none_returns_all(self, perf_service):
        session = perf_service.create_session("all test")
        for i in range(7):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"m{i}"))
        assert len(perf_service.store.list_messages(session.id)) == 7

    def test_limit_larger_than_count_returns_all(self, perf_service):
        session = perf_service.create_session("big limit test")
        for i in range(3):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"m{i}"))
        assert len(perf_service.store.list_messages(session.id, limit=100)) == 3


class TestSessionTokenCount:
    def test_matches_python_sum(self, perf_service):
        session = perf_service.create_session("sum test")
        for i in range(10):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"msg {i}"))
        expected = sum(m.token_count for m in perf_service.store.list_messages(session.id))
        assert perf_service.store.session_token_count(session.id) == expected

    def test_empty_session_returns_zero(self, perf_service):
        session = perf_service.create_session("empty")
        assert perf_service.store.session_token_count(session.id) == 0


class TestIngestScaleConstantTime:
    """Proves ingest latency no longer grows linearly with session size.

    Before #4, ingest() called list_messages() to sum tokens, making it O(N).
    After #4, it calls session_token_count() which is a single SQL SUM.
    """

    @pytest.mark.slow
    def test_late_ingest_not_much_slower_than_early(self, perf_service):
        session = perf_service.create_session("scale")

        # Warm up to avoid cold-start noise.
        for _ in range(5):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content="warmup"))

        def measure_batch(n: int) -> float:
            t0 = time.perf_counter()
            for i in range(n):
                perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"x{i}"))
            return (time.perf_counter() - t0) / n

        early_avg = measure_batch(50)
        # Grow session to ~500 messages before measuring the "late" batch.
        for i in range(445):
            perf_service.ingest(session.id, MessageCreate(role=Role.USER, content=f"filler {i}"))
        late_avg = measure_batch(50)

        # With O(N) ingest this ratio was easily 10×+ at 500 messages.
        # Allow generous headroom (5×) for SQLite warmup / CI jitter.
        assert late_avg < early_avg * 5, (
            f"ingest latency grew {late_avg / early_avg:.1f}× from 5→500 messages "
            f"(early={early_avg * 1000:.2f}ms late={late_avg * 1000:.2f}ms); "
            "hot path may have regressed to O(N)"
        )
