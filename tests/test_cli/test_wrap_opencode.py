"""Tests for `headroom wrap opencode` and RTK injection.

Exercises the OpenCode-specific helpers for proxy routing and
CLI context-tool setup.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from headroom.cli import wrap as wrap_mod
from headroom.cli.main import main


def _set_test_home(monkeypatch, tmp_path: Path) -> None:
    home = str(tmp_path)
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)


# ---------------------------------------------------------------------------
# Unit tests: RTK instruction injection
# ---------------------------------------------------------------------------


def test_opencode_rtk_injected_into_project_agents_md(tmp_path: Path) -> None:
    """wrap opencode must inject rtk instructions into the project AGENTS.md."""
    agents_md = tmp_path / "AGENTS.md"
    agent_home = tmp_path / ".config" / "opencode"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        with patch(
            "headroom.cli.wrap._ensure_rtk_binary", return_value="/usr/bin/rtk"
        ):
            with patch(
                "headroom.cli.wrap._inject_opencode_provider_config"
            ):
                with patch(
                    "headroom.cli.wrap._snapshot_opencode_config_if_unwrapped"
                ):
                    with patch(
                        "headroom.cli.wrap._setup_headroom_mcp"
                    ):
                        with patch(
                            "headroom.cli.wrap.shutil.which",
                            return_value="/usr/bin/opencode",
                        ):
                            result = runner.invoke(
                                main,
                                [
                                    "wrap",
                                    "opencode",
                                    "--prepare-only",
                                    "--port",
                                    "8787",
                                ],
            )

    assert result.exit_code == 0, result.output
    assert "rtk instructions injected into" in result.output


def test_opencode_rtk_injected_into_global_agents_md(monkeypatch, tmp_path: Path) -> None:
    """wrap opencode must inject rtk instructions into ~/.config/opencode/AGENTS.md."""
    _set_test_home(monkeypatch, tmp_path)
    global_agents = tmp_path / ".config" / "opencode" / "AGENTS.md"
    runner = CliRunner()

    with patch(
        "headroom.cli.wrap._ensure_rtk_binary", return_value="/usr/bin/rtk"
    ):
        with patch(
            "headroom.cli.wrap._inject_opencode_provider_config"
        ):
            with patch(
                "headroom.cli.wrap._snapshot_opencode_config_if_unwrapped"
            ):
                with patch(
                    "headroom.cli.wrap._setup_headroom_mcp"
                ):
                    with patch(
                        "headroom.cli.wrap.shutil.which",
                        return_value="/usr/bin/opencode",
                    ):
                        result = runner.invoke(
                            main,
                            [
                                "wrap",
                                "opencode",
                                "--prepare-only",
                                "--port",
                                "8787",
                            ],
        )

    assert result.exit_code == 0, result.output
    assert global_agents.exists(), (
        f"Global AGENTS.md not created at {global_agents}\n{result.output}"
    )
    content = global_agents.read_text()
    assert "rtk" in content.lower()


def test_opencode_rtk_skipped_with_flag(monkeypatch, tmp_path: Path) -> None:
    """--no-rtk must skip RTK setup entirely."""
    global_agents = tmp_path / ".config" / "opencode" / "AGENTS.md"
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        with patch(
            "headroom.cli.wrap._inject_opencode_provider_config"
        ):
            with patch(
                "headroom.cli.wrap._snapshot_opencode_config_if_unwrapped"
            ):
                with patch(
                    "headroom.cli.wrap._setup_headroom_mcp"
                ):
                    with patch(
                        "headroom.cli.wrap.shutil.which",
                        return_value="/usr/bin/opencode",
                    ):
                        result = runner.invoke(
                            main,
                            [
                                "wrap",
                                "opencode",
                                "--no-context-tool",
                                "--prepare-only",
                                "--port",
                                "8787",
                            ],
            )

    assert result.exit_code == 0, result.output
    assert "rtk" not in result.output.lower()


# ---------------------------------------------------------------------------
# --code-graph flag
# ---------------------------------------------------------------------------


def test_opencode_code_graph_flag_accepted(tmp_path: Path) -> None:
    """--code-graph must be accepted by wrap opencode without error."""
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        with patch(
            "headroom.cli.wrap._ensure_rtk_binary", return_value="/usr/bin/rtk"
        ):
            with patch(
                "headroom.cli.wrap._inject_opencode_provider_config"
            ):
                with patch(
                    "headroom.cli.wrap._snapshot_opencode_config_if_unwrapped"
                ):
                    with patch(
                        "headroom.cli.wrap._setup_headroom_mcp"
                    ):
                        with patch(
                            "headroom.cli.wrap.shutil.which",
                            return_value="/usr/bin/opencode",
                        ):
                            result = runner.invoke(
                                main,
                                [
                                    "wrap",
                                    "opencode",
                                    "--code-graph",
                                    "--prepare-only",
                                    "--port",
                                    "8787",
                                ],
            )

    assert result.exit_code == 0, result.output
