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
