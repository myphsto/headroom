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
