"""OpenCode MCP registrar.

OpenCode stores MCP server config in ``~/.config/opencode/opencode.jsonc``
as a JSONC object under ``mcp.servers.<name>``.  There is no general-purpose
CLI for adding entries, so we edit the file in place — using
marker-delimited comment blocks so we can idempotently inject, replace,
and remove our entry without disturbing anything else.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .base import MCPRegistrar, RegisterResult, RegisterStatus, ServerSpec

logger = logging.getLogger(__name__)

_MARKER_START = "// --- Headroom MCP server ---"
_MARKER_END = "// --- end Headroom MCP server ---"


def _marker_start(server_name: str) -> str:
    if server_name == "headroom":
        return _MARKER_START
    return f"// --- Headroom MCP server: {server_name} ---"


def _marker_end(server_name: str) -> str:
    if server_name == "headroom":
        return _MARKER_END
    return f"// --- end Headroom MCP server: {server_name} ---"


# ---------------------------------------------------------------------------
# JSONC helpers — strip comments / trailing commas so stdlib json works
# ---------------------------------------------------------------------------

def _strip_jsonc(text: str) -> str:
    """Remove JSONC comments and trailing commas, returning valid JSON."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]

        # String literal — pass through verbatim (handle escapes)
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(text[i:j])
            i = j
            continue

        # Line comment
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.index('\n', i) if '\n' in text[i:] else n
            out.append(' ')
            i = j if j < n else n
            continue

        # Block comment
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.index('*/', i + 2) if '*/' in text[i:] else n - 1
            out.append(' ')
            i = j + 2 if j < n - 1 else n
            continue

        # Trailing comma before } or ]
        if c == ',':
            rest = text[i + 1:].lstrip()
            if rest and rest[0] in '}]':
                i += 1
                continue

        out.append(c)
        i += 1

    return ''.join(out)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def _render_block(spec: ServerSpec, indent: int = 4) -> str:
    """Render a Headroom-marked JSONC block for ``spec``."""
    inner_indent = ' ' * indent
    obj: dict[str, Any] = {
        "type": "local",
        "command": [spec.command] + list(spec.args) if spec.args else [spec.command],
    }
    if spec.env:
        obj["environment"] = dict(spec.env)

    lines: list[str] = [_marker_start(spec.name)]
    lines.append(f'{inner_indent}"{spec.name}": {{')

    items = list(obj.items())
    for idx, (k, v) in enumerate(items):
        comma = ',' if idx < len(items) - 1 else ''
        val = json.dumps(v)
        lines.append(f'{inner_indent * 2}"{k}": {val}{comma}')

    lines.append(f'{inner_indent}}}')
    lines.append(_marker_end(spec.name))
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Registrar
# ---------------------------------------------------------------------------

class OpenCodeRegistrar(MCPRegistrar):
    """Register MCP servers with OpenCode."""

    name = "opencode"
    display_name = "OpenCode"

    def __init__(self, *, home_dir: Path | None = None) -> None:
        home = home_dir if home_dir is not None else Path.home()
        self._config_dir = home / ".config" / "opencode"
        self._config_file = home / ".config" / "opencode" / "opencode.jsonc"

    # ------------------------------------------------------------------
    # MCPRegistrar interface
    # ------------------------------------------------------------------

    def detect(self) -> bool:
        return self._config_dir.is_dir()

    def get_server(self, server_name: str) -> ServerSpec | None:
        data = self._load_jsonc()
        servers = data.get("mcp", {}).get("servers", {})
        if not isinstance(servers, dict):
            return None
        entry = servers.get(server_name)
        if not isinstance(entry, dict):
            return None
        return _entry_to_spec(server_name, entry)

    def register_server(self, spec: ServerSpec, *, force: bool = False) -> RegisterResult:
        existing = self.get_server(spec.name)

        if existing is not None and _specs_equivalent(existing, spec):
            return RegisterResult(RegisterStatus.ALREADY, "matches current configuration")

        if existing is not None and not force:
            content = self._read_text()
            if _marker_start(spec.name) not in content:
                return RegisterResult(
                    RegisterStatus.MISMATCH,
                    f"user-managed mcp.servers.{spec.name} entry outside "
                    f"Headroom markers; {_diff_specs(existing, spec)}",
                )
            return RegisterResult(RegisterStatus.MISMATCH, _diff_specs(existing, spec))

        if existing is not None and force:
            content = self._read_text()
            if _marker_start(spec.name) not in content:
                return RegisterResult(
                    RegisterStatus.MISMATCH,
                    f"user-managed mcp.servers.{spec.name} entry outside "
                    f"Headroom markers; {_diff_specs(existing, spec)}",
                )
            self.unregister_server(spec.name)

        return self._write_block(spec)

    def unregister_server(self, server_name: str) -> bool:
        if not self._config_file.exists():
            return False
        content = self._read_text()
        marker_start = _marker_start(server_name)
        marker_end = _marker_end(server_name)
        if marker_start not in content or marker_end not in content:
            return False
        try:
            start = content.index(marker_start)
            end = content.index(marker_end) + len(marker_end)
        except ValueError:
            return False
        before = content[:start].rstrip('\n')
        after = content[end:].lstrip('\n')
        # Remove trailing comma from before (our block includes its own comma handling)
        if before.endswith(','):
            before = before[:-1]
        if before and after:
            new_content = before + '\n\n' + after
        else:
            new_content = (before or after).rstrip('\n') + ('\n' if (before or after) else '')
        try:
            self._config_file.write_text(new_content)
        except OSError:
            return False
        return True

    # ------------------------------------------------------------------
    # File IO
    # ------------------------------------------------------------------

    def _load_jsonc(self) -> dict[str, Any]:
        if not self._config_file.exists():
            return {}
        try:
            text = self._config_file.read_text()
            cleaned = _strip_jsonc(text)
            data = json.loads(cleaned)
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_text(self) -> str:
        try:
            return self._config_file.read_text()
        except OSError:
            return ""

    def _write_block(self, spec: ServerSpec) -> RegisterResult:
        block = _render_block(spec)
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            content = self._read_text()
            marker_start = _marker_start(spec.name)
            marker_end = _marker_end(spec.name)

            if marker_start in content and marker_end in content:
                # Replace existing marker block
                start = content.index(marker_start)
                end = content.index(marker_end) + len(marker_end)
                before = content[:start].rstrip('\n')
                after = content[end:].lstrip('\n')
                # Remove trailing comma from before
                if before.endswith(','):
                    before = before[:-1]
                if before and after:
                    content = before + '\n\n' + block + '\n\n' + after
                elif before:
                    content = before + '\n\n' + block + '\n' + after
                else:
                    content = block + '\n' + after
            elif content.strip():
                # Append to existing config — inject inside mcp.servers object
                content = self._append_to_servers(content, block)
            else:
                # New file
                content = json.dumps({"mcp": {"servers": {}}}, indent=4) + '\n'
                content = self._append_to_servers(content, block)

            self._config_file.write_text(content)
        except OSError as exc:
            return RegisterResult(
                RegisterStatus.FAILED, f"could not write {self._config_file}: {exc}"
            )
        return RegisterResult(RegisterStatus.REGISTERED, f"wrote to {self._config_file}")

    def _append_to_servers(self, content: str, block: str) -> str:
        """Insert ``block`` inside the ``mcp.servers`` object in ``content``."""
        # Try to find the servers object to insert into
        servers_pattern = re.compile(
            r'"servers"\s*:\s*\{',
            re.DOTALL,
        )
        m = servers_pattern.search(content)
        if m:
            # Find the matching closing brace for the servers object
            servers_start = m.end()  # position after '{'
            brace_depth = 1
            pos = servers_start
            while pos < len(content) and brace_depth > 0:
                if content[pos] == '{':
                    brace_depth += 1
                elif content[pos] == '}':
                    brace_depth -= 1
                elif content[pos] == '"':
                    # Skip string literal
                    pos += 1
                    while pos < len(content) and content[pos] != '"':
                        if content[pos] == '\\':
                            pos += 1
                        pos += 1
                pos += 1
            # pos is now after the closing '}' of servers
            before_close = content[:pos - 1]
            after_close = content[pos - 1:]  # includes the '}'

            # Check if servers object already has content (other entries)
            inner = content[servers_start:pos - 1].strip()
            if inner:
                if not inner.endswith(','):
                    before_close = before_close.rstrip() + ','
                inserted = before_close + '\n' + block + '\n' + after_close
            else:
                inserted = before_close + '\n' + block + '\n' + after_close
            return inserted

        # No servers object found — try mcp object
        mcp_pattern = re.compile(r'"mcp"\s*:\s*\{', re.DOTALL)
        m = mcp_pattern.search(content)
        if m:
            # Add servers object inside mcp
            mcp_start = m.end()
            brace_depth = 1
            pos = mcp_start
            while pos < len(content) and brace_depth > 0:
                if content[pos] == '{':
                    brace_depth += 1
                elif content[pos] == '}':
                    brace_depth -= 1
                elif content[pos] == '"':
                    pos += 1
                    while pos < len(content) and content[pos] != '"':
                        if content[pos] == '\\':
                            pos += 1
                        pos += 1
                pos += 1

            servers_block = '\n'.join([
                '    "servers": {',
                block,
                '    }',
            ])
            before_close = content[:pos - 1]
            after_close = content[pos - 1:]
            inner = content[mcp_start:pos - 1].strip()
            if inner:
                if not inner.endswith(','):
                    before_close = before_close.rstrip() + ','
                inserted = before_close + '\n' + servers_block + '\n' + after_close
            else:
                inserted = before_close + '\n' + servers_block + '\n' + after_close
            return inserted

        # No mcp object at all — parse, merge, and re-serialize
        try:
            data = json.loads(_strip_jsonc(content))
        except json.JSONDecodeError:
            data = {}
        if "mcp" not in data:
            data["mcp"] = {}
        if "servers" not in data["mcp"]:
            data["mcp"]["servers"] = {}

        # Re-serialize with the block injected inside the servers object
        base = json.dumps(data, indent=4)
        inner_m = re.search(r'"servers"\s*:\s*\{', base)
        if inner_m:
            base = base[:inner_m.end()] + '\n' + block + '\n' + base[inner_m.end():]
        return base + '\n'


# ----------------------------------------------------------------------
# Spec conversion helpers (module-private)
# ----------------------------------------------------------------------


def _entry_to_spec(name: str, entry: dict[str, Any]) -> ServerSpec:
    """Convert an opencode server entry dict to a ServerSpec."""
    command_value = entry.get("command", [])
    if isinstance(command_value, list) and command_value:
        command = str(command_value[0])
        args = tuple(str(a) for a in command_value[1:])
    elif isinstance(command_value, str):
        command = command_value
        args = ()
    else:
        command = ""
        args = ()

    env_value = entry.get("environment", {})
    env: dict[str, str] = {}
    if isinstance(env_value, dict):
        env = {str(k): str(v) for k, v in env_value.items()}

    return ServerSpec(name=name, command=command, args=args, env=env)


def _specs_equivalent(a: ServerSpec, b: ServerSpec) -> bool:
    return (
        a.name == b.name
        and a.command == b.command
        and tuple(a.args) == tuple(b.args)
        and dict(a.env) == dict(b.env)
    )


def _diff_specs(existing: ServerSpec, requested: ServerSpec) -> str:
    parts: list[str] = []
    if existing.command != requested.command:
        parts.append(f"command {existing.command!r} -> {requested.command!r}")
    if tuple(existing.args) != tuple(requested.args):
        parts.append(f"args {list(existing.args)} -> {list(requested.args)}")
    if dict(existing.env) != dict(requested.env):
        parts.append(f"env {dict(existing.env)} -> {dict(requested.env)}")
    if not parts:
        return "spec differs in unidentified field(s)"
    return "; ".join(parts)
