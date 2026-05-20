import re
import warnings
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any

import uvicorn
from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.table import Table
from typer import Argument, Option, Typer

from memoryos_lite.config import Settings, get_settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.evals import EvalResult, run_eval, run_eval_llm
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
AGENT_ANSWER_TABLE_COLUMNS = [
    "cases",
    "has_citation",
    "uses_retrieved_source",
    "no_evidence_refusal",
    "unsupported_rate",
]
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
    "sup_rec",
    "cand_drop",
    "act_not5",
    "avg_ms",
]


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the FastAPI server."""
    uvicorn.run("memoryos_lite.api.app:app", host=host, port=port, reload=reload)


@demo_app.command("run")
def demo_run() -> None:
    """Run an end-to-end ingest -> page -> context demo."""
    warnings.filterwarnings(
        "ignore",
        message="The default value of `allowed_objects` will change*",
        category=Warning,
        module=r"langgraph\..*",
    )
    from memoryos_lite.graphs import build_memory_graph

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


class _ScriptedAgentDemoLLM:
    """Deterministic local LLM stand-in for the CLI demo."""

    def __init__(self, patch_page_id: str) -> None:
        self.patch_page_id = patch_page_id
        self._patch_called = False

    def bind_tools(self, tools: list[Any]) -> "_ScriptedAgentDemoLLM":
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        system_text = _message_text(messages[0]) if messages else ""
        user_text = _message_text(messages[-1]) if messages else ""
        if "Classify the user's intent" in system_text:
            intent = "update" if "patch" in user_text.lower() else "recall"
            return AIMessage(content=intent)
        if "memory management agent" in system_text:
            if "patch" in user_text.lower() and not self._patch_called:
                self._patch_called = True
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "patch_page",
                            "args": {
                                "page_id": self.patch_page_id,
                                "operation": "replace",
                                "old_text": "production-ready MemoryOS platform",
                                "new_text": "eval-driven MemoryOS Lite prototype",
                            },
                            "id": "call_demo_patch",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="Tool work finished.")
        if "experimental memory QA node" in system_text:
            message_id = _first_message_id(user_text)
            citation = f" [{message_id}]" if message_id else ""
            return AIMessage(
                content=(
                    "The user decided to build MemoryOS Lite as an "
                    f"eval-driven Agent/RAG memory prototype{citation}."
                )
            )
        return AIMessage(content="recall")


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    return str(content)


def _first_message_id(text: str) -> str | None:
    match = re.search(r"message_id=([^\s]+)", text)
    return match.group(1) if match else None


@demo_app.command("agent")
def demo_agent(
    data_dir: Annotated[
        Path | None,
        Option(
            "--data-dir",
            help="Optional directory for demo storage; defaults to an isolated temp dir.",
        ),
    ] = None,
) -> None:
    """Run a deterministic LangGraph agent demo without calling a real LLM."""
    if data_dir is None:
        with TemporaryDirectory(prefix="memoryos-agent-demo-") as tmp_dir:
            _run_agent_demo(Path(tmp_dir))
        return
    _run_agent_demo(data_dir)


def _run_agent_demo(data_dir: Path) -> None:
    warnings.filterwarnings(
        "ignore",
        message="The default value of `allowed_objects` will change*",
        category=Warning,
        module=r"langgraph\..*",
    )
    from memoryos_lite.agent_graph import build_agent_graph

    settings = Settings(data_dir=data_dir, openai_api_key=None, recent_message_limit=1)
    service = MemoryOSService(settings=settings)
    session = service.create_session("MemoryOS Lite agent demo")
    seed_messages = [
        "User first considered a Runbook Oncall Agent for the portfolio.",
        (
            "Final decision: build MemoryOS Lite as an eval-driven Agent/RAG "
            "memory prototype with source attribution."
        ),
        "The demo should show citations, conflict review, and bounded tool loops.",
    ]
    for content in seed_messages:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    page = service.page(session.id)
    if page is None:
        raise RuntimeError("Agent demo setup failed to create a memory page.")

    llm = _ScriptedAgentDemoLLM(page.id)
    graph = build_agent_graph(service, session.id, settings=settings, llm=llm)
    config = {"configurable": {"thread_id": "agent-demo"}}

    recall_state = graph.invoke(
        {
            "messages": [HumanMessage(content="What project did the user decide to build?")],
            "session_id": session.id,
            "intent": "",
            "should_page": False,
            "context": None,
            "conflict_detected": False,
            "patch_errors": [],
            "human_approved": False,
            "result": "",
            "tool_turns": 0,
        },
        config=config,
    )
    patch_state = graph.invoke(
        {
            "messages": [HumanMessage(content="Patch the page with the corrected positioning.")],
            "session_id": session.id,
            "intent": "",
            "should_page": False,
            "context": None,
            "conflict_detected": False,
            "patch_errors": [],
            "human_approved": False,
            "result": "",
            "tool_turns": 0,
        },
        config={"configurable": {"thread_id": "agent-demo-patch"}},
    )

    console.print("[bold]Agent demo:[/bold] deterministic LangGraph run; no real LLM call")
    console.print(f"[bold]Session:[/bold] {session.id}")
    console.print(f"[bold]Paged memory:[/bold] {page.id} ({len(page.source_message_ids)} sources)")
    console.print("\n[bold]Recall answer[/bold]")
    console.print(recall_state["result"], markup=False)
    console.print("\n[bold]Patch conflict review[/bold]")
    errors = patch_state.get("patch_errors") or ["No patch errors recorded."]
    for error in errors:
        console.print(f"- {error}", markup=False)
    trace_types = [
        trace.event_type
        for trace in service.store.list_traces(session.id)
        if trace.event_type.startswith("agent_")
    ]
    console.print("\n[bold]Agent trace[/bold]")
    console.print(", ".join(trace_types), markup=False)


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


@eval_app.command("agent-answer")
def eval_agent_answer(run_id: str | None = None) -> None:
    """Run deterministic agent-answer diagnostics without real LLM/API calls."""
    from memoryos_lite.agent_answer_eval import run_agent_answer_eval

    settings = get_settings()
    eval_run_id = run_id or datetime.now(UTC).strftime("agent_answer_%Y%m%d_%H%M%S")
    summary = run_agent_answer_eval(settings, eval_run_id)
    table = Table(*AGENT_ANSWER_TABLE_COLUMNS)
    row = _agent_answer_table_row(summary)
    table.add_row(*(row[column] for column in AGENT_ANSWER_TABLE_COLUMNS))
    console.print(table)
    console.print(
        f"[bold]Report:[/bold] {settings.data_dir / 'evals' / f'{eval_run_id}_agent_answer.json'}"
    )


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


@eval_app.command("manifest")
def eval_manifest(
    data_path: Annotated[str, Option("--data-path", "-d", help="Path to LongMemEval JSON")],
    output_path: Annotated[
        str, Option("--output", "-o", help="Output manifest path")
    ] = ".memoryos/evals/manifests/longmemeval_50.json",
    n: Annotated[int, Option("--n", help="Number of cases to sample")] = 50,
    seed: Annotated[int, Option("--seed", help="Random seed for sampling")] = 42,
) -> None:
    """Create a fixed manifest for LongMemEval subset."""
    from memoryos_lite.longmemeval_manifest import create_manifest

    create_manifest(Path(data_path), Path(output_path), n=n, seed=seed)
    console.print(f"[green]Manifest created:[/green] {output_path} ({n} cases, seed={seed})")


@eval_app.command("diagnose")
def eval_diagnose(
    report_path: Annotated[str, Argument(help="Path to benchmark result JSON")],
) -> None:
    """Classify failure modes from a benchmark result file."""
    from memoryos_lite.diagnostic_report import generate_report, load_results

    results = load_results(Path(report_path))
    report = generate_report(results)

    console.print(f"\n[bold]Diagnostic Report[/bold] ({report['total_cases']} cases)\n")
    console.print(f"Source hit rate: [green]{report['source_hit_rate']:.1%}[/green]\n")

    console.print("[bold]Failure Breakdown:[/bold]")
    for mode, count in sorted(report["failure_breakdown"].items(), key=lambda x: -x[1]):
        pct = count / report["total_cases"] * 100 if report["total_cases"] > 0 else 0
        color = "green" if mode == "pass" else "red"
        console.print(f"  [{color}]{mode}[/{color}]: {count} ({pct:.0f}%)")

    if report["typical_failures"]:
        console.print("\n[bold]Typical Failures:[/bold]")
        for mode, case_ids in report["typical_failures"].items():
            console.print(f"  {mode}: {', '.join(case_ids)}")

    item_contrib = report["item_contribution"]
    console.print("\n[bold]Item Contribution:[/bold]")
    console.print(f"  Item helped: {item_contrib['item_helped']}")
    console.print(f"  Page only: {item_contrib['page_only']}")


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


def _agent_answer_table_row(summary: Any) -> dict[str, str]:
    refusal = (
        "-"
        if summary.refusal_when_no_evidence is None
        else f"{summary.refusal_when_no_evidence:.2f}"
    )
    return {
        "cases": str(summary.total_cases),
        "has_citation": f"{summary.answer_has_citation:.2f}",
        "uses_retrieved_source": f"{summary.answer_uses_retrieved_source:.2f}",
        "no_evidence_refusal": refusal,
        "unsupported_rate": f"{summary.unsupported_answer_rate:.2f}",
    }


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
                "sup_rec": str(sum(item.superseded_source_recovered for item in items)),
                "cand_drop": str(sum(item.candidate_budget_dropped for item in items)),
                "act_not5": str(sum(item.active_overlap_not_top5 for item in items)),
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
