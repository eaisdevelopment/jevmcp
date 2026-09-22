# jevmcp — TypeSafe's fast model as routine tooling for your coding agent

**One plugin, installed once.** It gives **Claude Code** and **OpenAI Codex** (both tested) the
tools that put TypeSafe's fast model **Jev** to work: the fast model screens everything in seconds
and for fractions of a cent, and your agent spends its own effort only on what was flagged. Built
on the portable [Agent Plugins](https://agent-plugins.org) format, so other clients of that format
can load it too.

New tools are added to this same plugin — you do not install or configure anything again, you
update it (`claude plugin update jevmcp@jev`).

## What is in it today

**Spec-drift checking** — does the code still match the project's design spec or requirements
document? Your agent checks after it changes something, and before a release. On a real Java
project (131 requirements): a check after editing two files took 3 seconds and cost $0.0013; a
full check took 11 seconds and cost $0.006.

- **A skill** (`spec-drift`) that teaches the agent the whole workflow: setting up a project,
  checking after every change, reading the results, the fast model's blind spots, and reporting.
- **One MCP server** (`jevmcp`) that today offers four tools — `check_spec_drift`, `validate_spec_map`,
  `preview_spec_check`, `draft_spec_map`. It keeps the parsed code in memory, so after an edit only the
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
/plugin install jevmcp@jev
```

Claude Code asks for your TypeSafe API key when the plugin is enabled and keeps it out of every
settings file (in the macOS Keychain, or `~/.claude/.credentials.json` on other systems). To change
it later: `/plugin manage`. Enter it at that prompt rather than with `claude plugin install
--config`, which would leave it in your shell history.

**OpenAI Codex**

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jev
```

Codex has no prompt for keys, so store it once — in your own terminal, not in a Codex session:

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jev/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key
```

It asks for the key without showing it and writes `~/.config/jevmcp/typesafe.env` (only you can
read it). The server picks it up at its next start, it survives plugin updates, and the model
never sees it. `--show-key-source` says where the key would come from, without printing it.

`export TYPESAFE_API_KEY=...` in the shell that starts Codex works too, but then Codex's own shell
tool inherits it, so the model *could* read it with `env`; the skill tells it never to.

`check_spec_drift` is marked as a write action, because it sends code out of your machine: Codex asks
you before each check — that is your consent. The free tools (`validate_spec_map`, `preview_spec_check`) can
run without asking if you add to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jev".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

**Unattended runs in Codex** (tested, 2026-09-22): `codex exec` runs with approval policy
"never", which blocks every MCP tool, and `--approve-for-me` does not help — Codex's automatic
reviewer refuses a tool that sends code to a third party. Two honest options:

- `codex exec --dangerously-bypass-approvals-and-sandbox '...'` — the check then runs (verified).
  The flag switches off Codex's sandbox and all approvals, so use it only where the whole job is
  already isolated, such as a CI container.
- Better for CI: skip the agent and run the checker directly, where the network works:
  `uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json` (exit 1 on drift, 2 on a
  map problem, 3 if TypeSafe is unavailable).

Do not let an agent inside Codex fall back to that command line: Codex's sandbox has no network,
so the check cannot reach TypeSafe and silently finds nothing. The MCP server runs outside the
sandbox, which is why the tools work there.

If the server's very first start times out while uv downloads the parsers, run
`uv run --script ~/.codex/plugins/cache/jev/jevmcp/<version>/scripts/jevmcp_server.py --help`
once (uv caches them), then start Codex again; Codex's `config.toml` cannot change a plugin
server's startup timeout.

**Other Agent Plugins clients** (VS Code, GitHub Copilot, Kiro, ...) load the portable core of
this folder — `plugin.json`, `mcp.json`, `skills/` — through their own plugin setup. The portable
format has no secret mechanism (keys must not go in `mcp.json`), so give the server the key either
through `TYPESAFE_API_KEY` in the environment the client passes on, or by putting the line
`TYPESAFE_API_KEY=...` into `typesafe.env` in the plugin's data folder (`PLUGIN_DATA`); if the key
is missing, the server's error message names that exact path. Cursor is not supported yet: it
does not expand the standard's `${PLUGIN_ROOT}`.

## First run in a project: the spec map

You never write or edit a file yourself. Ask your agent, in the project:

> Set up spec-drift checking for this project.

1. It finds your spec (a design, requirements or architecture document in Markdown).
2. `draft_spec_map` **writes `spec_map.json` for you** — one entry per sentence of the spec, each with
   a suggested place in the code. Free: nothing is sent anywhere.
3. The agent reviews the entries with you: it fixes wrong guesses and marks sentences that are not
   requirements as excluded, with a reason. Your knowledge is needed here, and only here.
4. `validate_spec_map` confirms nothing is missing. Commit the file with your code.

**`spec_map.json` is the pairing between your spec and your code** — for each sentence, the code
that implements it. One entry, written by the agent and reviewed by you:

```json
{"spec": "docs/spec.md", "line": 6,
 "text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
 "status": "reviewed",
 "code": ["app/settings.py:SHOP_MAX_ITEMS", "app/services.py:place_order"]}
```

That pairing is why a check costs fractions of a cent: each requirement is sent with the few lines
that enforce it, never the whole repository. After this, a check is one sentence and takes seconds.

## Your API key

Never commit it, and never paste it into an issue or a chat. The MCP server reads it, in this
order, from:

1. `--key-file FILE`, if the server was registered with one (an absolute path; then only from
   that file);
2. the `TYPESAFE_API_KEY` environment variable (Claude Code fills it from the plugin's settings,
   Codex forwards yours if you exported it);
3. `typesafe.env` in the plugin's data folder (`$PLUGIN_DATA`, or `$CLAUDE_PLUGIN_DATA`);
4. `~/.config/jevmcp/typesafe.env` — what `--set-key` writes.

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
`preview_spec_check` (or `--dry-run --show-payload`) shows exactly what would be sent, without sending
it. [PRIVACY.md](PRIVACY.md) has the details, including exactly which values are redacted.

## Command line

The same checks run without an agent, from the folder of the project you are checking:

```bash
uv run --script <path to this plugin>/scripts/spec_drift.py --help
```

(In a clone of this repository the script is `plugins/jevmcp/scripts/spec_drift.py`.) It works in
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

## Documentation

- [Install and set up](docs/install.md) · [Tools and spec map](docs/tools.md) ·
  [Client behaviour and limits](docs/clients.md) · [Recipes](docs/how-to.md) ·
  [Privacy](PRIVACY.md)
- These pages ship with the plugin, so an agent can read them after installing it.

## Support

Questions and bugs: <https://github.com/eaisdevelopment/jevmcp/issues>. Security problems: see
[SECURITY.md](https://github.com/eaisdevelopment/jevmcp/blob/main/SECURITY.md).

## License

Apache-2.0 — see [LICENSE](LICENSE).
