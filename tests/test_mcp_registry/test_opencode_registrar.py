"""Tests for the OpenCode MCP registrar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from headroom.mcp_registry.base import RegisterStatus, ServerSpec
from headroom.mcp_registry.opencode import OpenCodeRegistrar, _strip_jsonc


def _make_registrar(tmp_path: Path) -> OpenCodeRegistrar:
    return OpenCodeRegistrar(home_dir=tmp_path)


def _spec(env: dict[str, str] | None = None) -> ServerSpec:
    return ServerSpec(
        name="headroom",
        command="headroom",
        args=("mcp", "serve"),
        env=env or {},
    )


def _serena_spec() -> ServerSpec:
    return ServerSpec(
        name="serena",
        command="uvx",
        args=(
            "--from",
            "git+https://github.com/oraios/serena",
            "serena",
            "start-mcp-server",
            "--project-from-cwd",
            "--context",
            "opencode",
        ),
    )


def _config_path(tmp_path: Path) -> Path:
    return tmp_path / ".config" / "opencode" / "opencode.jsonc"


# ----------------------------------------------------------------------
# JSONC stripping
# ----------------------------------------------------------------------


def test_strip_jsonc_removes_line_comments() -> None:
    result = _strip_jsonc('{"key": "value"} // comment\n')
    assert json.loads(result) == {"key": "value"}


def test_strip_jsonc_removes_block_comments() -> None:
    result = _strip_jsonc('{"key": "value"} /* block comment */\n')
    assert json.loads(result) == {"key": "value"}


def test_strip_jsonc_preserves_strings_with_slashes() -> None:
    result = _strip_jsonc('{"url": "http://example.com/path"}\n')
    assert json.loads(result)["url"] == "http://example.com/path"


def test_strip_jsonc_removes_trailing_commas() -> None:
    result = _strip_jsonc('{"a": 1,}\n')
    assert json.loads(result) == {"a": 1}


def test_strip_jsonc_handles_nested_trailing_commas() -> None:
    result = _strip_jsonc('{"a": [1, 2,],}\n')
    assert json.loads(result) == {"a": [1, 2]}


# ----------------------------------------------------------------------
# detect()
# ----------------------------------------------------------------------


def test_detect_true_when_config_dir_exists(tmp_path: Path) -> None:
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    assert _make_registrar(tmp_path).detect() is True


def test_detect_false_when_config_dir_missing(tmp_path: Path) -> None:
    assert _make_registrar(tmp_path).detect() is False


# ----------------------------------------------------------------------
# get_server()
# ----------------------------------------------------------------------


def test_get_server_returns_none_when_config_missing(tmp_path: Path) -> None:
    assert _make_registrar(tmp_path).get_server("headroom") is None


def test_get_server_returns_none_when_no_mcp_key(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"editor": {"theme": "dark"}}\n')
    assert _make_registrar(tmp_path).get_server("headroom") is None


def test_get_server_returns_spec_when_entry_present(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{\n'
        '  "mcp": {\n'
        '    "servers": {\n'
        '      "headroom": {\n'
        '        "type": "local",\n'
        '        "command": ["headroom", "mcp", "serve"],\n'
        '        "environment": {"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"}\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    got = _make_registrar(tmp_path).get_server("headroom")
    assert got is not None
    assert got.command == "headroom"
    assert got.args == ("mcp", "serve")
    assert got.env == {"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"}


def test_get_server_handles_jsonc_comments(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '// OpenCode config\n'
        '{\n'
        '  "mcp": {  // MCP servers\n'
        '    "servers": {\n'
        '      "headroom": {\n'
        '        "type": "local",\n'
        '        "command": ["headroom", "mcp", "serve"],\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    got = _make_registrar(tmp_path).get_server("headroom")
    assert got is not None
    assert got.command == "headroom"
    assert got.args == ("mcp", "serve")


def test_get_server_robust_to_invalid_jsonc(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{this is not valid json}\n')
    assert _make_registrar(tmp_path).get_server("headroom") is None


# ----------------------------------------------------------------------
# register_server() — happy paths
# ----------------------------------------------------------------------


def test_register_creates_config_when_missing(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    result = reg.register_server(_spec())
    assert result.status == RegisterStatus.REGISTERED
    cfg = _config_path(tmp_path)
    assert cfg.exists()
    text = cfg.read_text()
    assert "// --- Headroom MCP server ---" in text
    assert '"headroom"' in text


def test_register_appends_to_existing_config(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{\n'
        '  // user settings\n'
        '  "editor": {\n'
        '    "theme": "dark"\n'
        '  }\n'
        '}\n'
    )
    result = _make_registrar(tmp_path).register_server(_spec())
    assert result.status == RegisterStatus.REGISTERED
    text = cfg.read_text()
    assert '"editor"' in text
    assert '"theme": "dark"' in text
    assert "// --- Headroom MCP server ---" in text
    # Verify the resulting JSONC parses correctly
    data = json.loads(_strip_jsonc(text))
    assert "mcp" in data
    assert "headroom" in data["mcp"]["servers"]


def test_register_includes_environment(tmp_path: Path) -> None:
    spec = _spec(env={"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"})
    _make_registrar(tmp_path).register_server(spec)
    text = _config_path(tmp_path).read_text()
    assert '"environment"' in text
    assert '"HEADROOM_PROXY_URL"' in text


def test_register_headroom_and_serena_coexist(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    assert reg.register_server(_spec()).status == RegisterStatus.REGISTERED
    assert reg.register_server(_serena_spec()).status == RegisterStatus.REGISTERED

    text = _config_path(tmp_path).read_text()
    assert '"headroom"' in text
    assert '"serena"' in text
    assert "// --- Headroom MCP server ---" in text
    assert "// --- Headroom MCP server: serena ---" in text


def test_register_omits_environment_when_empty(tmp_path: Path) -> None:
    _make_registrar(tmp_path).register_server(_spec())
    text = _config_path(tmp_path).read_text()
    assert '"environment"' not in text


# ----------------------------------------------------------------------
# Idempotency: ALREADY / MISMATCH
# ----------------------------------------------------------------------


def test_register_already_when_block_matches_spec(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    reg.register_server(_spec())
    text_before = _config_path(tmp_path).read_text()
    result = reg.register_server(_spec())
    assert result.status == RegisterStatus.ALREADY
    assert _config_path(tmp_path).read_text() == text_before


def test_register_mismatch_when_block_differs_no_force(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    reg.register_server(_spec(env={"HEADROOM_PROXY_URL": "http://127.0.0.1:9999"}))
    text_before = _config_path(tmp_path).read_text()

    result = reg.register_server(_spec())
    assert result.status == RegisterStatus.MISMATCH
    assert "env" in (result.detail or "")
    assert _config_path(tmp_path).read_text() == text_before


def test_register_force_overwrites_block(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    reg.register_server(_spec(env={"HEADROOM_PROXY_URL": "http://127.0.0.1:9999"}))
    result = reg.register_server(_spec(), force=True)
    assert result.status == RegisterStatus.REGISTERED
    text = _config_path(tmp_path).read_text()
    assert "9999" not in text


def test_register_force_preserves_user_managed_entry(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{\n'
        '  "mcp": {\n'
        '    "servers": {\n'
        '      "headroom": {\n'
        '        "type": "local",\n'
        '        "command": ["/usr/local/bin/custom-headroom", "serve"]\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    result = _make_registrar(tmp_path).register_server(_spec(), force=True)
    assert result.status == RegisterStatus.MISMATCH
    assert "user-managed" in (result.detail or "").lower()
    assert "/usr/local/bin/custom-headroom" in cfg.read_text()


def test_register_mismatch_when_user_managed_outside_markers(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{\n'
        '  "mcp": {\n'
        '    "servers": {\n'
        '      "headroom": {\n'
        '        "type": "local",\n'
        '        "command": ["/usr/local/bin/custom-headroom", "serve"]\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    result = _make_registrar(tmp_path).register_server(_spec())
    assert result.status == RegisterStatus.MISMATCH
    assert "user-managed" in (result.detail or "").lower()
    assert "/usr/local/bin/custom-headroom" in cfg.read_text()


# ----------------------------------------------------------------------
# unregister
# ----------------------------------------------------------------------


def test_unregister_removes_marker_block(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"editor": {"theme": "dark"}}\n')
    reg.register_server(_spec())
    assert '"headroom"' in cfg.read_text()

    assert reg.unregister_server("headroom") is True
    text = cfg.read_text()
    assert "// --- Headroom MCP server ---" not in text
    assert '"editor"' in text


def test_unregister_serena_preserves_headroom_block(tmp_path: Path) -> None:
    reg = _make_registrar(tmp_path)
    reg.register_server(_spec())
    reg.register_server(_serena_spec())

    assert reg.unregister_server("serena") is True
    text = _config_path(tmp_path).read_text()
    assert '"headroom"' in text
    assert "// --- Headroom MCP server ---" in text
    assert "// --- Headroom MCP server: serena ---" not in text


def test_unregister_returns_false_when_no_block(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"editor": {"theme": "dark"}}\n')
    assert _make_registrar(tmp_path).unregister_server("headroom") is False


def test_unregister_preserves_user_managed_entry(tmp_path: Path) -> None:
    cfg = _config_path(tmp_path)
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{\n'
        '  "mcp": {\n'
        '    "servers": {\n'
        '      "headroom": {\n'
        '        "type": "local",\n'
        '        "command": ["/custom/headroom"]\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    assert _make_registrar(tmp_path).unregister_server("headroom") is False
    assert "/custom/headroom" in cfg.read_text()


# ----------------------------------------------------------------------
# Round-trip: write -> re-read produces equivalent ServerSpec
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [
        ServerSpec(name="headroom", command="headroom", args=("mcp", "serve")),
        ServerSpec(
            name="headroom",
            command="headroom",
            args=("mcp", "serve"),
            env={"HEADROOM_PROXY_URL": "http://127.0.0.1:9000"},
        ),
        ServerSpec(name="headroom", command="/usr/bin/headroom", args=()),
    ],
)
def test_round_trip(tmp_path: Path, spec: ServerSpec) -> None:
    reg = _make_registrar(tmp_path)
    reg.register_server(spec)
    got = reg.get_server("headroom")
    assert got is not None
    assert got.command == spec.command
    assert got.args == spec.args
    assert got.env == spec.env
