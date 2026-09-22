# jevmcp

Plugins that let coding agents — **Claude Code**, **OpenAI Codex**, and other clients of the
portable [Agent Plugins](https://agent-plugins.org) format — use TypeSafe's fast model **Jev** as
routine tooling across the software lifecycle. The fast model screens everything in seconds and
for fractions of a cent; the agent spends its own effort only on what the fast model flags.

## Plugins

| Plugin | What it does |
|---|---|
| [docdrift](plugins/docdrift) | Checks code against its design spec or requirements. Jev screens every requirement against the code that implements it; the agent investigates only what it flags and says which side to fix. A skill plus an MCP server; Java/Spring, JavaScript/TypeScript, Python, and any language by line range. |

More tools (code audit, CI/CD failure analysis) are planned as further plugins in this
marketplace; each is installed on its own.

## Install

You need [`uv`](https://docs.astral.sh/uv/) and a TypeSafe API key
(<https://console.typesafe.ai>).

**Claude Code**

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install docdrift@jevmcp
```

Claude Code asks for the API key when the plugin is enabled and keeps it in its credential store.

**OpenAI Codex**

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add docdrift@jevmcp
```

Codex forwards `TYPESAFE_API_KEY` from the environment that starts it.

**Other Agent Plugins clients**: each folder under `plugins/` is a portable Agent Plugins 1.0.0
package (`plugin.json`, `mcp.json`, `skills/`). See the plugin's README for how it gets its key.

## Your API key stays yours

No key is stored in this repository, and none should ever be: the plugins' MCP servers read the
key from the client's own settings, from your environment, or from the plugin's data folder on
your machine — never from a file in this repository or in the project being checked. Never paste a
key into an issue or pull request.

## Repository layout

```
.claude-plugin/marketplace.json    the marketplace, as Claude Code reads it
.agents/plugins/marketplace.json   the same marketplace, as Codex reads it
plugins/<name>/                    one self-contained plugin per folder
```

## Support

- Questions and bugs: [GitHub Issues](https://github.com/eaisdevelopment/jevmcp/issues)
- Security problems: [SECURITY.md](SECURITY.md)

## License

[Apache-2.0](LICENSE)
