"""OpenCode runtime helpers."""

DEFAULT_API_URL = "https://api.opencode.ai"


def proxy_base_url(port: int) -> str:
    """Return the proxy base URL for OpenCode."""
    return f"http://127.0.0.1:{port}/v1"
