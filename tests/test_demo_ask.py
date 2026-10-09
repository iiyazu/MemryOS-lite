"""``python -m memoryos_eval ask-demo``: the scripted ask graph example (no network)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from memoryos_eval.ask import run_ask
from memoryos_eval.ask_demo import (
    DEMO_MARKS,
    DEMO_REQUEST,
    DEMO_REWRITE,
    DemoRewriteLLM,
    demo_retrieve,
)
from memoryos_eval.cli import app

pytest.importorskip("langgraph")


def test_demo_rewrites_once_and_puts_the_current_value_first():
    response = run_ask(
        session_id="demo",
        request=DEMO_REQUEST,
        retrieve=demo_retrieve,
        marks=DEMO_MARKS,
        llm=DemoRewriteLLM(),
    )

    assert response.queries == [DEMO_REQUEST.question, DEMO_REWRITE]
    assert response.diagnostics.stopped == "enough"
    assert response.diagnostics.llm_calls == 1
    assert "Envoy" in response.items[0].text and not response.items[0].outdated
    outdated = [item for item in response.items if item.outdated]
    assert [item.item_id for item in outdated] == ["m03"]
    assert outdated[0].current == DEMO_MARKS[0].current


def test_cli_ask_demo_shows_the_loop_and_the_outdated_note():
    result = CliRunner().invoke(app, ["ask-demo", "--mermaid"])

    assert result.exit_code == 0, result.output
    assert "not enough evidence" in result.output
    assert f"new query: {DEMO_REWRITE}" in result.output
    assert "[outdated; current: Envoy" in result.output
    assert "retrieve" in result.output and "rewrite" in result.output
