from typer.testing import CliRunner

from memoryos_lite.cli import app
from memoryos_lite.config import get_settings


def test_archive_cli_ingest_attach_and_passages(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / ".memoryos"))
    runner = CliRunner()

    try:
        ingest = runner.invoke(
            app,
            [
                "archive",
                "ingest",
                "--document-id",
                "adoc_cli",
                "--archive-id",
                "archive_cli",
                "--title",
                "CLI archive",
                "--content",
                "CLI archive says Project Helios launches in Lisbon.",
                "--source-type",
                "document",
                "--source-id",
                "doc_cli",
            ],
        )
        assert ingest.exit_code == 0, ingest.output
        assert "apsg_" in ingest.output
        assert "adoc_cli" in ingest.output

        attach = runner.invoke(
            app,
            [
                "archive",
                "attach",
                "--archive-id",
                "archive_cli",
                "--scope-type",
                "session",
                "--scope-id",
                "ses_cli",
                "--source-type",
                "document",
                "--source-id",
                "doc_cli",
            ],
        )
        assert attach.exit_code == 0, attach.output
        assert "archive_cli" in attach.output

        passages = runner.invoke(
            app,
            ["archive", "passages", "--archive-id", "archive_cli"],
        )
        assert passages.exit_code == 0, passages.output
        assert "apsg_" in passages.output
    finally:
        get_settings.cache_clear()
