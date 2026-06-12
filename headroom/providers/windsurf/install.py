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
