from datetime import UTC, datetime
from typing import Annotated

import uvicorn
from rich.console import Console
from rich.table import Table
from typer import Option, Typer

from memoryos_lite.config import get_settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import EvalResult, run_eval
from memoryos_lite.graphs import build_memory_graph
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
) -> None:
    """Run the built-in demo benchmark."""
    settings = get_settings()
    eval_run_id = run_id or datetime.now(UTC).strftime("run_%Y%m%d_%H%M%S")
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
