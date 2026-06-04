"""OpenCode runtime helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping

DEFAULT_API_URL = "https://api.opencode.ai"


def proxy_base_url(port: int) -> str:
    """Return the proxy base URL for OpenCode."""
    return f"http://127.0.0.1:{port}/v1"


def build_launch_env(
    port: int, environ: Mapping[str, str] | None = None
) -> tuple[dict[str, str], list[str]]:
    """Build environment variables for OpenCode through the local proxy."""
    env = dict(environ or os.environ)
    base_url = proxy_base_url(port)
    # Opencode doesn't read OPENAI_BASE_URL — proxy routing is done via config injection
    env["HEADROOM_PROXY_PORT"] = str(port)
    return env, [f"HEADROOM_PROXY_PORT={port}"]
