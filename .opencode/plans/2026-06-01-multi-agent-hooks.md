# Multi-Agent Hook Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add headroom agent hook support for opencode (JS plugin), Gemini CLI (extension package), and Windsurf (proxy rule).

**Architecture:** Each agent gets a provider module under `headroom/providers/`, init command under `headroom/cli/init.py`, and plugin/extension files under `plugins/headroom-agent-hooks/`. The existing hook infrastructure (`headroom init hook ensure`) is reused.

**Tech Stack:** Python (Click CLI), JavaScript (opencode plugin), JSON (Gemini extension), Markdown (Windsurf rule).

---

## Research Summary

| Agent | Hook System | Config Path | Hook Events | Approach |
|-------|------------|-------------|-------------|----------|
| opencode | JS/TS plugins | `.opencode/plugins/` or `~/.config/opencode/plugins/` | `session.created`, `tool.execute.before`, `shell.env` | JS plugin file |
| Gemini CLI | Extension + hooks | `~/.gemini/extensions/` + `hooks/hooks.json` | `SessionStart`, `BeforeTool` | Extension package |
| Windsurf | Rules/Skills (no hooks) | `.windsurf/rules/*.md` | N/A | Proxy Rule file |
| Codex | hooks.json + config.toml | `.codex/hooks.json` | `SessionStart`, `PreToolUse` | Already supported |
| Claude | settings.json hooks | `.claude/settings.json` | `SessionStart`, `PreToolUse` | Already supported |

---

## File Structure

### New files
- `headroom/providers/opencode/__init__.py` - opencode provider helpers
- `headroom/providers/opencode/install.py` - opencode install-time helpers
- `headroom/providers/opencode/runtime.py` - opencode runtime helpers
- `headroom/providers/gemini/install.py` - gemini install-time helpers
- `headroom/providers/windsurf/__init__.py` - windsurf provider helpers
- `headroom/providers/windsurf/install.py` - windsurf install-time helpers
- `plugins/headroom-agent-hooks/.opencode/plugin/headroom-plugin.js` - opencode JS plugin
- `plugins/headroom-agent-hooks/.gemini-extension/gemini-extension.json` - gemini extension manifest
- `plugins/headroom-agent-hooks/.gemini-extension/hooks/hooks.json` - gemini hooks config
- `plugins/headroom-agent-hooks/.windsurf/rules/headroom.md` - windsurf proxy rule

### Modified files
- `headroom/install/models.py` - add `OPENCODE`, `GEMINI`, `WINDSURF` to `ToolTarget`
- `headroom/install/paths.py` - add path helpers
- `headroom/cli/init.py` - add init commands and dispatch logic
- `plugins/headroom-agent-hooks/README.md` - update for new agents
- `README.md` - update agent compatibility matrix

---

## Task 1: Add ToolTarget enum values

**Files:**
- Modify: `headroom/install/models.py:50-58`

- [ ] **Step 1: Add new ToolTarget values**

```python
class ToolTarget(str, Enum):
    """Supported tool targets for persistent proxy wiring."""

    CLAUDE = "claude"
    COPILOT = "copilot"
    CODEX = "codex"
    AIDER = "aider"
    CURSOR = "cursor"
    OPENCLAW = "openclaw"
    OPENCODE = "opencode"
    GEMINI = "gemini"
    WINDSURF = "windsurf"
```

- [ ] **Step 2: Commit**

```bash
git add headroom/install/models.py
git commit -m "feat: add opencode, gemini, windsurf to ToolTarget enum"
```

---

## Task 2: Add install path helpers

**Files:**
- Modify: `headroom/install/paths.py`

- [ ] **Step 1: Add path helper functions after `openclaw_config_path()`**

```python
def opencode_config_path() -> Path:
    """Return the opencode global config path."""
    return Path.home() / ".config" / "opencode" / "opencode.json"


def opencode_plugins_path() -> Path:
    """Return the opencode global plugins directory."""
    return Path.home() / ".config" / "opencode" / "plugins"


def gemini_settings_path() -> Path:
    """Return the Gemini CLI user settings path."""
    return Path.home() / ".gemini" / "settings.json"


def gemini_extensions_path() -> Path:
    """Return the Gemini CLI extensions directory."""
    return Path.home() / ".gemini" / "extensions"


def windsurf_rules_path() -> Path:
    """Return the Windsurf workspace rules directory."""
    return Path.cwd() / ".windsurf" / "rules"


def windsurf_global_rules_path() -> Path:
    """Return the Windsurf global rules path."""
    return Path.home() / ".codeium" / "windsurf" / "memories" / "global_rules.md"
```

- [ ] **Step 2: Commit**

```bash
git add headroom/install/paths.py
git commit -m "feat: add path helpers for opencode, gemini, windsurf"
```

---

## Task 3: Create opencode provider module

**Files:**
- Create: `headroom/providers/opencode/__init__.py`
- Create: `headroom/providers/opencode/install.py`
- Create: `headroom/providers/opencode/runtime.py`

- [ ] **Step 1: Create `headroom/providers/opencode/__init__.py`**

```python
"""OpenCode-specific provider helpers."""

from .runtime import DEFAULT_API_URL

__all__ = ["DEFAULT_API_URL"]
```

- [ ] **Step 2: Create `headroom/providers/opencode/runtime.py`**

```python
"""OpenCode runtime helpers."""

DEFAULT_API_URL = "https://api.opencode.ai"


def proxy_base_url(port: int) -> str:
    """Return the proxy base URL for OpenCode."""
    return f"http://127.0.0.1:{port}/v1"
```

- [ ] **Step 3: Create `headroom/providers/opencode/install.py`**

```python
"""OpenCode install-time helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from headroom.install.models import ConfigScope, DeploymentManifest, ManagedMutation, ToolTarget
from headroom.install.paths import opencode_config_path, opencode_plugins_path

from .runtime import proxy_base_url


def build_install_env(*, port: int, backend: str) -> dict[str, str]:
    """Build the persistent install environment for OpenCode."""
    del backend
    return {"OPENAI_BASE_URL": proxy_base_url(port)}


def apply_provider_scope(manifest: DeploymentManifest) -> ManagedMutation | None:
    """Apply OpenCode provider-scope configuration when requested."""
    if manifest.scope != ConfigScope.PROVIDER.value:
        return None

    path = opencode_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(path.read_text())
    values = manifest.tool_envs.get(ToolTarget.OPencode.value, {})
    if values:
        existing_env = payload.get("env", {})
        if isinstance(existing_env, dict):
            existing_env.update(values)
            payload["env"] = existing_env
        else:
            payload["env"] = values
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return ManagedMutation(
        target=ToolTarget.OPencode.value,
        kind="json-env",
        path=str(path),
        data={},
    )


def install_plugin(plugin_source: Path, plugin_name: str) -> bool:
    """Install the headroom JS plugin into opencode plugins directory."""
    dest = opencode_plugins_path()
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"{plugin_name}.js"
    if plugin_source.exists():
        shutil.copy2(str(plugin_source), str(target))
        return True
    return False


def revert_provider_scope(mutation: ManagedMutation, manifest: DeploymentManifest) -> None:
    """Revert OpenCode provider-scope configuration."""
    if not mutation.path:
        return
    path = Path(mutation.path)
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    env = payload.get("env")
    if isinstance(env, dict):
        values = manifest.tool_envs.get(ToolTarget.OPencode.value, {})
        for name in values:
            env.pop(name, None)
        payload["env"] = env
    path.write_text(json.dumps(payload, indent=2) + "\n")
```

- [ ] **Step 4: Commit**

```bash
git add headroom/providers/opencode/
git commit -m "feat: add opencode provider module with install helpers"
```

---

## Task 4: Create Gemini CLI provider install module

**Files:**
- Create: `headroom/providers/gemini/install.py`

- [ ] **Step 1: Create `headroom/providers/gemini/install.py`**

```python
"""Gemini CLI install-time helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from headroom.install.models import ConfigScope, DeploymentManifest, ManagedMutation, ToolTarget
from headroom.install.paths import gemini_extensions_path, gemini_settings_path

from headroom.providers.codex.runtime import proxy_base_url


def build_install_env(*, port: int, backend: str) -> dict[str, str]:
    """Build the persistent install environment for Gemini CLI."""
    del backend
    return {"OPENAI_BASE_URL": proxy_base_url(port)}


def apply_provider_scope(manifest: DeploymentManifest) -> ManagedMutation | None:
    """Apply Gemini CLI provider-scope configuration when requested."""
    if manifest.scope != ConfigScope.PROVIDER.value:
        return None

    path = gemini_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(path.read_text())
    values = manifest.tool_envs.get(ToolTarget.GEMINI.value, {})
    if values:
        existing_env = payload.get("env", {})
        if isinstance(existing_env, dict):
            existing_env.update(values)
            payload["env"] = existing_env
        else:
            payload["env"] = values
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return ManagedMutation(
        target=ToolTarget.GEMINI.value,
        kind="json-env",
        path=str(path),
        data={},
    )


def install_extension(extension_source: Path) -> bool:
    """Install the headroom Gemini CLI extension."""
    dest = gemini_extensions_path() / "headroom"
    dest.mkdir(parents=True, exist_ok=True)
    if extension_source.is_dir():
        for item in extension_source.iterdir():
            if item.is_file():
                shutil.copy2(str(item), str(dest / item.name))
            else:
                shutil.copytree(str(item), str(dest / item.name), dirs_exist_ok=True)
        return True
    return False


def revert_provider_scope(mutation: ManagedMutation, manifest: DeploymentManifest) -> None:
    """Revert Gemini CLI provider-scope configuration."""
    if not mutation.path:
        return
    path = Path(mutation.path)
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    env = payload.get("env")
    if isinstance(env, dict):
        values = manifest.tool_envs.get(ToolTarget.GEMINI.value, {})
        for name in values:
            env.pop(name, None)
        payload["env"] = env
    path.write_text(json.dumps(payload, indent=2) + "\n")
```

- [ ] **Step 2: Commit**

```bash
git add headroom/providers/gemini/install.py
git commit -m "feat: add gemini CLI provider install helpers"
```

---

## Task 5: Create Windsurf provider module

**Files:**
- Create: `headroom/providers/windsurf/__init__.py`
- Create: `headroom/providers/windsurf/install.py`

- [ ] **Step 1: Create `headroom/providers/windsurf/__init__.py`**

```python
"""Windsurf-specific provider helpers."""

__all__ = []
```

- [ ] **Step 2: Create `headroom/providers/windsurf/install.py`**

```python
"""Windsurf install-time helpers."""

from __future__ import annotations

from pathlib import Path

from headroom.install.models import ConfigScope, DeploymentManifest, ManagedMutation, ToolTarget

from headroom.install.paths import windsurf_rules_path


def build_install_env(*, port: int, backend: str) -> dict[str, str]:
    """Build the persistent install environment for Windsurf.

    Windsurf doesn't use env vars for proxy routing directly,
    so we return an empty dict. Proxy config is done via Rules.
    """
    del port
    del backend
    return {}


def apply_provider_scope(manifest: DeploymentManifest) -> ManagedMutation | None:
    """Apply Windsurf provider-scope configuration when requested."""
    if manifest.scope != ConfigScope.PROVIDER.value:
        return None

    path = windsurf_rules_path()
    path.mkdir(parents=True, exist_ok=True)
    rule_file = path / "headroom.md"
    rule_content = (
        "---\n"
        "trigger: always_on\n"
        "---\n"
        "\n"
        "# Headroom Proxy\n"
        "\n"
        "When making API calls, route requests through the Headroom compression proxy.\n"
        f"The proxy is running at http://127.0.0.1:{manifest.port}/v1.\n"
    )
    rule_file.write_text(rule_content)
    return ManagedMutation(
        target=ToolTarget.WINDSURF.value,
        kind="rule-file",
        path=str(rule_file),
        data={},
    )


def revert_provider_scope(mutation: ManagedMutation, manifest: DeploymentManifest) -> None:
    """Revert Windsurf provider-scope configuration."""
    del manifest
    if not mutation.path:
        return
    path = Path(mutation.path)
    if path.exists():
        path.unlink()
```

- [ ] **Step 3: Commit**

```bash
git add headroom/providers/windsurf/
git commit -m "feat: add windsurf provider module with rule-based install"
```

---

## Task 6: Create opencode JS plugin

**Files:**
- Create: `plugins/headroom-agent-hooks/.opencode/plugin/headroom-plugin.js`

- [ ] **Step 1: Create the plugin file**

```javascript
/**
 * Headroom plugin for OpenCode
 * Ensures the Headroom compression proxy is running before tool execution.
 */
export const HeadroomPlugin = async ({ project, client, $, directory, worktree }) => {
  const HEADROOM_MARKER = "headroom-init-opencode";
  let proxyStarted = false;

  async function ensureHeadroomRunning() {
    if (proxyStarted) return;

    try {
      const healthCheck = await $`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8787/readyz`
        .nothrow()
        .timeout(3000);

      if (healthCheck.stdout.trim() === "200") {
        proxyStarted = true;
        return;
      }
    } catch {
      // Health check failed, try to start headroom
    }

    try {
      await $`headroom init hook ensure --marker ${HEADROOM_MARKER}`
        .nothrow()
        .timeout(15000);
      proxyStarted = true;
    } catch (err) {
      await client.app.log({
        body: {
          service: "headroom-plugin",
          level: "debug",
          message: "Failed to ensure headroom proxy: " + (err.message || err),
        },
      });
    }
  }

  return {
    "session.created": async () => {
      await ensureHeadroomRunning();
      await client.app.log({
        body: {
          service: "headroom-plugin",
          level: "info",
          message: "Headroom plugin initialized",
          extra: { project: project?.name, directory },
        },
      });
    },

    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash" || input.tool === "shell") {
        await ensureHeadroomRunning();
      }
    },

    "shell.env": async (input, output) => {
      output.env.HEADROOM_MARKER = HEADROOM_MARKER;
      output.env.HEADROOM_PROJECT_DIR = input.cwd || directory;
    },
  };
};
```

- [ ] **Step 2: Commit**

```bash
git add plugins/headroom-agent-hooks/.opencode/
git commit -m "feat: add opencode JS plugin for headroom proxy integration"
```

---

## Task 7: Create Gemini CLI extension package

**Files:**
- Create: `plugins/headroom-agent-hooks/.gemini-extension/gemini-extension.json`
- Create: `plugins/headroom-agent-hooks/.gemini-extension/hooks/hooks.json`

- [ ] **Step 1: Create extension manifest**

```json
{
  "name": "headroom",
  "version": "0.22.3",
  "description": "Headroom compression proxy integration for Gemini CLI. Ensures the local Headroom runtime is available and routes API calls through the compression proxy.",
  "contextFileName": "GEMINI.md"
}
```

- [ ] **Step 2: Create hooks config**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "name": "headroom-ensure",
            "type": "command",
            "command": "headroom init hook ensure --marker headroom-init-gemini",
            "timeout": 15000,
            "description": "Ensure Headroom compression proxy is running"
          }
        ]
      }
    ],
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "hooks": [
          {
            "name": "headroom-ensure-before-tool",
            "type": "command",
            "command": "headroom init hook ensure --marker headroom-init-gemini",
            "timeout": 15000,
            "description": "Ensure Headroom proxy before shell execution"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add plugins/headroom-agent-hooks/.gemini-extension/
git commit -m "feat: add gemini CLI extension package with hooks"
```

---

## Task 8: Create Windsurf proxy rule

**Files:**
- Create: `plugins/headroom-agent-hooks/.windsurf/rules/headroom.md`

- [ ] **Step 1: Create the rule file**

```markdown
---
trigger: always_on
---

# Headroom Compression Proxy

When making external API calls or tool calls that could benefit from context compression,
be aware that the Headroom compression proxy may be available.

If the environment variable `HEADROOM_PROXY_URL` is set, use it as the base URL for
API routing. Otherwise, the default proxy runs at `http://127.0.0.1:8787/v1`.

This rule ensures that Windsurf Cascade is aware of the Headroom compression layer
for token optimization during long coding sessions.
```

- [ ] **Step 2: Commit**

```bash
git add plugins/headroom-agent-hooks/.windsurf/
git commit -m "feat: add windsurf proxy rule for headroom awareness"
```

---

## Task 9: Add init commands for new agents

**Files:**
- Modify: `headroom/cli/init.py`

- [ ] **Step 1: Update `_SUPPORTED_TARGETS` and scope sets (line 46-48)**

```python
_SUPPORTED_TARGETS = ("claude", "copilot", "codex", "openclaw", "opencode", "gemini", "windsurf")
_LOCAL_TARGETS = {"claude", "codex", "opencode", "windsurf"}
_GLOBAL_TARGETS = {"claude", "copilot", "codex", "openclaw", "opencode", "gemini", "windsurf"}
```

- [ ] **Step 2: Add hook markers after line 45**

```python
_OPENCODE_HOOK_MARKER = "headroom-init-opencode"
_GEMINI_HOOK_MARKER = "headroom-init-gemini"
_WINDSURF_RULE_MARKER = "headroom-init-windsurf"
```

- [ ] **Step 3: Add helper functions after `_codex_hooks_path`**

```python
def _opencode_hooks_path(global_scope: bool) -> Path:
    return (
        Path.home() / ".config" / "opencode" / "plugins"
        if global_scope
        else Path.cwd() / ".opencode" / "plugins"
    )


def _gemini_hooks_path(global_scope: bool) -> Path:
    return (
        Path.home() / ".gemini"
        if global_scope
        else Path.cwd() / ".gemini"
    )


def _windsurf_rules_path_local() -> Path:
    return Path.cwd() / ".windsurf" / "rules"
```

- [ ] **Step 4: Add `_ensure_opencode_hooks` function**

```python
def _ensure_opencode_hooks(path: Path, profile: str) -> None:
    logger.debug("ensure opencode hooks: %s (profile=%s)", path, profile)
    command = f"{_hook_command('--profile', profile)} --marker {_OPENCODE_HOOK_MARKER}"
    plugin_file = path / "headroom-plugin.js"
    repo_root = Path(__file__).resolve().parents[2]
    source_plugin = repo_root / "plugins" / "headroom-agent-hooks" / ".opencode" / "plugin" / "headroom-plugin.js"
    if source_plugin.exists():
        import shutil
        shutil.copy2(str(source_plugin), str(plugin_file))
```

- [ ] **Step 5: Add `_ensure_gemini_hooks` function**

```python
def _ensure_gemini_hooks(path: Path, profile: str) -> None:
    logger.debug("ensure gemini hooks: %s (profile=%s)", path, profile)
    command = f"{_hook_command('--profile', profile)} --marker {_GEMINI_HOOK_MARKER}"
    hooks_file = path / "settings.json"
    payload = _json_file(hooks_file)
    hooks = dict(payload.get("hooks") or {}) if isinstance(payload.get("hooks"), dict) else {}

    for event, matcher in (
        ("SessionStart", "startup|resume"),
        ("BeforeTool", "run_shell_command"),
    ):
        entries = list(hooks.get(event) or []) if isinstance(hooks.get(event), list) else []
        retained = [
            entry
            for entry in entries
            if not (
                isinstance(entry, dict) and _GEMINI_HOOK_MARKER in str(entry.get("command", ""))
            )
        ]
        retained.append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "name": "headroom-ensure",
                        "type": "command",
                        "command": command,
                        "timeout": 15000,
                    }
                ],
            }
        )
        hooks[event] = retained
    payload["hooks"] = hooks
    _write_json(hooks_file, payload)
```

- [ ] **Step 6: Add `_ensure_windsurf_rule` function**

```python
def _ensure_windsurf_rule(path: Path, port: int) -> None:
    logger.debug("ensure windsurf rule: %s (port=%s)", path, port)
    rule_file = path / "headroom.md"
    rule_content = (
        "---\n"
        "trigger: always_on\n"
        "---\n"
        "\n"
        "# Headroom Compression Proxy\n"
        "\n"
        "When making external API calls or tool calls that could benefit from context compression,\n"
        "be aware that the Headroom compression proxy may be available.\n"
        "\n"
        f"The proxy is running at http://127.0.0.1:{port}/v1.\n"
    )
    path.mkdir(parents=True, exist_ok=True)
    rule_file.write_text(rule_content)
```

- [ ] **Step 7: Add `_init_opencode` function**

```python
def _init_opencode(*, global_scope: bool, profile: str, port: int) -> None:
    plugins_path = _opencode_hooks_path(global_scope)
    _ensure_opencode_hooks(plugins_path, profile)
    click.echo(f"Configured OpenCode ({'user' if global_scope else 'local'} scope).")
    click.echo("Restart OpenCode to activate Headroom plugin.")
```

- [ ] **Step 8: Add `_init_gemini` function**

```python
def _init_gemini(*, global_scope: bool, profile: str, port: int) -> None:
    gemini_path = _gemini_hooks_path(global_scope)
    _ensure_gemini_hooks(gemini_path, profile)
    repo_root = Path(__file__).resolve().parents[2]
    ext_source = repo_root / "plugins" / "headroom-agent-hooks" / ".gemini-extension"
    if ext_source.exists():
        import shutil
        ext_dest = (Path.home() / ".gemini" / "extensions" / "headroom") if global_scope else (Path.cwd() / ".gemini" / "extensions" / "headroom")
        ext_dest.mkdir(parents=True, exist_ok=True)
        for item in ext_source.iterdir():
            if item.is_file():
                shutil.copy2(str(item), str(ext_dest / item.name))
            else:
                shutil.copytree(str(item), str(ext_dest / item.name), dirs_exist_ok=True)
    click.echo(f"Configured Gemini CLI ({'user' if global_scope else 'local'} scope).")
    click.echo("Restart Gemini CLI to activate Headroom hooks.")
```

- [ ] **Step 9: Add `_init_windsurf` function**

```python
def _init_windsurf(*, global_scope: bool, profile: str, port: int) -> None:
    del profile
    rules_path = _windsurf_rules_path_local()
    _ensure_windsurf_rule(rules_path, port)
    click.echo("Configured Windsurf workspace rules.")
    click.echo("Restart Windsurf to activate Headroom proxy rule.")
```

- [ ] **Step 10: Update `_run_init_targets` dispatch loop**

Add after the `openclaw` case:
```python
        elif target == "opencode":
            _init_opencode(global_scope=global_scope, profile=profile, port=port)
        elif target == "gemini":
            _init_gemini(global_scope=global_scope, profile=profile, port=port)
        elif target == "windsurf":
            _init_windsurf(global_scope=global_scope, profile=profile, port=port)
```

- [ ] **Step 11: Add Click commands after `init_openclaw`**

```python
@init.command("opencode")
@click.pass_context
def init_opencode(ctx: click.Context) -> None:
    """Install OpenCode durable plugin and proxy routing."""
    _run_init_targets(
        targets=["opencode"],
        global_scope=bool(_ctx_value(ctx, "global_scope")),
        port=int(_ctx_value(ctx, "port") or 8787),
        backend=str(_ctx_value(ctx, "backend") or "anthropic"),
        anyllm_provider=_ctx_value(ctx, "anyllm_provider"),
        region=_ctx_value(ctx, "region"),
        memory=bool(_ctx_value(ctx, "memory")),
    )


@init.command("gemini")
@click.pass_context
def init_gemini(ctx: click.Context) -> None:
    """Install Gemini CLI durable hooks and proxy routing."""
    _run_init_targets(
        targets=["gemini"],
        global_scope=bool(_ctx_value(ctx, "global_scope")),
        port=int(_ctx_value(ctx, "port") or 8787),
        backend=str(_ctx_value(ctx, "backend") or "anthropic"),
        anyllm_provider=_ctx_value(ctx, "anyllm_provider"),
        region=_ctx_value(ctx, "region"),
        memory=bool(_ctx_value(ctx, "memory")),
    )


@init.command("windsurf")
@click.pass_context
def init_windsurf(ctx: click.Context) -> None:
    """Install Windsurf proxy rule."""
    _run_init_targets(
        targets=["windsurf"],
        global_scope=bool(_ctx_value(ctx, "global_scope")),
        port=int(_ctx_value(ctx, "port") or 8787),
        backend=str(_ctx_value(ctx, "backend") or "anthropic"),
        anyllm_provider=_ctx_value(ctx, "anyllm_provider"),
        region=_ctx_value(ctx, "region"),
        memory=bool(_ctx_value(ctx, "memory")),
    )
```

- [ ] **Step 12: Verify syntax**

```bash
python -c "import headroom.cli.init" 2>&1
```

- [ ] **Step 13: Commit**

```bash
git add headroom/cli/init.py
git commit -m "feat: add init commands for opencode, gemini, windsurf"
```

---

## Task 10: Update documentation

**Files:**
- Modify: `plugins/headroom-agent-hooks/README.md`
- Modify: `README.md`

- [ ] **Step 1: Update agent hooks README**

Replace `plugins/headroom-agent-hooks/README.md`:

```markdown
# Headroom agent hooks

This plugin exposes lightweight startup hooks for Claude Code, GitHub Copilot CLI, OpenCode, Gemini CLI, and Windsurf.

The hooks call:

```bash
headroom init hook ensure
```

That hidden helper checks for a matching durable `headroom init` deployment and starts it if needed.

## Supported agents

| Agent | Hook Type | Config Location |
|-------|-----------|----------------|
| Claude Code | settings.json hooks | `.claude/settings.json` |
| GitHub Copilot CLI | config.json hooks | `~/.copilot/config.json` |
| Codex | hooks.json + config.toml | `.codex/hooks.json` |
| OpenCode | JS plugin | `.opencode/plugins/headroom-plugin.js` |
| Gemini CLI | Extension + hooks | `~/.gemini/extensions/headroom/` |
| Windsurf | Rules | `.windsurf/rules/headroom.md` |
```

- [ ] **Step 2: Update README agent compatibility matrix**

Add to the table in `README.md`:

```markdown
| OpenCode    | ●               | JS plugin · `headroom init opencode` |
| Gemini CLI  | ●               | extension · `headroom init gemini` |
| Windsurf    | ●               | proxy rule · `headroom init windsurf` |
```

- [ ] **Step 3: Commit**

```bash
git add plugins/headroom-agent-hooks/README.md README.md
git commit -m "docs: update agent compatibility for opencode, gemini, windsurf"
```

---

## Task 11: Run tests and verify

- [ ] **Step 1: Run existing tests**

```bash
pytest tests/ -x -v --tb=short -k "init or install or provider" 2>&1 | head -100
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -x -v --tb=short 2>&1 | tail -30
```

- [ ] **Step 3: Verify CLI commands**

```bash
python -m headroom.cli.main init --help 2>&1
```

Expected: `opencode`, `gemini`, `windsurf` appear as subcommands.

- [ ] **Step 4: Verify plugin files**

```bash
ls -la plugins/headroom-agent-hooks/.opencode/plugin/headroom-plugin.js
ls -la plugins/headroom-agent-hooks/.gemini-extension/
ls -la plugins/headroom-agent-hooks/.windsurf/rules/
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] opencode JS plugin - Task 6 + Task 9
   - [x] Gemini CLI extension - Task 7 + Task 9
   - [x] Windsurf proxy rule - Task 8 + Task 9
   - [x] Init commands for all three - Task 9
   - [x] Documentation updates - Task 10

2. **Placeholder scan:** No "TBD", "TODO", or vague instructions found.

3. **Type consistency:**
   - `ToolTarget` enum values match init command names: `opencode`, `gemini`, `windsurf`
   - Hook markers unique per agent: `headroom-init-opencode`, `headroom-init-gemini`, `headroom-init-windsurf`
   - Path helpers follow naming convention

4. **Existing patterns followed:**
   - Provider modules mirror `headroom/providers/claude/` structure
   - Init commands mirror existing `init_claude`, `init_copilot`, `init_codex` pattern
   - Hook markers follow `_CLAUDE_HOOK_MARKER` naming convention
   - Plugin files in `plugins/headroom-agent-hooks/` alongside existing `.claude-plugin/` and `.github/`
