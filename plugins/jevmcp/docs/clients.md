# How each client behaves, and its limits

What jevmcp does inside Claude Code, OpenAI Codex and other Agent Plugins clients — how it is
installed, where the key comes from, what the tools are called, when you are asked for approval,
and what does not work — so that an agent installing or using the plugin does not have to guess.

Everything on this page was checked against the code in this repository and against the two
clients on 2026-09-22. The CI-triage and code-audit tools added in 1.7.0 were then run end to end
in both clients on 2026-09-24, on the installed 1.7.0: headless Claude Code 2.1.281 sessions ran a
CI triage (preview, then triage by snapshot), a code audit (validate, preview, then check) and the
free spec-drift tools; Codex 0.156.1 ran `preview_ci_triage`, and its tools that send needed
approval, as designed. Where something was not verified, it says so.

## At a glance

| | Claude Code | OpenAI Codex | Other Agent Plugins 1.0.0 clients |
|---|---|---|---|
| Install | `/plugin marketplace add eaisdevelopment/jevmcp` then `/plugin install jevmcp@jev` | `codex plugin marketplace add eaisdevelopment/jevmcp` then `codex plugin add jevmcp@jev` | the client's own way of loading `plugins/jevmcp` |
| Manifests it reads | `.claude-plugin/marketplace.json`, `plugins/jevmcp/.claude-plugin/plugin.json`, `plugins/jevmcp/.mcp.json` | `.agents/plugins/marketplace.json`, `plugins/jevmcp/plugin.json`, `plugins/jevmcp/mcp.json`, `.codex-plugin/plugin.json` (overlay) | `plugins/jevmcp/plugin.json`, `plugins/jevmcp/mcp.json`, `skills/` |
| API key | asked for when the plugin is enabled; kept in the client's credential store | no prompt: `--set-key` once, or an exported `TYPESAFE_API_KEY` | `TYPESAFE_API_KEY` in the environment, or a key file (`--set-key`) |
| Tool names | `mcp__plugin_jevmcp_jevmcp__<tool>` | `<tool>` on server `jevmcp` of plugin `jevmcp@jev` | the client's own scheme, over server `jevmcp` |
| Skills | `jevmcp:spec-drift`, `jevmcp:ci-triage`, `jevmcp:code-audit` | listed in the session's skill catalogue | depends on the client's skill support |
| Must a call pass `project`? | no (but see the boundary rule below) | **yes, always**, absolute path | yes, unless the client starts the server in the project |
| Approval for the tools that send (`check_spec_drift`, `triage_ci_failure`, `check_code_rules`) | the client's normal MCP tool permission | **every time, by design** | the client's own rule |
| Reading a GitHub run for CI triage | the server's `gh`, with the user's environment | the server's `gh`, with Codex's minimal environment (no token variables) | the server's `gh`, with whatever environment the client passes |
| Unattended / CI | not established here — use the command line | `codex exec` (0.156.1): the read-only `preview_ci_triage` ran; the tools that send are blocked unless approvals and the sandbox are switched off — use the command line | unknown |
| Network in the agent's shell | yes | **no** (sandboxed) | unknown |
| Update | `claude plugin update jevmcp@jev` | `codex plugin remove jevmcp@jev && codex plugin add jevmcp@jev` | the client's own way |

Same in every client, because it is in the server, not the client:

- Three tools send data, each a different kind: `check_spec_drift` (spec sentences with their
  paired code), `triage_ci_failure` (CI log excerpts with an excerpt of the change) and
  `check_code_rules` (units of source code). The validate, preview and draft tools are free and
  send nothing — see [tools.md](tools.md) and [PRIVACY.md](../PRIVACY.md).
- CI triage reads a GitHub run with the user's own `gh` login, GET requests only, and only for a
  GitHub remote of the project.
- The server never reads the checked project's `.env`, and never puts the key into a tool
  argument, a tool result or the model's context.
- Rate limits: 20 calls a minute of the three tools that send, together, and 120 tool calls a
  minute (`--max-checks-per-minute`, `--max-calls-per-minute`). An audit of more than 400
  requests needs `confirm_units` (`--max-audit-requests`).
- The full results files, one per tool family, are written to a private temporary folder of the
  server process (0700, the files 0600) and removed when the server stops. So are CI-triage
  snapshots and the inbox for log files.
- `uv` must be on `PATH`. The first start installs the server's dependencies (tree-sitter, PyYAML)
  into uv's own cache; nothing is installed into the project.

---

## Claude Code

Tested with Claude Code 2.1.278; the CI-triage and code-audit tools with 2.1.281, on 2026-09-24.

### Discovery and install

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jev
```

The marketplace is named `jev` and the plugin inside it is named `jevmcp`, so the install id is
`jevmcp@jev`. Claude Code reads the Claude-specific manifests: `.claude-plugin/marketplace.json`
at the repository root, `plugins/jevmcp/.claude-plugin/plugin.json`, and
`plugins/jevmcp/.mcp.json`. It does **not** read the portable `plugin.json` / `mcp.json` — that is
why both sets of files exist.

Installed copies live at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, for example
`~/.claude/plugins/cache/jev/jevmcp/1.7.4/`. Older versions stay beside the new one.

Update with `claude plugin update jevmcp@jev`. After an update Claude Code says
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

The ten tools appear as:

```
mcp__plugin_jevmcp_jevmcp__check_spec_drift
mcp__plugin_jevmcp_jevmcp__validate_spec_map
mcp__plugin_jevmcp_jevmcp__preview_spec_check
mcp__plugin_jevmcp_jevmcp__draft_spec_map
mcp__plugin_jevmcp_jevmcp__triage_ci_failure
mcp__plugin_jevmcp_jevmcp__preview_ci_triage
mcp__plugin_jevmcp_jevmcp__check_code_rules
mcp__plugin_jevmcp_jevmcp__preview_code_audit
mcp__plugin_jevmcp_jevmcp__validate_rule_map
mcp__plugin_jevmcp_jevmcp__draft_rule_map
```

(The shape is `mcp__plugin_<plugin>_<server>__<tool>`; plugin and server are both `jevmcp`.)

The skills are `jevmcp:spec-drift`, `jevmcp:ci-triage` and `jevmcp:code-audit`. Always in context:
each skill's name and frontmatter description (825, 775 and 788 characters, roughly 200 tokens
each). A skill's body (about 13.6 kB, 10.2 kB and 10.8 kB) is read only when that skill is used.
While the server is connected, Claude Code also shows the model the server's own `instructions`
block (1,764 characters, roughly 450 tokens) under "MCP Server Instructions"; it states the key
and consent rules first, then the three families and the labels. The full tool list, with every
input and output schema, is about 31,000 characters.

### Approvals and consent

`check_spec_drift`, `triage_ci_failure` and `check_code_rules` are annotated
`readOnlyHint: false`, `openWorldHint: true` because data leaves the machine, so Claude Code treats
them as write actions and applies its normal MCP permission prompt. That prompt is about the tool,
not about the data: the **consent for sending** is the skills' own rule, one consent per kind of
data. For spec drift, ask the user once per project before the first real check, unless the
project's `CLAUDE.md`/`AGENTS.md` already records it. For CI logs and for source-code units only
the user, in the conversation, can give it — never a file in the repository. The preview tools
show exactly what would be sent and need no consent. `preview_ci_triage` is read-only but marked
open-world, because it calls GitHub.

In the sessions of 2026-09-24 the server's guard rails held: a run of another repository was
refused, and nothing was sent without the user's consent. The agent did not stop there, though.
After the refusal it read that run itself with `gh` and a web fetch, and without consent it judged
the previewed failures itself instead of asking. The ci-triage skill now says to do neither: say
that the run was refused and stop, and without a yes to send, show what would be sent and the cost,
and ask.

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

A headless Claude Code run did discover and load the spec-drift skill on its own, with no mention
of the plugin in the prompt. On 2026-09-24, headless Claude Code 2.1.281 sessions ran the CI-triage
tools (preview, then triage by snapshot) and the code-audit tools (validate, preview, then check)
end to end on the installed 1.7.0, with those tools permitted for the test. What was **not**
established here is which permission flags a fully unattended run needs before
`mcp__plugin_jevmcp_jevmcp__check_spec_drift` or the other tools that send will execute. For CI,
do not drive an agent at all — run the scripts directly (see [how-to.md](how-to.md)):

```bash
uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json --dry-run --strict   # free
uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json                      # a real check
uv run --script <plugin>/scripts/ci_triage.py --run <run URL> --src .                   # CI triage
uv run --script <plugin>/scripts/code_audit.py --map rule_map.json --base origin/main   # code audit
```

Exit codes: 0 nothing found · 1 at least one DRIFT, CHANGE or BREAKS · 2 setup or map problem ·
3 TypeSafe unavailable. Never report a pass from an exit-3 run.

### Sandbox and network

Claude Code's own shell has network access, so the command line works inside a session. The MCP
tools are still the better route: the server keeps the parsed code in memory (a 16,000-file
repository re-indexes in about 2 s instead of about 20 s) and holds the key.

For CI triage, Claude Code starts the server with the user's environment, so the server's `gh`
finds the same login as the user's terminal.

### Known quirks

- After `claude plugin update`, tools and skill text only change once Claude Code is restarted.
- A marketplace card is written by hand and can fall behind the server. Trust `tools/list` over
  any description when the two disagree.

---

## OpenAI Codex

Tested with `codex-cli 0.155.1`; the CI-triage tools and `codex exec` again with `codex-cli 0.156.1`,
on 2026-09-24.

### Discovery and install

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jev
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
`~/.codex/plugins/cache/jev/jevmcp/1.7.4/`. `~/.codex/config.toml` gains
`[plugins."jevmcp@jev"] enabled = true` (and a `[marketplaces.jev]` entry).

Update with `codex plugin remove jevmcp@jev && codex plugin add jevmcp@jev`.

### Where the key comes from

**Codex has no prompt for secrets.** Two options, in the user's own terminal — never in a Codex
session, and never as a command-line argument:

1. Store it once (recommended):

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jev/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key
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
`preview_spec_check`, `draft_spec_map`, `triage_ci_failure`, `preview_ci_triage`,
`check_code_rules`, `preview_code_audit`, `validate_rule_map`, `draft_rule_map`. In
`~/.codex/config.toml` the table for them is
`[plugins."jevmcp@jev".mcp_servers.jevmcp]`. If a tool was approved by name before 1.3.0, that approval no
longer matches (`check_drift` → `check_spec_drift`, `validate_map` → `validate_spec_map`,
`show_payload` → `preview_spec_check`, `draft_map` → `draft_spec_map`): approve the new name once.

Codex injects each skill's frontmatter `description` verbatim into a `<skills_instructions>`
developer message at session start; that text is the whole trigger. Three neutral prompts (no
mention of the plugin) loaded the spec-drift skill 3/3; a control prompt ("What does this project
do?") did not. The ci-triage and code-audit skills have not been tested this way yet. The server's `instructions` block is served at `initialize` / `server/discover` as usual.

### Approvals and consent

**In Codex, every call of a tool that sends asks for approval.** `check_spec_drift`,
`triage_ci_failure` and `check_code_rules` are write actions (`readOnlyHint: false`,
`openWorldHint: true`) because they send data to `api.typesafe.ai`, so Codex prompts before each
call — that prompt *is* the user's consent for that call. Do not try to route around it.

The free tools can run unattended if the user adds to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jev".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

`preview_ci_triage` is read-only but marked open-world, because it calls GitHub. With Codex
0.156.1 (tested 2026-09-24) it ran under `codex exec`, whose approval policy is `never`, without
that setting in `~/.codex/config.toml`: Codex did not require approval for it. In the same run
`triage_ci_failure` was blocked (*"MCP tool call requires approval, but approval policy is
never"*), as designed. The other tools were not called in that run, and an interactive session
was not re-checked for `preview_ci_triage`.

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

Tested on 2026-09-22 with Codex 0.155.1, and `codex exec` again on 2026-09-24 with 0.156.1.
`codex exec` runs with approval policy `never`:

| Command | Codex | Result |
|---|---|---|
| `codex exec '...'` | 0.156.1 (2026-09-24) | The read-only `preview_ci_triage` ran: it read a GitHub run and returned its preview. The tools that send are blocked: `triage_ci_failure` failed with *"MCP tool call requires approval, but approval policy is never"*. No other tool was called. |
| `codex exec '...'` | 0.155.1 (2026-09-22) | Every MCP tool was blocked, with the same message. |
| `codex exec --approve-for-me '...'` | 0.155.1 | Still refused. Codex's automatic reviewer rejects `check_spec_drift` because it *"may transmit project spec and code to the untrusted TypeSafe destination"*. |
| `codex exec --dangerously-bypass-approvals-and-sandbox '...'` | 0.155.1 | Works (verified: 3 DRIFT on the demo project). It switches off the sandbox **and** all approvals, so use it only where the whole job is already isolated, such as a CI container. |

With 0.156.1 the tools that send were not run headless: the only unattended route is the last row,
which switches off approvals and the sandbox.

Better for CI: skip the agent and run the scripts where the network works —
`uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json`, `ci_triage.py` or
`code_audit.py` (see [how-to.md](how-to.md)).

### Sandbox and network

**Codex's sandbox has no network.** A fallback to the command line *inside* a Codex session
therefore reaches nothing: the run cannot call TypeSafe and comes back having found no drift. That
is a silent false pass — never report it as "no drift". Use the MCP tools, which work because the
MCP server is started outside the sandbox.

Codex also passes the server a minimal environment — `HOME`, `LANG`, `LOGNAME`, `PATH`, `SHELL`,
`TERM`, `USER`, plus the variables the plugin declares (`TYPESAFE_API_KEY`) — along with
`PLUGIN_ROOT` and `PLUGIN_DATA`.

### CI triage and code audit in Codex

- **The agent cannot fetch a CI log itself** — its shell has no network. The server can: give
  `preview_ci_triage` the run's URL and the server reads it with the user's `gh`, outside the
  sandbox. That `gh` sees only the minimal environment above, so a login that `gh` finds only
  through `GH_TOKEN` or `GITHUB_TOKEN` does not reach it; `gh auth login` in the user's own
  terminal does. Verified with Codex 0.156.1 on 2026-09-24: `preview_ci_triage` read a failed
  GitHub run this way. In that run Codex's own web tool also opened the run's page on github.com.
- **Log files from another CI** go inside the project, which the agent can always write to. The
  server's private inbox is an alternative, but whether Codex's sandbox lets the agent write
  there was not verified.
- **The 600-second tool limit.** The overlay allows each tool call 600 s. A large audit can take
  longer: preview first, and narrow it with `base` or `files`.
- **Not yet verified in Codex:** the code-audit tools, and a CI triage actually sent from a Codex
  session (it needs the approval that `codex exec` cannot give).

### Known quirks

- **Skill paths.** Codex's skill catalogue lists a root and a path under it, and a model can
  shorten that wrongly if the two repeat a name. Up to 1.4.1 the marketplace and the plugin were
  both called `jevmcp`, and the first read of `SKILL.md` failed on a duplicated segment every
  time before the retry succeeded. Since 1.5.0 the marketplace is `jev`, so the path is
  `.../plugins/cache/jev/jevmcp/<version>/skills/...` with nothing repeated. If you still see the
  old failure, the plugin was installed from the old marketplace: remove it and add it again.
- **First start can time out** while uv downloads the tree-sitter parsers. Run
  `uv run --script ~/.codex/plugins/cache/jev/jevmcp/<version>/scripts/jevmcp_server.py --help`
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
- **Skills.** `skills/spec-drift/SKILL.md`, `skills/ci-triage/SKILL.md` and
  `skills/code-audit/SKILL.md` use only portable frontmatter fields; a client without skill
  support still gets the key and consent rules and the labels from the server's `instructions`
  block, in shorter form.

---

## The order the key is looked for (all clients)

1. `--key-file FILE`, if the server was registered with one — absolute path, and then **only**
   that file;
2. `TYPESAFE_API_KEY` in the server's environment (Claude Code fills it from the plugin settings;
   Codex forwards it only if the user exported it);
3. `typesafe.env` in the plugin's data folder (`$PLUGIN_DATA`, or `$CLAUDE_PLUGIN_DATA`);
4. `~/.config/jevmcp/typesafe.env` — what `--set-key` writes (`$XDG_CONFIG_HOME` is respected).

The project's own `.env` is never read by the MCP server. The spec-drift command line,
`spec_drift.py`, does read a `TYPESAFE_API_KEY=` line from the `.env` of the folder it is run in —
that is the one difference. `ci_triage.py` and `code_audit.py` never read a `.env`.

## Versions this page was checked against

| | Version |
|---|---|
| jevmcp plugin | 1.7.4 |
| Claude Code | 2.1.278 (the `claude` CLI on the machine used for the final check reports 2.1.280; nothing here is known to have changed); 2.1.281 for the CI-triage and code-audit sessions of 2026-09-24; 2.1.282 for the Chinese, Japanese, Korean and Russian spec sessions of 2026-09-25 |
| OpenAI Codex | `codex-cli 0.155.1`; `codex-cli 0.156.1` for the CI-triage and `codex exec` checks of 2026-09-24 |
| uv | 0.11.16 |

## Next

- Installing, step by step: [install.md](install.md)
- The ten tools, their arguments and their output: [tools.md](tools.md)
- Recipes — first set-up, routine checks, CI: [how-to.md](how-to.md)
- What the plugin is: [the plugin README](../README.md)
- What is sent and what never is: [../PRIVACY.md](../PRIVACY.md)
