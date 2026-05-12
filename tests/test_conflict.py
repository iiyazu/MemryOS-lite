from memoryos_lite.conflict import ConflictDetector
from memoryos_lite.schemas import MemoryPage, MemoryPatch, PageType, PatchOperation


def _make_page(
    title: str = "test page",
    facts: list[str] | None = None,
    decisions: list[str] | None = None,
) -> MemoryPage:
    return MemoryPage(
        session_id="s1",
        page_type=PageType.SOURCE_SUMMARY,
        title=title,
        summary="test",
        facts=facts or [],
        decisions=decisions or [],
    )


def _make_patch(
    new_text: str,
    operation: PatchOperation = PatchOperation.REPLACE,
    target_page_id: str | None = None,
) -> MemoryPatch:
    return MemoryPatch(
        operation=operation,
        target_page_id=target_page_id,
        new_text=new_text,
        reason="test",
        source_refs=[],
    )


def test_no_conflict_on_unrelated_content():
    detector = ConflictDetector()
    page = _make_page(facts=["用户喜欢 Python"])
    patch = _make_patch("项目使用 Docker 部署")
    conflicts = detector.detect(patch, [page])
    assert conflicts == []


def test_detects_negation_conflict_chinese():
    detector = ConflictDetector()
    page = _make_page(
        title="项目决策",
        facts=["用户想做 Runbook Oncall Agent"],
    )
    patch = _make_patch("用户不想做 Runbook Oncall Agent")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1
    assert conflicts[0].page_id == page.id
    assert conflicts[0].severity == "warning"


def test_detects_negation_conflict_english():
    detector = ConflictDetector()
    page = _make_page(
        title="preferences",
        decisions=["user wants to use Redis for caching"],
    )
    patch = _make_patch("user no longer wants to use Redis for caching")
    conflicts = detector.detect(patch, [page])
    assert len(conflicts) >= 1


def test_no_conflict_when_no_pages():
    detector = ConflictDetector()
    patch = _make_patch("something new")
    conflicts = detector.detect(patch, [])
    assert conflicts == []


def test_skips_target_page():
    detector = ConflictDetector()
    page = _make_page(facts=["用户想做 Runbook Oncall Agent"])
    patch = _make_patch(
        "用户不想做 Runbook Oncall Agent",
        target_page_id=page.id,
    )
    # The target page itself should not be checked for conflicts
    conflicts = detector.detect(patch, [page])
    assert conflicts == []


def test_add_with_no_new_text_returns_empty():
    detector = ConflictDetector()
    page = _make_page(facts=["something"])
    patch = MemoryPatch(
        operation=PatchOperation.ADD,
        new_text=None,
        reason="test",
        source_refs=[],
    )
    conflicts = detector.detect(patch, [page])
    assert conflicts == []
