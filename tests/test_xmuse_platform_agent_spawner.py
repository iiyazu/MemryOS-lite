from pathlib import Path

from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig


def test_agent_spawner_uses_configurable_codex_model(monkeypatch) -> None:
    monkeypatch.setenv("XMUSE_CODEX_MODEL", "gpt-5.5")
    spawner = AgentSpawner(repo_root=Path("/tmp/xmuse"), mcp_port=8100)

    command = spawner._build_command(
        GodConfig(
            name="execution-god",
            runtime="codex",
            timeout_s=60,
            skill_prompt_path="",
        ),
        Path("/tmp/worktree"),
    )

    assert command[:4] == ["codex", "exec", "-m", "gpt-5.5"]


def test_agent_spawner_defaults_to_local_codex_config_model(monkeypatch) -> None:
    monkeypatch.delenv("XMUSE_CODEX_MODEL", raising=False)
    spawner = AgentSpawner(repo_root=Path("/tmp/xmuse"), mcp_port=8100)

    command = spawner._build_command(
        GodConfig(
            name="execution-god",
            runtime="codex",
            timeout_s=60,
            skill_prompt_path="",
        ),
        Path("/tmp/worktree"),
    )

    assert command[:4] == ["codex", "exec", "-m", "gpt-5.5"]


def test_agent_spawner_builds_claude_command_with_mcp_config(monkeypatch) -> None:
    monkeypatch.delenv("XMUSE_CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("XMUSE_CLAUDE_BARE", raising=False)
    spawner = AgentSpawner(repo_root=Path("/tmp/xmuse"), mcp_port=9001)

    command = spawner._build_command(
        GodConfig(
            name="execution-god",
            runtime="claude",
            timeout_s=60,
            skill_prompt_path="",
        ),
        Path("/tmp/worktree"),
    )

    assert command[0] == "claude"
    assert "-p" in command
    assert "--bare" in command
    assert "--dangerously-skip-permissions" in command
    assert "--output-format" in command and "json" in command
    assert "--model" in command
    assert command[command.index("--model") + 1] == "sonnet"
    assert "--mcp-config" in command
    mcp_config_path = Path(command[command.index("--mcp-config") + 1])
    assert mcp_config_path.exists()
    assert "9001" in mcp_config_path.read_text()
    # Claude does not accept --cwd; we must rely on subprocess cwd= instead.
    assert "--cwd" not in command


def test_agent_spawner_claude_bare_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("XMUSE_CLAUDE_BARE", "0")
    spawner = AgentSpawner(repo_root=Path("/tmp/xmuse"), mcp_port=8100)

    command = spawner._build_command(
        GodConfig(
            name="execution-god",
            runtime="claude",
            timeout_s=60,
            skill_prompt_path="",
        ),
        Path("/tmp/worktree"),
    )

    assert "--bare" not in command


def test_agent_spawner_claude_command_honors_model_override(monkeypatch) -> None:
    monkeypatch.setenv("XMUSE_CLAUDE_MODEL", "opus")
    spawner = AgentSpawner(repo_root=Path("/tmp/xmuse"), mcp_port=8100)

    command = spawner._build_command(
        GodConfig(
            name="review-god",
            runtime="claude",
            timeout_s=60,
            skill_prompt_path="",
        ),
        Path("/tmp/worktree"),
    )

    assert command[command.index("--model") + 1] == "opus"
