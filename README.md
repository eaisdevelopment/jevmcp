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
| **spec-drift** (skill) + tools on the `jevmcp` server (`check_spec_drift`, `validate_spec_map`, `preview_spec_check`, `draft_spec_map`) | Checks code against its design spec or requirements. Jev screens every requirement against the code that implements it; the agent investigates only what it flags and says which side to fix. Java/Spring, JavaScript/TypeScript, Python, and any language by line range. | available |
| CI failure triage | Reads a failed pipeline and says what actually broke. | planned |
| Code audit | Screens a codebase against its own rules and conventions. | planned |

Each tool is its own skill, and all of them share the single `jevmcp` MCP server: one install,
one server process, one API key. Your client can still approve or disable each tool separately.

## What happens the first time (about 5 minutes, once per project)

You do not create or edit any file yourself. In your project, ask your agent:

> Set up spec-drift checking for this project.

1. It finds your spec — a design, requirements or architecture document (Markdown).
2. It runs `draft_spec_map`, which **writes `spec_map.json` for you**: one entry per sentence of the
   spec, each with a suggested place in the code. Nothing is sent anywhere; this is free.
3. It reviews the entries with you, fixes the wrong guesses, and marks sentences that are not
   requirements as excluded with a reason. This is the part that needs your knowledge, and it is
   the only part that takes time.
4. `validate_spec_map` confirms the file is complete, and you commit it with your code.

From then on, a check is one sentence — *"Check my changes against the spec"* — and takes seconds
and fractions of a cent, because each requirement is sent with only the code it is about.

**What is `spec_map.json`?** It is the pairing between your spec and your code: for each sentence,
which code implements it. One entry looks like this (the agent writes it, you review it):

```json
{"spec": "docs/spec.md", "line": 6,
 "text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
 "status": "reviewed",
 "code": ["app/settings.py:SHOP_MAX_ITEMS", "app/services.py:place_order"]}
```

Without it, checking a spec would mean sending your whole repository to a model for every
sentence. With it, the fast model gets one requirement and the few lines that enforce it.

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

Codex has no prompt for keys. Store it once, in your own terminal:

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jevmcp/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key
```

It asks for the key without showing it, writes `~/.config/jevmcp/typesafe.env` (readable only by
you), and survives plugin updates. No file for you to create by hand.

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
