"""Benchmark commands, run from a checkout: ``uv run python -m memoryos_eval --help``."""

from __future__ import annotations

import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from rich.console import Console
from rich.table import Table
from typer import Exit, Option, Typer

from memoryos_lite.capabilities import require_benchmark_capability, require_remote_capability
from memoryos_lite.config import get_settings

if TYPE_CHECKING:
    from memoryos_eval.evals import EvalResult
    from memoryos_eval.llm_judge import JudgeVerdict
    from memoryos_eval.public_benchmarks import PublicBenchmarkResult

app = Typer(help="Run benchmark tasks")
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
ROOMMEM_READ_COLUMNS = [
    "arm",
    "asked_in",
    "probes",
    "repeats",
    "hit@8",
    "source@8",
    "stale@8",
    "tokens",
    "correct",
    "stale",
    "missing",
    "wrong",
    "substring",
]
ROOMMEM_WRITE_COLUMNS = [
    "arm",
    "memories",
    "matched",
    "precision",
    "recall",
    "unmatched",
    "noise",
    "supersede",
    "stale_active",
    "duplicate",
    "kind_agree",
    "scope_agree",
    "legit/noise",
]
ROOMMEM_CURATOR_COLUMNS = [
    "room",
    "windows",
    "added",
    "superseded",
    "noop",
    "rej_grounding",
    "rej_schema",
    "llm_errors",
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


@app.command("run")
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
    require_remote_capability("eval.run")
    from memoryos_eval.evals import run_eval, run_eval_llm

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


@app.command("public")
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
    require_benchmark_capability("eval.public")
    from memoryos_eval.public_benchmarks import run_public_benchmark

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


@app.command("manifest")
def eval_manifest(
    data_path: Annotated[str, Option("--data-path", "-d", help="Path to LongMemEval JSON")],
    output_path: Annotated[
        str, Option("--output", "-o", help="Output manifest path")
    ] = ".memoryos/evals/manifests/longmemeval_50.json",
    n: Annotated[int, Option("--n", help="Number of cases to sample")] = 50,
    seed: Annotated[int, Option("--seed", help="Random seed for sampling")] = 42,
) -> None:
    """Create a fixed manifest for LongMemEval subset."""
    from memoryos_eval.longmemeval_manifest import create_manifest

    create_manifest(Path(data_path), Path(output_path), n=n, seed=seed)
    console.print(f"[green]Manifest created:[/green] {output_path} ({n} cases, seed={seed})")


@app.command("roommem")
def eval_roommem(
    data: Annotated[
        str,
        Option("--data", help="Directory containing rm*.json RoomMem rooms"),
    ] = "benchmarks/roommem/rooms",
    arm: Annotated[
        list[str] | None,
        Option(
            "--arm",
            help="raw | raw_project | oracle | curated | full_context; repeat for multiple arms",
        ),
    ] = None,
    rooms: Annotated[
        str | None,
        Option("--rooms", help="Comma-separated room ids (default: all rooms)"),
    ] = None,
    split: Annotated[
        str | None,
        Option("--split", help="Dataset preset: dev=rm01-rm06, test=rm07-rm12, trap=rm13-rm16"),
    ] = None,
    repeats: Annotated[
        int,
        Option("--repeats", help="Repeat each probe N times (LLM cache bypassed per repeat)"),
    ] = 1,
    embedding: Annotated[
        str,
        Option("--embedding", help="none | fastembed"),
    ] = "none",
    fake_llm: Annotated[
        bool,
        Option(
            "--fake-llm",
            help="Use the deterministic fake answerer/judge instead of the configured provider",
        ),
    ] = False,
    curated_source: Annotated[
        str,
        Option("--curated-source", help="Registered curated memory source name for --arm curated"),
    ] = "default",
    curator_window: Annotated[
        int,
        Option("--curator-window", help="Curator window size in messages for --arm curated"),
    ] = 12,
    price_in_per_mtok: Annotated[
        float | None,
        Option(
            "--price-in-per-mtok",
            help="Optional input price per million tokens for the estimated-cost line",
        ),
    ] = None,
    price_out_per_mtok: Annotated[
        float | None,
        Option(
            "--price-out-per-mtok",
            help="Optional output price per million tokens for the estimated-cost line",
        ),
    ] = None,
    answerer_llm: Annotated[
        str | None,
        Option("--answerer-llm", help="Answerer model spec provider:model[@wire]"),
    ] = None,
    judge_llm: Annotated[
        str | None,
        Option("--judge-llm", help="Judge model spec provider:model[@wire]"),
    ] = None,
    curator_llm: Annotated[
        str | None,
        Option("--curator-llm", help="Curator model spec provider:model[@wire]"),
    ] = None,
    merge_project: Annotated[
        str | None,
        Option("--merge-project", help="Put every selected room into this one project"),
    ] = None,
    shared_project: Annotated[
        bool,
        Option(
            "--shared-project",
            help="Curated/oracle arms deliver project/user memories to every room of the project",
        ),
    ] = False,
    curated_evidence: Annotated[
        list[str] | None,
        Option(
            "--curated-evidence",
            help="plain | demote | agentic: how the curated arm builds evidence (repeatable)",
        ),
    ] = None,
    out: Annotated[
        str,
        Option("--out", help="Output directory for results and reports"),
    ] = "artifacts/roommem",
) -> None:
    """Run the RoomMem multi-room memory evaluation."""
    from memoryos_lite.roommem import RoomMemError, load_rooms, resolve_split, run_roommem

    if split is not None and rooms is not None:
        console.print("[red]RoomMem error:[/red] --split and --rooms are mutually exclusive")
        raise Exit(1)
    try:
        if split is not None:
            room_ids: list[str] | None = resolve_split(split)
        elif rooms:
            room_ids = [value.strip() for value in rooms.split(",") if value.strip()]
        else:
            room_ids = None
        selected = load_rooms(Path(data), room_ids=room_ids)
        summary = run_roommem(
            rooms=selected,
            arms=arm or ["raw", "oracle"],
            out_dir=Path(out),
            repeats=repeats,
            embedding=embedding,
            curated_source_name=curated_source,
            curator_window=curator_window,
            fake_llm=fake_llm,
            price_in_per_mtok=price_in_per_mtok,
            price_out_per_mtok=price_out_per_mtok,
            answerer_llm=answerer_llm,
            judge_llm=judge_llm,
            curator_llm=curator_llm,
            merge_project=merge_project,
            shared_project=shared_project,
            curated_evidence=tuple(curated_evidence or ("plain",)),
        )
    except RoomMemError as exc:
        console.print(f"[red]RoomMem error:[/red] {exc}")
        raise Exit(1) from exc
    _print_roommem_summary(summary)
    _print_roommem_usage(summary)
    console.print(f"[bold]Reports:[/bold] {Path(out) / 'summary.md'}")


@app.command("modulemem")
def eval_modulemem(
    data: Annotated[
        str, Option("--data", help="Directory containing mm*.json ModuleMem modules")
    ] = "benchmarks/modulemem/modules",
    arm: Annotated[
        list[str] | None,
        Option(
            "--arm",
            help="pack | oracle_pack | recent | raw_log | retrieval | full_history | none "
            "(repeatable)",
        ),
    ] = None,
    split: Annotated[str | None, Option("--split", help="dev=mm01-mm04, test=mm05-mm08")] = None,
    modules: Annotated[str | None, Option("--modules", help="Comma-separated module ids")] = None,
    repeats: Annotated[int, Option("--repeats")] = 1,
    embedding: Annotated[str, Option("--embedding", help="none | fastembed")] = "none",
    fake_llm: Annotated[bool, Option("--fake-llm")] = False,
    curator_llm: Annotated[str | None, Option("--curator-llm")] = None,
    answerer_llm: Annotated[str | None, Option("--answerer-llm")] = None,
    judge_llm: Annotated[str | None, Option("--judge-llm")] = None,
    pack_budget: Annotated[int, Option("--pack-budget")] = 1500,
    max_repairs: Annotated[
        int, Option("--max-repairs", help="Curate repair rounds per window (0-2)")
    ] = 2,
    probes: Annotated[
        bool, Option("--probes/--no-probes", help="Ask the modules' question probes")
    ] = True,
    tasks: Annotated[
        bool,
        Option("--tasks", help="Also run owner tasks (behavior); the coder uses --answerer-llm"),
    ] = False,
    coder_cmd: Annotated[
        str | None,
        Option(
            "--coder-cmd",
            help="Coding agent for owner tasks, run as CMD --workspace DIR with the task on "
            "stdin; it edits a copy of the module's seed repository and the judge grades its diff",
        ),
    ] = None,
    seeds: Annotated[
        str | None, Option("--seeds", help="Directory of <module_id>.json seed repositories")
    ] = None,
    coder_timeout: Annotated[
        float, Option("--coder-timeout", help="Seconds per coding-agent task")
    ] = 1800.0,
    out: Annotated[str, Option("--out")] = "artifacts/modulemem",
) -> None:
    """Run the ModuleMem evaluation of curated module memory."""
    from memoryos_eval.modulemem import (
        MODULEMEM_ARMS,
        MODULEMEM_SPLITS,
        ModuleMemConfig,
        ModuleMemError,
        load_modules,
        run_modulemem,
    )
    from memoryos_lite.roommem import RoomMemError

    try:
        if split is not None:
            if split not in MODULEMEM_SPLITS:
                raise ModuleMemError(f"unknown split {split!r}")
            module_ids: list[str] | None = list(MODULEMEM_SPLITS[split])
        elif modules:
            module_ids = [value.strip() for value in modules.split(",") if value.strip()]
        else:
            module_ids = None
        summary = run_modulemem(
            load_modules(Path(data), module_ids),
            out_dir=Path(out),
            config=ModuleMemConfig(
                arms=tuple(arm or MODULEMEM_ARMS),
                repeats=repeats,
                embedding=embedding,
                fake_llm=fake_llm,
                curator_llm=curator_llm,
                answerer_llm=answerer_llm,
                judge_llm=judge_llm,
                pack_budget=pack_budget,
                max_repairs=max_repairs,
                probes=probes,
                tasks=tasks,
                coder_command=tuple(shlex.split(coder_cmd)) if coder_cmd else (),
                seeds_dir=seeds,
                coder_timeout_s=coder_timeout,
            ),
        )
    except (ModuleMemError, RoomMemError) as exc:
        console.print(f"[red]ModuleMem error:[/red] {exc}")
        raise Exit(1) from exc
    for arm_name, categories in summary["read_side"].items():
        if probes:
            console.print(f"{arm_name}: correct={categories['all']['correct']}")
    for arm_name, stats in summary["behavior"].items():
        console.print(f"{arm_name}: requirements satisfied={stats['all']['satisfied']}")
    console.print(f"[bold]Reports:[/bold] {Path(out) / 'summary.md'}")


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


def _print_roommem_summary(summary: dict[str, object]) -> None:
    read_side = summary.get("read_side")
    if isinstance(read_side, dict) and read_side:
        read_table = Table(*ROOMMEM_READ_COLUMNS)
        for arm in sorted(read_side):
            asked_groups = read_side[arm]
            if not isinstance(asked_groups, dict):
                continue
            for asked_in in sorted(asked_groups):
                metrics = asked_groups[asked_in]
                if not isinstance(metrics, dict):
                    continue
                read_table.add_row(*_roommem_read_row(arm, asked_in, metrics))
        console.print(read_table)

    write_side = summary.get("write_side")
    if isinstance(write_side, dict) and write_side:
        write_table = Table(*ROOMMEM_WRITE_COLUMNS)
        for arm in sorted(write_side):
            payload = write_side[arm]
            if not isinstance(payload, dict):
                continue
            write_table.add_row(*_roommem_write_row(arm, payload))
        console.print(write_table)

        curated = write_side.get("curated")
        rooms = curated.get("curator_rooms") if isinstance(curated, dict) else None
        if isinstance(rooms, dict) and rooms:
            curator_table = Table(*ROOMMEM_CURATOR_COLUMNS)
            for room_id in sorted(rooms):
                counters = rooms[room_id]
                if not isinstance(counters, dict):
                    counters = {}
                curator_table.add_row(
                    room_id,
                    *[str(counters.get(key, 0)) for key in ROOMMEM_CURATOR_COLUMNS[1:]],
                )
            console.print(curator_table)


def _print_roommem_usage(summary: dict[str, object]) -> None:
    usage = summary.get("usage")
    if not isinstance(usage, dict) or not usage:
        return
    roles = usage.get("roles")
    if isinstance(roles, dict) and roles:
        usage_table = Table(
            "role", "calls", "cached", "tokens in", "tokens out", "mean s", "p50 s", "p95 s"
        )
        for role in sorted(roles):
            payload = roles[role] if isinstance(roles[role], dict) else {}
            latency = payload.get("latency_s")
            if not isinstance(latency, dict):
                latency = {}
            usage_table.add_row(
                role,
                str(payload.get("calls", 0)),
                str(payload.get("cached", 0)),
                _roommem_count(payload.get("tokens_in")),
                _roommem_count(payload.get("tokens_out")),
                _roommem_latency(latency.get("mean")),
                _roommem_latency(latency.get("p50")),
                _roommem_latency(latency.get("p95")),
            )
        console.print(usage_table)
    curator = usage.get("curator")
    if isinstance(curator, dict):
        tokens = curator.get("tokens_per_100_messages")
        seconds = curator.get("seconds_per_window")
        console.print(
            "Curator: {messages} messages in {windows} windows; {tokens} tokens/100 msgs; "
            "{seconds} s/window".format(
                messages=curator.get("messages", 0),
                windows=curator.get("windows", 0),
                tokens=f"{float(tokens):.1f}" if isinstance(tokens, (int, float)) else "-",
                seconds=f"{float(seconds):.3f}" if isinstance(seconds, (int, float)) else "-",
            )
        )
    cost = usage.get("estimated_cost")
    if isinstance(cost, dict) and isinstance(cost.get("cost"), (int, float)):
        console.print(
            f"[bold]Estimated cost:[/bold] ${float(cost['cost']):.4f} (provider tokens only)"
        )


def _roommem_count(value: object) -> str:
    return str(value) if isinstance(value, int) else "-"


def _roommem_latency(value: object) -> str:
    return f"{float(value):.3f}" if isinstance(value, (int, float)) else "-"


def _roommem_read_row(arm: str, asked_in: str, metrics: dict[str, object]) -> list[str]:
    labels = metrics.get("judge_labels")
    if not isinstance(labels, dict):
        labels = {}
    probes = metrics.get("probes")
    repeats = metrics.get("repeats")
    probe_count = probes if isinstance(probes, int) else 0
    repeat_count = repeats if isinstance(repeats, int) else 0
    return [
        arm,
        asked_in,
        str(probe_count),
        str(repeat_count),
        _roommem_stat(metrics.get("hit_at_8")),
        _roommem_stat(metrics.get("source_hit_at_8")),
        _roommem_stat(metrics.get("stale_at_8")),
        _roommem_stat(metrics.get("evidence_tokens"), digits=1),
        _roommem_label_rate(labels.get("correct"), probe_count, repeat_count),
        _roommem_label_rate(labels.get("stale"), probe_count, repeat_count),
        _roommem_label_rate(labels.get("missing"), probe_count, repeat_count),
        _roommem_label_rate(labels.get("wrong"), probe_count, repeat_count),
        _roommem_stat(metrics.get("substring_pass")),
    ]


def _roommem_write_row(arm: str, payload: dict[str, object]) -> list[str]:
    rates = payload.get("rates")
    if not isinstance(rates, dict):
        rates = {}
    unmatched_judged = payload.get("unmatched_judged")
    if not isinstance(unmatched_judged, dict):
        unmatched_judged = {}
    gold = payload.get("gold")
    matched = payload.get("matched")
    matched_text = (
        f"{matched}/{gold}" if isinstance(matched, int) and isinstance(gold, int) else "-"
    )
    return [
        arm,
        str(payload.get("memories", 0)),
        matched_text,
        _roommem_number(rates.get("precision")),
        _roommem_number(rates.get("recall")),
        _roommem_number(rates.get("unmatched_rate")),
        _roommem_number(rates.get("noise_rate")),
        _roommem_number(rates.get("supersede_rate")),
        _roommem_number(rates.get("stale_active_rate")),
        _roommem_number(rates.get("duplicate_rate")),
        _roommem_number(rates.get("kind_agreement")),
        _roommem_number(rates.get("scope_agreement")),
        f"{unmatched_judged.get('legit_unannotated', 0)}/{unmatched_judged.get('noise', 0)}",
    ]


def _roommem_stat(value: object, *, digits: int = 2) -> str:
    if not isinstance(value, dict):
        return "-"
    mean = value.get("mean")
    if not isinstance(mean, (int, float)):
        return "-"
    text = f"{float(mean):.{digits}f}"
    low = value.get("min")
    high = value.get("max")
    if (
        isinstance(low, (int, float))
        and isinstance(high, (int, float))
        and float(low) != float(mean)
    ):
        text += f" [{float(low):.{digits}f}, {float(high):.{digits}f}]"
    return text


def _roommem_label_rate(count: object, probes: int, repeats: int) -> str:
    denominator = probes * repeats
    if not isinstance(count, int) or denominator <= 0:
        return "-"
    return f"{count / denominator:.2f}"


def _roommem_number(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.3f}"
