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
