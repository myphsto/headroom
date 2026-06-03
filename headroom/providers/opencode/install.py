"""OpenCode install-time helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from headroom.install.models import DeploymentManifest, ManagedMutation, ToolTarget
from headroom.install.paths import opencode_config_path, opencode_plugins_path

from .runtime import proxy_base_url


def build_install_env(*, port: int, backend: str) -> dict[str, str]:
    """Build the persistent install environment for OpenCode."""
    del backend
    return {"OPENAI_BASE_URL": proxy_base_url(port)}


def apply_provider_scope(manifest: DeploymentManifest) -> ManagedMutation | None:
    """Rewrite OpenCode provider baseURL to route through the Headroom proxy."""
    path = opencode_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(path.read_text())

    proxy_url = proxy_base_url(manifest.port)
    providers = payload.get("provider")
    if not isinstance(providers, dict):
        return None

    original_urls = {}
    for name, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue
        options = provider_config.get("options", {})
        if not isinstance(options, dict):
            continue
        base_url = options.get("baseURL")
        if base_url and isinstance(base_url, str) and base_url != proxy_url:
            original_urls[name] = base_url
            options["baseURL"] = proxy_url

    if not original_urls:
        return None

    path.write_text(json.dumps(payload, indent=2) + "\n")
    return ManagedMutation(
        target=ToolTarget.OPENCODE.value,
        kind="json-baseurl",
        path=str(path),
        data={"original_urls": original_urls},
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
    """Revert OpenCode provider baseURL to original values."""
    if not mutation.path:
        return
    path = Path(mutation.path)
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    original_urls = mutation.data.get("original_urls", {})
    if not original_urls:
        return
    providers = payload.get("provider")
    if not isinstance(providers, dict):
        return
    for name, original_url in original_urls.items():
        provider_config = providers.get(name)
        if not isinstance(provider_config, dict):
            continue
        options = provider_config.get("options", {})
        if not isinstance(options, dict):
            continue
        options["baseURL"] = original_url
    path.write_text(json.dumps(payload, indent=2) + "\n")
