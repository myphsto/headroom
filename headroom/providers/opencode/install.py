"""OpenCode install-time helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from headroom.install.models import ConfigScope, DeploymentManifest, ManagedMutation, ToolTarget
from headroom.install.paths import opencode_config_path, opencode_plugins_path
from headroom.mcp_registry.opencode import _strip_jsonc

from .runtime import proxy_base_url


def build_install_env(*, port: int, backend: str) -> dict[str, str]:
    """Build the persistent install environment for OpenCode."""
    del backend
    return {"HEADROOM_PROXY_PORT": str(port)}


def apply_provider_scope(manifest: DeploymentManifest) -> ManagedMutation | None:
    """Rewrite OpenCode provider URLs to route through the Headroom proxy."""
    if manifest.scope != ConfigScope.PROVIDER.value:
        return None

    path = opencode_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))

    proxy_url = proxy_base_url(manifest.port)
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return None

    original_urls: dict[str, str] = {}
    for name, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue
        api = provider_config.get("api")
        if not isinstance(api, dict):
            continue
        base_url = api.get("url")
        if base_url and isinstance(base_url, str) and base_url != proxy_url:
            original_urls[name] = base_url
            api["url"] = proxy_url

    if not original_urls:
        return None

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ManagedMutation(
        target=ToolTarget.OPENCODE.value,
        kind="json-api-url",
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
    """Revert OpenCode provider URLs to original values."""
    del manifest
    if not mutation.path:
        return
    path = Path(mutation.path)
    if not path.exists():
        return
    payload = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    original_urls: dict[str, str] = mutation.data.get("original_urls", {})
    if not original_urls:
        return
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return
    for name, original_url in original_urls.items():
        provider_config = providers.get(name)
        if not isinstance(provider_config, dict):
            continue
        api = provider_config.get("api")
        if not isinstance(api, dict):
            continue
        api["url"] = original_url
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
