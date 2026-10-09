from __future__ import annotations

from typing import Annotated, Any

import uvicorn
from rich.console import Console
from typer import Exit, Option, Typer

from memoryos_lite.config import get_settings
from memoryos_lite.curator import build_curator_llm

app = Typer(help="MemoryOS Lite CLI")
demo_app = Typer(help="Run local demos")
app.add_typer(demo_app, name="demo")
console = Console()


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the FastAPI server."""
    uvicorn.run("memoryos_lite.api.app:app", host=host, port=port, reload=reload)


@demo_app.command("curate")
def demo_curate(
    live: Annotated[
        bool, Option("--live", help="Use the configured LLM instead of the scripted one")
    ] = False,
    mermaid: Annotated[bool, Option("--mermaid", help="Print the graph as Mermaid")] = False,
) -> None:
    """Run the curate graph (extract -> check -> repair -> consolidate) on an example."""
    try:
        from memoryos_lite.curator.graph import build_curate_graph
    except ImportError as exc:
        console.print(f"[red]demo curate needs LangGraph:[/red] {exc}")
        raise Exit(1) from exc
    from memoryos_lite.curator.demo import DEMO_REQUEST, DemoCuratorLLM

    llm: Any = DemoCuratorLLM()
    if live:
        llm = build_curator_llm(get_settings())
        if llm is None:
            console.print("[red]--live needs an LLM key for the configured provider[/red]")
            raise Exit(1)
    graph = build_curate_graph(llm)
    if mermaid:
        console.print(graph.get_graph().draw_mermaid())
    final: dict[str, Any] = {}
    for update in graph.stream({"request": DEMO_REQUEST}, stream_mode="updates"):
        for node, state in update.items():
            final.update(state)
            check = state.get("check") if isinstance(state, dict) else None
            note = ""
            if check is not None:
                note = (
                    f" -> {len(check.violations)} violation(s)" if check.violations else " -> clean"
                )
            console.print(f"[bold]{node}[/bold]{note}")
            for violation in check.violations if check is not None else []:
                console.print(f"    - {violation}")
    response = final["response"]
    console.print_json(response.model_dump_json())


@demo_app.command("ask")
def demo_ask(
    mermaid: Annotated[bool, Option("--mermaid", help="Print the graph as Mermaid")] = False,
) -> None:
    """Run the ask graph (retrieve -> grade -> rewrite -> retrieve) on a scripted example."""
    try:
        from memoryos_lite.retrieval.agentic import build_ask_graph, render_ask_item, run_ask
        from memoryos_lite.retrieval.demo import (
            DEMO_MARKS,
            DEMO_REQUEST,
            DemoRewriteLLM,
            demo_retrieve,
        )

        graph = build_ask_graph(
            demo_retrieve, DEMO_MARKS, DemoRewriteLLM(), max_rounds=DEMO_REQUEST.max_rounds
        )
    except ImportError as exc:
        console.print(f"[red]demo ask needs LangGraph:[/red] {exc}")
        raise Exit(1) from exc
    if mermaid:
        console.print(graph.get_graph().draw_mermaid())
    console.print(f"[bold]question[/bold] {DEMO_REQUEST.question}")
    for update in graph.stream(
        {"question": DEMO_REQUEST.question, "queries": [DEMO_REQUEST.question]},
        stream_mode="updates",
    ):
        for node, state in update.items():
            state = state or {}
            if node == "retrieve":
                outdated = sum(1 for item in state["found"] if item["outdated"])
                note = f" -> {len(state['found'])} item(s) so far, {outdated} outdated"
            elif node == "grade":
                note = " -> enough evidence" if state["enough"] else " -> not enough evidence"
            elif node == "rewrite":
                queries = state.get("queries")
                note = f" -> new query: {queries[-1]}" if queries else f" -> {state['stopped']}"
            else:
                note = f" -> stopped: {state.get('stopped', '')}" if state else ""
            console.print(f"[bold]{node}[/bold]{note}")
    response = run_ask(
        session_id="demo",
        request=DEMO_REQUEST,
        retrieve=demo_retrieve,
        marks=DEMO_MARKS,
        llm=DemoRewriteLLM(),
    )
    console.print("[bold]evidence for the agent[/bold]")
    for item in response.items:
        console.print(f"  {item.rank}. {render_ask_item(item)}", markup=False)


if __name__ == "__main__":
    app()
