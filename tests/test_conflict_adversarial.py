"""Adversarial tests for ConflictDetector — verifies the M10 #2 slot-based
semantic layer catches contradictions without negation words.
"""

from memoryos_lite.conflict import ConflictDetector
from memoryos_lite.schemas import MemoryPage, MemoryPatch, PageType, PatchOperation


def _page(facts: list[str] | None = None, decisions: list[str] | None = None) -> MemoryPage:
    return MemoryPage(
        session_id="s1",
        page_type=PageType.SOURCE_SUMMARY,
        title="adversarial",
        summary="test",
        facts=facts or [],
        decisions=decisions or [],
    )


def _patch(new_text: str) -> MemoryPatch:
    return MemoryPatch(
        operation=PatchOperation.REPLACE,
        target_page_id=None,
        new_text=new_text,
        reason="adversarial",
        source_refs=[],
    )


def test_detects_postgres_to_mysql_swap():
    detector = ConflictDetector()
    page = _page(facts=["项目技术选型：数据库选 PostgreSQL"])
    patch = _patch("评审会后结论：数据库改用 MySQL 以简化运维")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1, (
        "ConflictDetector must flag swapping the database choice "
        "even without a negation word in the new statement"
    )


def test_detects_redis_to_memcached_swap():
    detector = ConflictDetector()
    page = _page(facts=["架构评审：缓存层选 Redis"])
    patch = _patch("压测结果出来，缓存层切换到 Memcached")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1


def test_detects_budget_currency_swap():
    detector = ConflictDetector()
    page = _page(facts=["客户初步报价：预算 5 万美元"])
    patch = _patch("客户把预算调整到 3 万欧元")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1


def test_detects_rpc_framework_swap():
    detector = ConflictDetector()
    page = _page(decisions=["架构设计：RPC 框架用 gRPC"])
    patch = _patch("与合作团队对接，RPC 框架采用 Thrift")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1
