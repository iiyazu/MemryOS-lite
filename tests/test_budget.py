from memoryos_lite.budget import DynamicBudget
from memoryos_lite.config import Settings
from memoryos_lite.schemas import MemoryPage, Message, PageType, Role
from memoryos_lite.tokenizer import TokenEstimator


def _make_message(content: str = "hello") -> Message:
    return Message(session_id="s1", role=Role.USER, content=content, token_count=5)


def _make_page(title: str = "page") -> MemoryPage:
    return MemoryPage(session_id="s1", page_type=PageType.SOURCE_SUMMARY, title=title, summary="x")


def test_empty_session_returns_floor():
    settings = Settings(rot_safe_budget=2400, hard_limit=8000)
    budget = DynamicBudget(settings, TokenEstimator())
    result = budget.compute(messages=[], pages=[], task="hi")
    assert result >= 2400
    assert result <= 8000


def test_many_pages_increases_budget():
    settings = Settings(rot_safe_budget=2400, hard_limit=8000)
    budget = DynamicBudget(settings, TokenEstimator())
    few = budget.compute([], [_make_page()], "task")
    many = budget.compute([], [_make_page() for _ in range(20)], "task")
    assert many > few


def test_complex_task_increases_budget():
    settings = Settings(rot_safe_budget=2400, hard_limit=8000)
    budget = DynamicBudget(settings, TokenEstimator())
    short = budget.compute([], [], "hi")
    long_task = budget.compute([], [], "a " * 300)
    assert long_task > short


def test_never_exceeds_hard_limit():
    settings = Settings(rot_safe_budget=2400, hard_limit=8000)
    budget = DynamicBudget(settings, TokenEstimator())
    result = budget.compute(
        [_make_message() for _ in range(100)],
        [_make_page() for _ in range(100)],
        "a " * 1000,
    )
    assert result == 8000


def test_never_below_floor():
    settings = Settings(rot_safe_budget=500, hard_limit=1000)
    budget = DynamicBudget(settings, TokenEstimator())
    result = budget.compute([], [], "")
    assert result >= 500
