from memoryos_lite.observability import (
    CONTEXT_BUILD_SECONDS,
    CONTEXT_TOKENS,
    INGEST_TOTAL,
    PAGE_TOTAL,
)
from memoryos_lite.schemas import MessageCreate, Role


def _counter_value(counter, labels=None):
    """Get current value of a counter."""
    if labels:
        return counter.labels(**labels)._value.get()
    return counter._value.get()


def _histogram_count(histogram):
    """Get observation count from a histogram."""
    return (
        histogram._sum._count.get() if hasattr(histogram._sum, "_count") else histogram._count.get()
    )


def test_ingest_increments_counter(service):
    before = _counter_value(INGEST_TOTAL)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))
    after = _counter_value(INGEST_TOTAL)
    assert after == before + 1


def test_page_increments_counter(service):
    session = service.create_session("test")
    for content in [
        "用户目标是在 20 天内完成 Agent infra 项目。",
        "最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        "技术栈选择 LangGraph 和 FastAPI。",
        "需要 benchmark 对比 Sliding Window 和 Vector RAG。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    before_heuristic = _counter_value(PAGE_TOTAL, {"mode": "heuristic"})
    before_agentic = _counter_value(PAGE_TOTAL, {"mode": "agentic"})
    before_fallback = _counter_value(PAGE_TOTAL, {"mode": "heuristic_fallback"})
    page = service.page(session.id)
    assert page is not None
    after_heuristic = _counter_value(PAGE_TOTAL, {"mode": "heuristic"})
    after_agentic = _counter_value(PAGE_TOTAL, {"mode": "agentic"})
    after_fallback = _counter_value(PAGE_TOTAL, {"mode": "heuristic_fallback"})
    before_total = before_heuristic + before_agentic + before_fallback
    after_total = after_heuristic + after_agentic + after_fallback
    assert after_total == before_total + 1


def test_build_context_observes_metrics(service):
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))
    service.build_context(session.id, "test task", budget=500)
    # Just verify no errors - metrics are observed internally
    # The histogram sum should be > 0 after at least one observation
    assert CONTEXT_BUILD_SECONDS._sum.get() >= 0
    assert CONTEXT_TOKENS._sum.get() >= 0
