# jevmcp

Plugins that let coding agents — **Claude Code**, **OpenAI Codex**, and other clients of the
portable [Agent Plugins](https://agent-plugins.org) format — use TypeSafe's fast model **Jev** as
routine tooling across the software lifecycle. The fast model screens everything in seconds and
for fractions of a cent; the agent spends its own effort only on what the fast model flags.

## One plugin, installed once

Everything lives in a single plugin, **jevmcp**. Install it once; new tools arrive as updates, with
no second install and no second API key.

| Tool | What it does | Status |
|---|---|---|
| **spec-drift** (skill) + **docdrift** (MCP server: `check_drift`, `validate_map`, `show_payload`, `draft_map`) | Checks code against its design spec or requirements. Jev screens every requirement against the code that implements it; the agent investigates only what it flags and says which side to fix. Java/Spring, JavaScript/TypeScript, Python, and any language by line range. | available |
| CI failure triage | Reads a failed pipeline and says what actually broke. | planned |
| Code audit | Screens a codebase against its own rules and conventions. | planned |

Each tool is its own skill and its own MCP server inside the plugin, so one cannot break another,
and each can be approved separately by your client.

## Install

You need [`uv`](https://docs.astral.sh/uv/) and a TypeSafe API key
(<https://console.typesafe.ai>).

**Claude Code**

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jevmcp
```

Claude Code asks for the API key when the plugin is enabled and keeps it in its credential store.

**OpenAI Codex**

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jevmcp
```

Codex forwards `TYPESAFE_API_KEY` from the environment that starts it.

**Other Agent Plugins clients**: `plugins/jevmcp` is a portable Agent Plugins 1.0.0 package
(`plugin.json`, `mcp.json`, `skills/`). See the [plugin's README](plugins/jevmcp) for how it gets
its key.

**Updating**: `claude plugin update jevmcp@jevmcp`, or in Codex
`codex plugin remove jevmcp@jevmcp && codex plugin add jevmcp@jevmcp`.

## Your API key stays yours

No key is stored in this repository, and none should ever be: the plugins' MCP servers read the
key from the client's own settings, from your environment, or from the plugin's data folder on
your machine — never from a file in this repository or in the project being checked. Never paste a
key into an issue or pull request.

## Repository layout

```
.claude-plugin/marketplace.json    the marketplace, as Claude Code reads it
.agents/plugins/marketplace.json   the same marketplace, as Codex reads it
plugins/jevmcp/                    the plugin: skills/<tool>/SKILL.md, scripts/, one MCP server per tool
```

## Support

- Questions and bugs: [GitHub Issues](https://github.com/eaisdevelopment/jevmcp/issues)
- Security problems: [SECURITY.md](SECURITY.md)

## License

[Apache-2.0](LICENSE)
