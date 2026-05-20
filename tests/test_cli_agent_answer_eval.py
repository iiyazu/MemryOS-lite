import json

from typer.testing import CliRunner

from memoryos_lite.cli import app
from memoryos_lite.config import get_settings


def test_agent_answer_eval_cli_runs_without_real_llm(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / ".memoryos"))
    runner = CliRunner()

    try:
        result = runner.invoke(app, ["eval", "agent-answer", "--run-id", "agent-cli"])

        assert result.exit_code == 0
        assert "0.33" in result.output
        assert "agent-cli_agent_answer.json" in result.output

        report_path = tmp_path / ".memoryos" / "evals" / "agent-cli_agent_answer.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_cases"] == 3
        assert report["refusal_when_no_evidence"] == 1.0
        assert report["unsupported_answer_rate"] == 1 / 3
    finally:
        get_settings.cache_clear()
