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


if __name__ == "__main__":
    app()
