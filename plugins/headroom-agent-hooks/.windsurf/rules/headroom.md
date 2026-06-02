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
