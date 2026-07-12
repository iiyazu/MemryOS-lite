from typer.testing import CliRunner

from memoryos_lite.cli import app


def test_agent_demo_cli_runs_without_real_llm(tmp_path):
    runner = CliRunner()

    result = runner.invoke(app, ["demo", "agent", "--data-dir", str(tmp_path / "demo")])

    assert result.exit_code == 0
    assert "deterministic LangGraph run; no real LLM call" in result.output
    assert "Recall answer" in result.output
    assert "Answer:" in result.output
    assert "Sources:" in result.output
    assert "msg_" in result.output
    assert "Patch conflict review" in result.output
    assert "old_text does not exist" in result.output
    assert "Agent trace" in result.output
    assert "agent_answered" in result.output
    assert "agent_patch_conflict_detected" in result.output
