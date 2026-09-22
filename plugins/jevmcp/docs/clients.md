# How each client behaves, and its limits

What jevmcp does inside Claude Code, OpenAI Codex and other Agent Plugins clients — how it is
installed, where the key comes from, what the tools are called, when you are asked for approval,
and what does not work — so that an agent installing or using the plugin does not have to guess.

Everything on this page was checked against the code in this repository and against the two
clients on 2026-09-22. Where something was not verified, it says so.

## At a glance

| | Claude Code | OpenAI Codex | Other Agent Plugins 1.0.0 clients |
|---|---|---|---|
| Install | `/plugin marketplace add eaisdevelopment/jevmcp` then `/plugin install jevmcp@jevmcp` | `codex plugin marketplace add eaisdevelopment/jevmcp` then `codex plugin add jevmcp@jevmcp` | the client's own way of loading `plugins/jevmcp` |
| Manifests it reads | `.claude-plugin/marketplace.json`, `plugins/jevmcp/.claude-plugin/plugin.json`, `plugins/jevmcp/.mcp.json` | `.agents/plugins/marketplace.json`, `plugins/jevmcp/plugin.json`, `plugins/jevmcp/mcp.json`, `.codex-plugin/plugin.json` (overlay) | `plugins/jevmcp/plugin.json`, `plugins/jevmcp/mcp.json`, `skills/` |
| API key | asked for when the plugin is enabled; kept in the client's credential store | no prompt: `--set-key` once, or an exported `TYPESAFE_API_KEY` | `TYPESAFE_API_KEY` in the environment, or a key file (`--set-key`) |
| Tool names | `mcp__plugin_jevmcp_jevmcp__<tool>` | `<tool>` on server `jevmcp` of plugin `jevmcp@jevmcp` | the client's own scheme, over server `jevmcp` |
| Skill | `jevmcp:spec-drift` | listed in the session's skill catalogue | depends on the client's skill support |
| Must a call pass `project`? | no (but see the boundary rule below) | **yes, always**, absolute path | yes, unless the client starts the server in the project |
| Approval for `check_spec_drift` | the client's normal MCP tool permission | **every time, by design** | the client's own rule |
| Unattended / CI | not established here — use the command line | MCP tools blocked unless the sandbox is switched off — use the command line | unknown |
| Network in the agent's shell | yes | **no** (sandboxed) | unknown |
| Update | `claude plugin update jevmcp@jevmcp` | `codex plugin remove jevmcp@jevmcp && codex plugin add jevmcp@jevmcp` | the client's own way |

Same in every client, because it is in the server, not the client:

- Only `check_spec_drift` sends anything. `validate_spec_map`, `preview_spec_check` and
  `draft_spec_map` are free and send nothing — see [tools.md](tools.md) and
  [PRIVACY.md](../PRIVACY.md).
- The server never reads the checked project's `.env`, and never puts the key into a tool
  argument, a tool result or the model's context.
- Rate limits: 20 `check_spec_drift` calls a minute, 120 tool calls a minute (`--max-checks-per-minute`,
  `--max-calls-per-minute`).
- The full results file is written to a private temporary folder of the server process (0700, the
  file 0600) and removed when the server stops.
- `uv` must be on `PATH`. The first start installs the server's dependencies (tree-sitter, PyYAML)
  into uv's own cache; nothing is installed into the project.

---

## Claude Code

Tested with Claude Code 2.1.278.

### Discovery and install

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jevmcp
```

The marketplace is named `jevmcp` and the plugin inside it is named `jevmcp`, so the install id is
`jevmcp@jevmcp`. Claude Code reads the Claude-specific manifests: `.claude-plugin/marketplace.json`
at the repository root, `plugins/jevmcp/.claude-plugin/plugin.json`, and
`plugins/jevmcp/.mcp.json`. It does **not** read the portable `plugin.json` / `mcp.json` — that is
why both sets of files exist.

Installed copies live at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, for example
`~/.claude/plugins/cache/jevmcp/jevmcp/1.3.1/`. Older versions stay beside the new one.

Update with `claude plugin update jevmcp@jevmcp`. After an update Claude Code says
**"Restart to apply changes"** — the MCP server process is only replaced on restart.

### Where the key comes from

`plugins/jevmcp/.claude-plugin/plugin.json` declares one `userConfig` entry, `typesafe_api_key`
(`"sensitive": true`, `"required": true`), so Claude Code asks for the key when the plugin is
enabled and keeps it out of every settings file — macOS Keychain, otherwise
`~/.claude/.credentials.json`. `plugins/jevmcp/.mcp.json` then passes it to the server as an
environment variable:

```json
"env": { "TYPESAFE_API_KEY": "${user_config.typesafe_api_key}" }
```

Change it later with `/plugin manage`. Do not use `claude plugin install --config ...`: the key
would end up in the shell history. Never ask the user for the key in chat, and never run
`--set-key` on their behalf — it refuses to run anywhere but a real terminal.

### Tool names and what the model sees

The four tools appear as:

```
mcp__plugin_jevmcp_jevmcp__check_spec_drift
mcp__plugin_jevmcp_jevmcp__validate_spec_map
mcp__plugin_jevmcp_jevmcp__preview_spec_check
mcp__plugin_jevmcp_jevmcp__draft_spec_map
```

(The shape is `mcp__plugin_<plugin>_<server>__<tool>`; plugin and server are both `jevmcp`.)

The skill is `jevmcp:spec-drift`. Always in context: the skill's name and its frontmatter
description (825 characters, roughly 200–230 tokens). The skill body
(`skills/spec-drift/SKILL.md`, about 10.7 kB, roughly 3,000 tokens) is read only when the skill is
used. While the server is connected, Claude Code also shows the model the server's own
`instructions` block (1,211 characters, roughly 300 tokens) under "MCP Server Instructions"; it
states the labels and that the server holds the key.

### Approvals and consent

`check_spec_drift` is annotated `readOnlyHint: false`, `openWorldHint: true` because code leaves
the machine, so Claude Code treats it as a write action and applies its normal MCP permission
prompt. That prompt is about the tool, not about the data: the **consent for sending code** is the
skill's own rule — ask the user once per project before the first real check, unless the project's
`CLAUDE.md`/`AGENTS.md` already records it. `preview_spec_check` shows exactly what would be sent
and needs no consent.

### Where the server runs, and which folder is the project

Claude Code starts the server in the project and sets `CLAUDE_PROJECT_DIR`, which the server uses
as its `--root` default, so tool calls may leave `project` out. Passing it is normally harmless,
with one boundary rule in the code: if `project` points outside the folder the server was started
for, the call is refused —

```
project /x/y is outside the project this server was started for (/a/b) - refused
```

A home folder or a filesystem root is refused as a project anywhere.

### Unattended and CI

A headless Claude Code run did discover and load the skill on its own, with no mention of the
plugin in the prompt. What was **not** established here is which permission flags a fully
unattended run needs before `mcp__plugin_jevmcp_jevmcp__check_spec_drift` will execute. For CI, do
not drive an agent at all — run the checker directly (see [how-to.md](how-to.md)):

```bash
uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json --dry-run --strict   # free
uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json                      # a real check
```

Exit codes: 0 no drift · 1 at least one DRIFT · 2 setup or map problem · 3 TypeSafe unavailable.
Never report "no drift" from an exit-3 run.

### Sandbox and network

Claude Code's own shell has network access, so the command line works inside a session. The MCP
tools are still the better route: the server keeps the parsed code in memory (a 16,000-file
repository re-indexes in about 2 s instead of about 20 s) and holds the key.

### Known quirks

- After `claude plugin update`, tools and skill text only change once Claude Code is restarted.
- A marketplace card is written by hand and can fall behind the server. Trust `tools/list` over
  any description when the two disagree.

---

## OpenAI Codex

Tested with `codex-cli 0.155.1`.

### Discovery and install

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jevmcp
```

Codex reads `.agents/plugins/marketplace.json` at the repository root and then the portable
package: `plugins/jevmcp/plugin.json` (the Codex listing sits under
`extensions."com.openai".interface`) and `plugins/jevmcp/mcp.json`, which starts the server with
`${PLUGIN_ROOT}/scripts/jevmcp_server.py`. `plugins/jevmcp/.codex-plugin/plugin.json` is an
overlay that adds only key forwarding and timeouts:

```json
{"command": "uv", "args": ["run", "--quiet", "--script", "./scripts/jevmcp_server.py"],
 "cwd": ".", "env_vars": ["TYPESAFE_API_KEY"],
 "startup_timeout_sec": 120, "tool_timeout_sec": 600}
```

Codex merges an overlay entry only when it is a complete server definition; the portable
`mcp.json` still decides the command (checked with `codex mcp list --json`).

Installed copies live at `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`, for example
`~/.codex/plugins/cache/jevmcp/jevmcp/1.3.1/`. `~/.codex/config.toml` gains
`[plugins."jevmcp@jevmcp"] enabled = true` (and a `[marketplaces.jevmcp]` entry).

Update with `codex plugin remove jevmcp@jevmcp && codex plugin add jevmcp@jevmcp`.

### Where the key comes from

**Codex has no prompt for secrets.** Two options, in the user's own terminal — never in a Codex
session, and never as a command-line argument:

1. Store it once (recommended):

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jevmcp/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key
```

`--set-key` asks without echoing (it refuses to run unless stdin and stdout are a terminal, so an
agent cannot run it), writes `~/.config/jevmcp/typesafe.env` with mode 0600 in a 0700 directory,
and survives plugin updates.

2. Or `export TYPESAFE_API_KEY=...` in the shell that starts Codex — the overlay's `env_vars`
   forwards it to the server. The cost: Codex's shell tool inherits the user's environment, so the
   model *could* read the key with `env`. The stored key file cannot be read that way.

Check without printing the key: `... jevmcp_server.py --show-key-source` (exit 0 if a key is
found, 1 if not). The plugin's own data folder works too, but Codex names it with an unguessable
hash (`~/.codex/plugins/data/agent-plugins/<64 hex characters>/`), which is exactly why
`~/.config/jevmcp/typesafe.env` exists as the last, findable place.

### Tool names, and what Codex shows the model

The tools keep their plain names on server `jevmcp`: `check_spec_drift`, `validate_spec_map`,
`preview_spec_check`, `draft_spec_map`. In `~/.codex/config.toml` the table for them is
`[plugins."jevmcp@jevmcp".mcp_servers.jevmcp]`. If a tool was approved by name before 1.3.0, that approval no
longer matches (`check_drift` → `check_spec_drift`, `validate_map` → `validate_spec_map`,
`show_payload` → `preview_spec_check`, `draft_map` → `draft_spec_map`): approve the new name once.

Codex injects the skill's frontmatter `description` verbatim into a `<skills_instructions>`
developer message at session start; that text is the whole trigger. Three neutral prompts (no
mention of the plugin) loaded the skill 3/3; a control prompt ("What does this project do?") did
not. The server's `instructions` block is served at `initialize` / `server/discover` as usual.

### Approvals and consent

**In Codex, every check asks for approval.** `check_spec_drift` is a write action
(`readOnlyHint: false`, `openWorldHint: true`) because it sends code to `api.typesafe.ai`, so
Codex prompts before each call — that prompt *is* the user's consent for that check. Do not try to
route around it.

The free tools can run unattended if the user adds to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jevmcp".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

### Where the server runs, and which folder is the project

The overlay sets `cwd: "."`, so Codex starts the server **inside the plugin's own folder**, and
Codex does not tell the server which project the session is in. The server detects this (its
working folder is under its own plugin root) and refuses to guess:

```
this client did not tell the server which project it is working in - pass project:
the absolute path of the project folder (your working directory).
```

So **every tool call from Codex must pass `project`** with the absolute path of the project. A
relative path is refused (`project must be an absolute path`), and a home folder or `/` is refused
(`is a home or root folder, not a project`).

### Unattended and CI — what fails, exactly

Tested on 2026-09-22 with Codex 0.155.1:

| Command | Result |
|---|---|
| `codex exec '...'` | Every MCP tool is blocked: *"MCP tool call requires approval, but approval policy is never"*. `codex exec` runs with approval policy `never`. |
| `codex exec --approve-for-me '...'` | Still refused. Codex's automatic reviewer rejects `check_spec_drift` because it *"may transmit project spec and code to the untrusted TypeSafe destination"*. |
| `codex exec --dangerously-bypass-approvals-and-sandbox '...'` | Works (verified: 3 DRIFT on the demo project). It switches off the sandbox **and** all approvals, so use it only where the whole job is already isolated, such as a CI container. |

Better for CI: skip the agent and run the checker where the network works —
`uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json` (see
[how-to.md](how-to.md)).

### Sandbox and network

**Codex's sandbox has no network.** A fallback to the command line *inside* a Codex session
therefore reaches nothing: the run cannot call TypeSafe and comes back having found no drift. That
is a silent false pass — never report it as "no drift". Use the MCP tools, which work because the
MCP server is started outside the sandbox.

Codex also passes the server a minimal environment — `HOME`, `LANG`, `LOGNAME`, `PATH`, `SHELL`,
`TERM`, `USER`, plus the variables the plugin declares (`TYPESAFE_API_KEY`) — along with
`PLUGIN_ROOT` and `PLUGIN_DATA`.

### Known quirks

- **Duplicated path segment on the first skill read.** Codex's skill catalogue shortens
  `.../plugins/cache/jevmcp/jevmcp` to a single root, so the model's first attempt to read
  `SKILL.md` can fail with a doubled path segment; the retry succeeds. Cause: the marketplace and
  the plugin share the name `jevmcp`. Cosmetic — just retry with the path the error reports.
- **First start can time out** while uv downloads the tree-sitter parsers. Run
  `uv run --script ~/.codex/plugins/cache/jevmcp/jevmcp/<version>/scripts/jevmcp_server.py --help`
  once (uv then has them cached) and start Codex again. Codex's `config.toml` cannot change a
  plugin server's startup timeout; the overlay already asks for 120 s.

---

## Other Agent Plugins 1.0.0 clients

Not tested end to end. The portable core of `plugins/jevmcp` — `plugin.json`, `mcp.json` and
`skills/` — validates against the Agent Plugins 1.0.0 schemas, so a client of that format can load
the folder through its own plugin setup.

- **`${PLUGIN_ROOT}` must be expanded.** `mcp.json` starts
  `uv run --quiet --script ${PLUGIN_ROOT}/scripts/jevmcp_server.py`. **Cursor does not expand it
  and is not supported yet.**
- **The key.** The portable format has no secret mechanism, and a key must never be written into
  `mcp.json`. Give the server either `TYPESAFE_API_KEY` in the environment the client passes on,
  or a `TYPESAFE_API_KEY=...` line in `typesafe.env` inside the plugin's data folder
  (`$PLUGIN_DATA`), or `~/.config/jevmcp/typesafe.env` from `--set-key`. When no key is found, the
  tool error names the exact command to run.
- **Which folder is the project.** If the client starts the server in the project, `project` may be
  left out; if it starts it in the plugin's folder, every call must pass `project`. The safe rule
  for an agent: always pass `project` with your absolute working directory.
- **MCP versions served.** `2026-07-28` as stateless per-request calls (`server/discover`,
  per-request `_meta` carrying `protocolVersion` and `clientCapabilities`, `resultType`, private
  caching hints, structured output, progress, cancellation, shutdown when stdin closes), and, for
  clients that open with `initialize`, `2025-11-25`, `2025-06-18`, `2025-03-26` and `2024-11-05`.
- **Skills.** `skills/spec-drift/SKILL.md` uses only portable frontmatter fields; a client without
  skill support still gets the same guidance from the server's `instructions` block, in shorter
  form.

---

## The order the key is looked for (all clients)

1. `--key-file FILE`, if the server was registered with one — absolute path, and then **only**
   that file;
2. `TYPESAFE_API_KEY` in the server's environment (Claude Code fills it from the plugin settings;
   Codex forwards it only if the user exported it);
3. `typesafe.env` in the plugin's data folder (`$PLUGIN_DATA`, or `$CLAUDE_PLUGIN_DATA`);
4. `~/.config/jevmcp/typesafe.env` — what `--set-key` writes (`$XDG_CONFIG_HOME` is respected).

The project's own `.env` is never read by the MCP server. The command-line checker does read a
`TYPESAFE_API_KEY=` line from the `.env` of the folder it is run in — that is the one difference.

## Versions this page was checked against

| | Version |
|---|---|
| jevmcp plugin | 1.3.1 |
| Claude Code | 2.1.278 (the `claude` CLI on the machine used for the final check reports 2.1.280; nothing here is known to have changed) |
| OpenAI Codex | `codex-cli 0.155.1` |
| uv | 0.11.16 |

## Next

- Installing, step by step: [install.md](install.md)
- The four tools, their arguments and their output: [tools.md](tools.md)
- Recipes — first set-up, routine checks, CI: [how-to.md](how-to.md)
- What the plugin is: [the plugin README](../README.md)
- What is sent and what never is: [../PRIVACY.md](../PRIVACY.md)
