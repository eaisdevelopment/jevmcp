# jevmcp — TypeSafe's fast model as routine tooling for your coding agent

**One plugin, installed once.** It gives **Claude Code** and **OpenAI Codex** (both tested) the
tools that put TypeSafe's fast model **Jev** to work: the fast model screens everything in seconds
and for fractions of a cent, and your agent spends its own effort only on what was flagged. Built
on the portable [Agent Plugins](https://agent-plugins.org) format, so other clients of that format
can load it too.

New tools are added to this same plugin — you do not install or configure anything again, you
update it (`claude plugin update jevmcp@jevmcp`).

## What is in it today

**Spec-drift checking** — does the code still match the project's design spec or requirements
document? Your agent checks after it changes something, and before a release. On a real Java
project (131 requirements): a check after editing two files took 3 seconds and cost $0.0013; a
full check took 11 seconds and cost $0.006.

- **A skill** (`spec-drift`) that teaches the agent the whole workflow: setting up a project,
  checking after every change, reading the results, the fast model's blind spots, and reporting.
- **One MCP server** (`jevmcp`) that today offers four tools — `check_drift`, `validate_map`,
  `show_payload`, `draft_map`. It keeps the parsed code in memory, so after an edit only the
  changed files are read again (a 16,000-file repository: ~2 s instead of ~20 s), and it holds
  your API key so the agent never sees it.

Planned for the same plugin and the same server: CI failure triage, and code audit. Each arrives
as its own skill and its own tools on the `jevmcp` server — one install, one server, one API key,
and they reach you as an update.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on your PATH. The first run installs the Python dependencies
  (tree-sitter, PyYAML) into uv's cache; nothing is installed into your project.
- A TypeSafe API key — get one at <https://console.typesafe.ai>. One key serves every tool in
  the plugin.

## Install

**Claude Code**

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jevmcp
```

Claude Code asks for your TypeSafe API key when the plugin is enabled and keeps it out of every
settings file (in the macOS Keychain, or `~/.claude/.credentials.json` on other systems). To change
it later: `/plugin configure jevmcp`. Enter it at those prompts rather than with
`claude plugin install --config`, which would leave it in your shell history.

**OpenAI Codex**

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jevmcp
```

Codex has no install-time prompt for keys: put `export TYPESAFE_API_KEY=...` in the shell profile
that starts Codex; the plugin forwards that variable to its server. Note that Codex's own shell
tool also inherits your environment, so on Codex the model *could* read an exported key if it
ran `env`; the skill tells it never to.

`check_drift` is marked as a write action, because it sends code out of your machine: Codex asks
you before each check — that is your consent. The free tools (`validate_map`, `show_payload`) can
run without asking if you add to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jevmcp".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

Unattended runs (`codex exec`) need `--approve-for-me`, which routes the approval to Codex's
automatic review. If the server's very first start times out while uv downloads the parsers, run
`uv run --script ~/.codex/plugins/cache/jevmcp/jevmcp/<version>/scripts/jevmcp_server.py --help`
once (uv caches them), then start Codex again; Codex's `config.toml` cannot change a plugin
server's startup timeout.

**Other Agent Plugins clients** (VS Code, GitHub Copilot, Kiro, ...) load the portable core of
this folder — `plugin.json`, `mcp.json`, `skills/` — through their own plugin setup. The portable
format has no secret mechanism (keys must not go in `mcp.json`), so give the server the key either
through `TYPESAFE_API_KEY` in the environment the client passes on, or by putting the line
`TYPESAFE_API_KEY=...` into `typesafe.env` in the plugin's data folder (`PLUGIN_DATA`); if the key
is missing, the server's error message names that exact path. Cursor is not supported yet: it
does not expand the standard's `${PLUGIN_ROOT}`.

## Your API key

Never commit it, and never paste it into an issue or a chat. The MCP server reads it, in this
order, from:

1. `--key-file FILE`, if the server was registered with one (an absolute path; then only from
   that file);
2. the `TYPESAFE_API_KEY` environment variable (Claude Code fills it from the plugin's settings,
   Codex forwards yours);
3. `typesafe.env` in the plugin's data folder (`$PLUGIN_DATA`, or `$CLAUDE_PLUGIN_DATA`).

It never reads a project's own `.env`: a repository you check cannot supply a key. The key is
never placed in the model's context, in tool arguments or in tool results.

## Use it

In any project, ask your agent, for example:

- *"Set up spec-drift checking for this project"* — it finds the spec, drafts a **spec map** that
  pairs each requirement with the code that implements it, reviews every entry with you, and
  validates it. The map (`spec_map.json`) belongs in your repository.
- *"Check my changes against the spec"* — after that, a check is seconds.
- *"Which requirements are about `src/billing/Invoice.java`, and does the code already drift from
  them?"* — before you change something, see what the spec says about it.
- *"Run a full spec-drift check before the release"* — every requirement, with a report of what
  to fix and on which side (code or spec).

The agent also checks by itself after changing code in a project that has a spec map.

## Languages

| Language | Understood |
|---|---|
| Java | classes, methods, constants; Spring routes (class and method mappings, constant paths, API-first interfaces), `@Value`, `@ConfigurationProperties`, `application*.yml/.properties` per profile |
| JavaScript / TypeScript | functions, classes, constants; NestJS, Express, Hono, Fastify (mounts followed across files), Next.js file routes; `process.env`, `import.meta.env` |
| Python | functions, classes, constants; FastAPI, Flask, Django routes; `os.environ`, pydantic settings |
| Also | OpenAPI files; `.env` templates (never a real `.env`) |
| Any other language | by line range (`src/main.go:120-160`) or a small whole file |

## What is sent, and what never is

Each check sends, per requirement, to `api.typesafe.ai`: the spec sentence; the code paired with
it, with **comments removed** (Python, Java, JavaScript/TypeScript and other C-family languages;
other files are sent as written), **secret-looking values redacted** and **paths relative to your
project**; and three fixed questions. A `.env` file, key files, and anything outside the project
are refused, never sent. The agent asks for your consent before the first check in a project, and
`show_payload` (or `--dry-run --show-payload`) shows exactly what would be sent, without sending
it. [PRIVACY.md](PRIVACY.md) has the details, including exactly which values are redacted.

## Command line

The same checks run without an agent, from the folder of the project you are checking:

```bash
uv run --script <path to this plugin>/scripts/docdrift.py --help
```

(In a clone of this repository the script is `plugins/jevmcp/scripts/docdrift.py`.) It works in
CI too: `--dry-run --strict` validates the map for free (exit 2 if a spec sentence is neither
mapped nor excluded); a real check exits 1 on drift and 3 when TypeSafe is unavailable. The command
line reads the key from `--key-file`, else `TYPESAFE_API_KEY`, else a `TYPESAFE_API_KEY=` line in
the `.env` of the folder you run it from.

## Standards

- **Agent Plugins 1.0.0**: root `plugin.json` and `mcp.json` validate against the official schemas;
  client-specific settings sit under `extensions` (`com.openai` for the Codex listing) or in the
  clients' own folders (`.claude-plugin/`, `.codex-plugin/`).
- **Agent Skills**: `skills/spec-drift/SKILL.md` uses only the portable frontmatter fields.
- **MCP 2026-07-28**: stateless requests with `server/discover`, per-request `_meta`, `resultType`,
  caching hints, structured tool output, progress and cancellation, and prompt shutdown when the
  client closes the connection; clients of earlier MCP revisions (which open with `initialize`)
  are served too.

## Support

Questions and bugs: <https://github.com/eaisdevelopment/jevmcp/issues>. Security problems: see
[SECURITY.md](https://github.com/eaisdevelopment/jevmcp/blob/main/SECURITY.md).

## License

Apache-2.0 — see [LICENSE](LICENSE).
