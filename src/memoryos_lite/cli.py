from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import uvicorn
from rich.console import Console
from rich.table import Table
from typer import Option, Typer

from memoryos_lite.config import get_settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import EvalResult, run_eval, run_eval_llm
from memoryos_lite.graphs import build_memory_graph
from memoryos_lite.llm_judge import JudgeVerdict
from memoryos_lite.public_benchmarks import PublicBenchmarkResult, run_public_benchmark
from memoryos_lite.schemas import MessageCreate, Role

app = Typer(help="MemoryOS Lite CLI")
demo_app = Typer(help="Run local demos")
eval_app = Typer(help="Run benchmark tasks")
app.add_typer(demo_app, name="demo")
app.add_typer(eval_app, name="eval")
console = Console()
EVAL_TABLE_COLUMNS = [
    "baseline",
    "cases",
    "accuracy",
    "source",
    "avg_tokens",
    "pages",
    "loaded",
    "dropped",
    "dropped_cases",
    "sources",
    "supporting",
]
LLM_JUDGE_TABLE_COLUMNS = ["baseline", "cases", "pass_rate", "failed", "errors"]
PUBLIC_TABLE_COLUMNS = [
    "benchmark",
    "baseline",
    "cases",
    "pass_rate",
    "source_hit",
    "session_hit",
    "msg_src@5",
    "msg_ses@5",
    "page_src@k",
    "page_ses@k",
    "avg_tokens",
    "pages",
    "loaded",
    "dropped",
    "srcs/page",
    "rel_dropped",
    "avg_ms",
]


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the FastAPI server."""
    uvicorn.run("memoryos_lite.api.app:app", host=host, port=port, reload=reload)


@demo_app.command("run")
def demo_run() -> None:
    """Run an end-to-end ingest -> page -> context demo."""
    service = MemoryOSService()
    service.settings.rot_safe_budget = 1
    service.settings.recent_message_limit = 2
    session = service.create_session("MemoryOS Lite demo")
    messages = [
        MessageCreate(role=Role.USER, content="用户目标：20 天内完成 Agent infra 简历项目。"),
        MessageCreate(role=Role.ASSISTANT, content="已记录目标。"),
        MessageCreate(
            role=Role.USER,
            content="最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        ),
        MessageCreate(
            role=Role.USER,
            content="技术栈优先练习 LangGraph、FastAPI、SQLite 和 benchmark。",
        ),
    ]
    graph = build_memory_graph(service)
    state = None
    for message in messages:
        state = graph.invoke(
            {
                "session_id": session.id,
                "message": message,
                "task": "用户最终决定做什么 Agent 项目？",
                "budget": 600,
            }
        )
    context = state["context"] if state else service.build_context(session.id, "demo", 600)
    console.print(f"[bold]Session:[/bold] {session.id}")
    console.print(f"[bold]Estimated tokens:[/bold] {context.estimated_tokens}")
    for page in context.retrieved_pages + context.active_task_pages:
        console.print(f"[green]Loaded page[/green] {page.page_id}: {page.title}")


@eval_app.command("run")
def eval_run(
    run_id: str | None = None,
    baseline: Annotated[list[str] | None, Option("--baseline", "-b")] = None,
    isolated: bool = True,
    case_set: Annotated[
        str, Option("--case-set", "-c", help="builtin | advanced | hard | all")
    ] = "builtin",
    llm_judge: Annotated[
        bool,
        Option("--llm-judge", help="Score answers with the configured chat LLM judge"),
    ] = False,
) -> None:
    """Run the built-in demo benchmark."""
    settings = get_settings()
    eval_run_id = run_id or datetime.now(UTC).strftime("run_%Y%m%d_%H%M%S")
    if llm_judge:
        verdicts = run_eval_llm(
            settings,
            run_id=eval_run_id,
            baselines=baseline or ["all"],
            isolated=isolated,
            case_set=case_set,
        )
        table = Table(*LLM_JUDGE_TABLE_COLUMNS)
        for row in _llm_judge_table_rows(verdicts):
            table.add_row(*(row[column] for column in LLM_JUDGE_TABLE_COLUMNS))
        console.print(table)
        console.print(
            f"[bold]Report:[/bold] {settings.data_dir / 'evals' / f'{eval_run_id}_llm_judge.json'}"
        )
        return
    results = run_eval(
        settings,
        run_id=eval_run_id,
        baselines=baseline or ["all"],
        isolated=isolated,
        case_set=case_set,
    )
    table = Table(*EVAL_TABLE_COLUMNS)
    for row in _eval_table_rows(results):
        table.add_row(*(row[column] for column in EVAL_TABLE_COLUMNS))
    console.print(table)
    console.print(f"[bold]Report:[/bold] {settings.data_dir / 'evals' / f'{eval_run_id}.json'}")


@eval_app.command("public")
def eval_public(
    benchmark: Annotated[str, Option("--benchmark", "-k", help="longmemeval | locomo")],
    data_path: Annotated[str, Option("--data-path", "-d", help="Path to benchmark JSON")],
    run_id: str | None = None,
    baseline: Annotated[list[str] | None, Option("--baseline", "-b")] = None,
    compare_baselines: Annotated[
        bool,
        Option(
            "--compare-baselines",
            help=("Run all public baselines; when set, this overrides any --baseline values."),
        ),
    ] = False,
    limit: Annotated[int | None, Option("--limit", "-n", help="Max QA cases to run")] = None,
    llm_answer: Annotated[
        bool,
        Option(
            "--llm-answer/--no-llm-answer",
            help="Generate answers with the configured chat LLM over retrieved context",
        ),
    ] = False,
    llm_judge: Annotated[
        bool,
        Option("--llm-judge/--no-llm-judge", help="Score answers with the configured chat LLM"),
    ] = False,
    isolated: bool = True,
) -> None:
    """Run LongMemEval or LoCoMo JSON through the local benchmark adapter."""
    settings = get_settings()
    eval_run_id = run_id or datetime.now(UTC).strftime("public_%Y%m%d_%H%M%S")
    selected_baselines = ["all"] if compare_baselines else baseline or ["memoryos_lite"]
    results = run_public_benchmark(
        settings,
        benchmark=benchmark,
        data_path=Path(data_path),
        run_id=eval_run_id,
        baselines=selected_baselines,
        limit=limit,
        llm_answer=llm_answer,
        llm_judge=llm_judge,
        isolated=isolated,
    )
    table = Table(*PUBLIC_TABLE_COLUMNS)
    for row in _public_table_rows(results):
        table.add_row(*(row[column] for column in PUBLIC_TABLE_COLUMNS))
    console.print(table)
    report_name = f"{eval_run_id}_{benchmark.lower()}.json"
    console.print(f"[bold]Report:[/bold] {settings.data_dir / 'evals' / report_name}")


def _llm_judge_table_rows(results: list[JudgeVerdict]) -> list[dict[str, str]]:
    grouped: dict[str, list[JudgeVerdict]] = {}
    for result in results:
        baseline = result.case_id.split("/", 1)[0] if "/" in result.case_id else "unknown"
        grouped.setdefault(baseline, []).append(result)
    rows: list[dict[str, str]] = []
    for name, items in grouped.items():
        passed = sum(1 for item in items if item.verdict == "pass")
        errors = sum(1 for item in items if item.verdict == "error")
        rows.append(
            {
                "baseline": name,
                "cases": str(len(items)),
                "pass_rate": f"{passed / len(items):.2f}",
                "failed": str(sum(1 for item in items if item.verdict == "fail")),
                "errors": str(errors),
            }
        )
    return rows


def _public_table_rows(results: list[PublicBenchmarkResult]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[PublicBenchmarkResult]] = {}
    for result in results:
        grouped.setdefault((result.benchmark, result.baseline), []).append(result)
    rows: list[dict[str, str]] = []
    for (benchmark, baseline), items in grouped.items():
        passed = sum(1 for item in items if item.verdict == "pass")
        source_items = [item for item in items if item.source_hit is not None]
        session_items = [item for item in items if item.session_hit is not None]
        source_at_k_items = [item for item in items if item.source_hit_at_k is not None]
        session_at_k_items = [item for item in items if item.session_hit_at_k is not None]
        page_source_at_k_items = [
            item for item in items if item.page_source_overlap_at_k is not None
        ]
        page_session_at_k_items = [
            item for item in items if item.page_session_overlap_at_k is not None
        ]
        rows.append(
            {
                "benchmark": benchmark,
                "baseline": baseline,
                "cases": str(len(items)),
                "pass_rate": f"{passed / len(items):.2f}",
                "source_hit": _optional_rate(source_items, "source_hit"),
                "session_hit": _optional_rate(session_items, "session_hit"),
                "msg_src@5": _optional_rate(source_at_k_items, "source_hit_at_k"),
                "msg_ses@5": _optional_rate(session_at_k_items, "session_hit_at_k"),
                "page_src@k": _optional_rate(
                    page_source_at_k_items,
                    "page_source_overlap_at_k",
                ),
                "page_ses@k": _optional_rate(
                    page_session_at_k_items,
                    "page_session_overlap_at_k",
                ),
                "avg_tokens": str(sum(item.context_tokens for item in items) // len(items)),
                "pages": f"{sum(item.page_count for item in items) / len(items):.1f}",
                "loaded": f"{sum(item.loaded_pages for item in items) / len(items):.1f}",
                "dropped": f"{sum(item.dropped_pages for item in items) / len(items):.1f}",
                "srcs/page": _avg_page_sources(items),
                "rel_dropped": str(sum(item.dropped_relevant_page_count for item in items)),
                "avg_ms": str(sum(item.latency_ms for item in items) // len(items)),
            }
        )
    return rows


def _avg_page_sources(items: list[PublicBenchmarkResult]) -> str:
    source_counts = [count for item in items for count in item.page_source_counts]
    if not source_counts:
        return "-"
    return f"{sum(source_counts) / len(source_counts):.1f}"


def _optional_rate(items: list[PublicBenchmarkResult], field_name: str) -> str:
    if not items:
        return "-"
    hits = sum(1 for item in items if getattr(item, field_name) is True)
    return f"{hits / len(items):.2f}"


def _eval_table_rows(results: list[EvalResult]) -> list[dict[str, str]]:
    grouped: dict[str, list[EvalResult]] = {}
    for result in results:
        grouped.setdefault(result.baseline, []).append(result)
    rows: list[dict[str, str]] = []
    for name, items in grouped.items():
        rows.append(
            {
                "baseline": name,
                "cases": str(len(items)),
                "accuracy": f"{sum(item.answer_accuracy for item in items) / len(items):.2f}",
                "source": f"{sum(item.source_accuracy for item in items) / len(items):.2f}",
                "avg_tokens": str(sum(item.context_tokens for item in items) // len(items)),
                "pages": f"{sum(item.page_count for item in items) / len(items):.1f}",
                "loaded": f"{sum(item.loaded_pages for item in items) / len(items):.1f}",
                "dropped": f"{sum(item.dropped_pages for item in items) / len(items):.1f}",
                "dropped_cases": str(sum(1 for item in items if item.dropped_pages > 0)),
                "sources": f"{sum(item.source_count for item in items) / len(items):.1f}",
                "supporting": (
                    f"{sum(item.supporting_source_count for item in items) / len(items):.1f}"
                ),
            }
        )
    return rows


if __name__ == "__main__":
    app()
