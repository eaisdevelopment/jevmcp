# Install and set up jevmcp

How to install the **jevmcp** plugin in a coding agent, give its MCP server a TypeSafe API key without ever putting the key in a chat message or a command line, prove the install works, and fix it when it does not — written for an agent doing the install on a user's machine, and readable by the human watching.

Related: [tools.md](tools.md) (what each tool does and what its output means) · [clients.md](clients.md) (per-client behaviour, approvals, CI) · [how-to.md](how-to.md) (setting up a project and running checks) · [the plugin README](../README.md) · [../PRIVACY.md](../PRIVACY.md).

---

## Rules for the agent doing the install

These are not style preferences. Break them and the user's API key ends up in a transcript, a shell history file, or a settings file in a repository.

| Never | Why | Do this instead |
|---|---|---|
| Ask the user for the API key in chat | Everything in the conversation is stored and re-read. The key would be in your context, in the transcript, and possibly in a summary. | Tell the user which **one command** to run in their own terminal, or which client prompt to use. Then wait. |
| Run `jevmcp_server.py --set-key` yourself | It asks for the key without echoing it. It refuses to run unless both stdin and stdout are a terminal, so your attempt will fail with exit code 2 anyway. | Give the user the command. They run it. |
| Put the key in a command, an environment assignment, or a file you write | Shell history, process listings and your own tool log all capture it. There is no flag that accepts the key as an argument, on purpose. | `--set-key` (interactive), or the client's own credential prompt. |
| Run `check_spec_drift` "just to test the install" | It sends code to TypeSafe and spends credits. | Use the free tools: `validate_spec_map`, `preview_spec_check`, or `--show-key-source`. |

`validate_spec_map`, `preview_spec_check`, `draft_spec_map`, `--help`, `--dry-run` and `--show-key-source` are free and send nothing. Only `check_spec_drift` (and a command-line run without `--dry-run`) sends anything anywhere.

---

## 1. What you need

| Requirement | Detail | Check it |
|---|---|---|
| **`uv`** on `PATH` | The MCP server and the command-line checker are single PEP 723 scripts: their dependencies (tree-sitter, tree-sitter-java, tree-sitter-javascript, tree-sitter-typescript, PyYAML) are declared inline and installed by `uv` into **uv's own cache** on first start. Nothing is installed into the user's project or into a virtualenv you have to manage. | `uv --version` |
| **A TypeSafe API key** | One key serves every tool in the plugin. Get one at <https://console.typesafe.ai>. Needed only by `check_spec_drift`; the other three tools work without it. | Section 5 |
| **A supported client** | Claude Code and OpenAI Codex are both tested. Any other client of the [Agent Plugins](https://agent-plugins.org) 1.0.0 format can load `plugins/jevmcp`. | Section 2–4 |
| **Python** | `>=3.10`, supplied by `uv` if the system Python is older. | — |

There is **one** plugin, `jevmcp`, version 1.3.1, published by Essential AI Solutions Ltd. under Apache-2.0. The marketplace is also called `jevmcp`, so the install id is **`jevmcp@jevmcp`**. Inside the plugin there is **one** MCP server (`jevmcp`, `scripts/jevmcp_server.py`), **one** skill (`skills/spec-drift/SKILL.md`), and the command-line checker (`scripts/spec_drift.py`). Future tool families (CI failure triage, code audit) add their tools to the *same* server and a skill to the *same* plugin: one install, one key, and they arrive as updates.

---

## 2. Install in Claude Code

Two commands, typed in a Claude Code session:

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jevmcp
```

When the plugin is enabled, Claude Code **asks for the TypeSafe API key itself**. That prompt comes from a `userConfig` field declared in the plugin manifest (`typesafe_api_key`, `sensitive: true`, `required: true`), so:

- the key is kept out of every settings file — macOS Keychain, or `~/.claude/.credentials.json` elsewhere;
- it is never shown to the model;
- Claude Code passes it to the server as the `TYPESAFE_API_KEY` environment variable, because `.mcp.json` declares `"TYPESAFE_API_KEY": "${user_config.typesafe_api_key}"`.

To change the key later: `/plugin manage`, open **jevmcp**, set *TypeSafe API key*.

**Do not** use `claude plugin install --config typesafe_api_key=...`. That leaves the key in the shell history. Use the prompt.

The same two steps from a terminal are `claude plugin marketplace add eaisdevelopment/jevmcp` and `claude plugin install jevmcp@jevmcp`, but the key prompt is part of enabling the plugin in a session.

After the install, restart Claude Code if it says *Restart to apply changes* — the MCP server is only started when the session starts.

**Where it lands:** `~/.claude/plugins/cache/jevmcp/jevmcp/<version>/`.

---

## 3. Install in Codex

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jevmcp
```

`codex plugin marketplace add` takes `owner/repo[@ref]`, an HTTPS or SSH Git URL, or a local path. `codex plugin add` takes `PLUGIN@MARKETPLACE`. Installing writes `[plugins."jevmcp@jevmcp"] enabled = true` into `~/.codex/config.toml`.

**Codex has no prompt for secrets.** It will not ask for the key and cannot store one. The user must store it themselves — see section 5, which is the same command for every client that cannot hold a key.

Codex's overlay (`.codex-plugin/plugin.json`) starts the server with `uv run --quiet --script ./scripts/jevmcp_server.py`, forwards `TYPESAFE_API_KEY` if the user exported it (`env_vars: ["TYPESAFE_API_KEY"]`), and allows 120 s for start-up and 600 s per tool call.

**Where it lands:** `~/.codex/plugins/cache/jevmcp/jevmcp/<version>/`.

Approval behaviour, `codex exec`, and why the command line must not be used as a fallback inside a Codex session are covered in [clients.md](clients.md).

---

## 4. Other Agent Plugins clients

`plugins/jevmcp` is a portable Agent Plugins 1.0.0 package. A client of that format loads:

| File | Purpose |
|---|---|
| `plugin.json` | The portable manifest (name, version, author, licence; the Codex store listing sits under `extensions."com.openai"`). |
| `mcp.json` | The portable server declaration: `stdio`, `command: "uv"`, args ending in `${PLUGIN_ROOT}/scripts/jevmcp_server.py`. No `env`, no `cwd` — the standard forbids secrets in a server's environment declaration, and `cwd` defaults to the plugin root. |
| `skills/spec-drift/SKILL.md` | The skill, using only portable frontmatter fields. |

Because `mcp.json` carries no secret, such a client must give the server the key by one of the routes in section 5 — `TYPESAFE_API_KEY` in the environment it passes on, `typesafe.env` in the plugin's data folder (`PLUGIN_DATA`), or `~/.config/jevmcp/typesafe.env`.

**Cursor is not supported yet:** it does not expand the standard's `${PLUGIN_ROOT}`, so the server path never resolves.

**Claude Code does not read the portable format**, which is why `.claude-plugin/plugin.json` and `.mcp.json` exist alongside it. Every manifest is checked to agree on name and version.

---

## 5. The API key

### The order the server tries

The MCP server looks in exactly this order and stops at the first one it finds:

| # | Source | Notes |
|---|---|---|
| 1 | `--key-file FILE` | Only if the server was registered with that flag. Must be an **absolute** path (`~` is expanded); a relative one is refused, because it would be read from inside the project being checked. If the flag is given, **only** that file is read — the other three are not tried. The file needs a `TYPESAFE_API_KEY=...` line. |
| 2 | `TYPESAFE_API_KEY` in the server's environment | Claude Code puts it there from the plugin's settings. Codex forwards it only if the user exported it in the shell that started Codex. |
| 3 | `typesafe.env` in the plugin's data folder | `$PLUGIN_DATA`, or `$CLAUDE_PLUGIN_DATA`. Only clients that provide such a folder. It survives plugin updates. Codex's is an unguessable hash, which is why it is not the route to recommend to a person. |
| 4 | `~/.config/jevmcp/typesafe.env` | What `--set-key` writes (`$XDG_CONFIG_HOME` is respected). Mode 0600, directory 0700. Readable by every client, survives plugin updates. **This is the one path that works everywhere.** |

The MCP server **never reads the checked project's `.env`** — a cloned repository cannot supply a key. (The command-line checker *does* read a `TYPESAFE_API_KEY=` line from the `.env` of the folder it is run in; that is a deliberate difference, and it is the user's own folder.)

### Storing the key: `--set-key`

The user runs this **in their own terminal**, not through an agent:

```bash
# Codex
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jevmcp/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key

# Claude Code (only needed if they would rather not use the plugin's own key prompt)
uv run --quiet --script "$(ls -d ~/.claude/plugins/cache/jevmcp/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key

# A clone of this repository
uv run --quiet --script plugins/jevmcp/scripts/jevmcp_server.py --set-key
```

The `$(ls … | sort -V | tail -1)` part picks the newest installed version, so the command keeps working after an update.

What it does:

- asks for the key with `getpass`, so nothing is echoed and nothing reaches the shell history;
- writes `~/.config/jevmcp/typesafe.env` with mode `0600` in a directory created with mode `0700`;
- prints a confirmation **to stderr** and nothing else — it never prints the key;
- **refuses to run unless both stdin and stdout are a terminal.** Piped or run by an agent, it exits **2** and prints the command to run by hand. This is why an agent cannot run it, and must not try.

To store it somewhere else, add `--key-file /absolute/path/typesafe.env`.

There is no flag that takes the key as an argument. That is deliberate.

### Checking the key without spending anything: `--show-key-source`

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jevmcp/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --show-key-source 2>&1
```

It prints every source, in order, marks the one that would be used, and **never prints the key**. Real output from a machine where the key is in the `--set-key` file:

```
       --key-file: None
       TYPESAFE_API_KEY in the environment (Claude Code sets it from the plugin's settings): not set
       the plugin's data folder: no PLUGIN_DATA here
  USED --set-key storage: /home/you/.config/jevmcp/typesafe.env - found

The key comes from: --set-key storage
```

- Exit **0** if a key was found, **1** if none was.
- It writes to **stderr**, hence the `2>&1` when piping.
- `no PLUGIN_DATA here` is normal when you run it by hand: the client sets that variable, your shell does not. It says nothing about whether the server will find the key when the client starts it.

An agent *may* run `--show-key-source` — it spends nothing and reveals nothing.

---

## 6. Check the install worked

Work down this list. Stop at the first thing that fails and go to section 9.

**a. The client sees the server.**

In Claude Code, `/mcp` in a session, or from a terminal:

```bash
claude mcp list
```

The line to look for (verified format):

```
plugin:jevmcp:jevmcp: uv run --quiet --script /…/plugins/jevmcp/scripts/jevmcp_server.py - ✔ Connected
```

`plugin:<plugin>:<server>` — both parts are `jevmcp`. Anything other than `✔ Connected` is section 9.

**b. The tools are there.**

Four tools, no more and no fewer: `check_spec_drift`, `validate_spec_map`, `preview_spec_check`, `draft_spec_map`. In Claude Code they are addressed as:

```
mcp__plugin_jevmcp_jevmcp__check_spec_drift
mcp__plugin_jevmcp_jevmcp__validate_spec_map
mcp__plugin_jevmcp_jevmcp__preview_spec_check
mcp__plugin_jevmcp_jevmcp__draft_spec_map
```

**c. The skill loaded.** In Claude Code it is `jevmcp:spec-drift`. You do not need to mention the plugin for it to trigger; its frontmatter description does that.

**d. One free `validate_spec_map` call.** This is the real proof, and it costs nothing:

```json
{"project": "/absolute/path/to/the/project"}
```

Always pass `project` with the absolute path of the project folder — some clients (Codex) do not tell the server which project it is in, and it is harmless where they do. In Claude Code a `project` outside `CLAUDE_PROJECT_DIR` is refused.

Two answers both count as a **pass**:

| Answer | What it means |
|---|---|
| An error: `this project (<path>) has no spec map yet (no *spec_map.json). Set one up: draft_spec_map with the spec file(s), then review every entry.` | The server started, `uv` resolved its dependencies, and it is looking at the right project. The project simply has not been set up yet — go to [how-to.md](how-to.md). |
| A result with `ready`, `entries_to_check`, `excluded`, `problems`, `notes` | The project already has a spec map and the server read it. |

Because `validate_spec_map` is read-only and sends nothing, a pass proves the install, the dependencies and the project wiring — but it says **nothing about the key**. Only `check_spec_drift` needs the key. Prove the key with `--show-key-source` (section 5), not by spending credits.

**e. The command line, optionally.** From the project root:

```bash
uv run --quiet --script <plugin>/scripts/spec_drift.py --help
```

---

## 7. Updating

| Client | Command |
|---|---|
| Claude Code | `claude plugin update jevmcp@jevmcp` (or `/plugin` in a session). Restart is required to apply — Claude Code says *Restart to apply changes*. |
| Codex | `codex plugin marketplace upgrade` to refresh the marketplace snapshot, then `codex plugin remove jevmcp@jevmcp && codex plugin add jevmcp@jevmcp`. |

New tool families arrive this way: same plugin, same server, same key, no second install and no reconfiguration. Read [../CHANGELOG.md](../CHANGELOG.md) after an update — tools have been renamed before (1.3.0 renamed `check_drift` → `check_spec_drift`, `validate_map` → `validate_spec_map`, `draft_map` → `draft_spec_map`, `show_payload` → `preview_spec_check`), and a per-tool approval pinned by name in `~/.codex/config.toml` has to be re-approved under the new name.

The stored key is **not** touched by an update: `~/.config/jevmcp/typesafe.env` and the plugin data folder both survive.

---

## 8. Uninstalling

| Client | Command |
|---|---|
| Claude Code | `claude plugin uninstall jevmcp@jevmcp`, then `claude plugin marketplace remove jevmcp` if you also want the marketplace gone. |
| Codex | `codex plugin remove jevmcp@jevmcp`, then `codex plugin marketplace remove jevmcp`. |

Neither removes the stored key. To remove it, the user deletes `~/.config/jevmcp/typesafe.env` themselves. Claude Code's copy lives in its credential store; remove it with `/plugin manage` before uninstalling, or leave it.

`spec_map.json` belongs to the project and is committed with the code. Uninstalling the plugin does not touch it, and it should not be deleted — it is the reviewed work, not a cache.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A check fails with *No TypeSafe API key is set for this server, so nothing was sent.* | The server found no key in any of the four sources. | The error already names the fix. Claude Code: `/plugin manage` → jevmcp → *TypeSafe API key*. Any other client: the user runs `--set-key` in their own terminal (section 5). **Do not ask for the key in chat and do not run `--set-key` yourself.** `validate_spec_map` and `preview_spec_check` still work meanwhile. |
| Server fails to start; the log mentions `uv` | `uv` is not on the `PATH` the client gives the server. Clients pass a minimal environment (Codex: `HOME`, `LANG`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER`, plus declared `env_vars`). | Install `uv` (<https://docs.astral.sh/uv/>) and make sure it is on the `PATH` of the shell that launches the client — not only inside an interactive shell profile that a GUI launch never reads. |
| The very first start times out | `uv` is downloading and building the tree-sitter wheels. This happens once; afterwards uv's cold start is short. Codex allows 120 s and its `config.toml` cannot change a plugin server's start-up timeout. | Run once, outside the agent: `uv run --script ~/.codex/plugins/cache/jevmcp/jevmcp/<version>/scripts/jevmcp_server.py --help`. That fills uv's cache. Then start the client again. |
| *Restart to apply changes* | Claude Code re-reads plugins and starts MCP servers at session start. Installing, updating, enabling or changing the key mid-session does not reach a running server. | Restart Claude Code. If the key was the thing that changed, this is required — the server reads it once, at start-up. |
| `claude mcp list` shows anything but `✔ Connected`, or `/mcp` shows the server as failed | The server exited at start-up. Everything it prints that is not protocol goes to stderr, and Claude Code keeps it. | Read `~/.cache/claude-cli-nodejs/<encoded-project-path>/mcp-logs-plugin-jevmcp-jevmcp/`. Then reproduce by hand: `uv run --quiet --script <installed path>/scripts/jevmcp_server.py --help`. A traceback there is the real error. |
| The tools work but a tool call says *this client did not tell the server which project it is working in* | Codex starts the server in the plugin's own folder, so the server has no default project. | Pass `project` with the **absolute** path of the project folder in every tool call. Relative paths, the home folder and the filesystem root are all refused. |
| The first read of `SKILL.md` in Codex fails with a duplicated path segment, then succeeds on retry | Cosmetic. Codex's skill catalogue shortens `…/plugins/cache/jevmcp/jevmcp` to a root because the marketplace name and the plugin name are both `jevmcp`. | Nothing to fix. Do not reinstall. The retry finds the file. |
| Codex refuses `check_spec_drift` | Intended. It is declared a **write** action (`readOnlyHint: false`, `openWorldHint: true`) because code leaves the machine, so Codex asks every time — that approval *is* the user's consent. Under `codex exec` the approval policy is `never`, which blocks every MCP tool (*MCP tool call requires approval, but approval policy is never*), and `--approve-for-me` does not help: Codex's automatic reviewer refuses a tool that *may transmit project spec and code to the untrusted TypeSafe destination*. | Interactively: approve it. Unattended: see [clients.md](clients.md). The free tools can be allowed to run unattended with this in `~/.codex/config.toml`:<br>`[plugins."jevmcp@jevmcp".mcp_servers.jevmcp]`<br>`default_tools_approval_mode = "auto"` |
| A check inside a Codex session reports no drift suspiciously fast, or you are tempted to fall back to `spec_drift.py` there | **Codex's sandbox has no network.** A command-line run inside it silently reaches nothing. The MCP server runs *outside* the sandbox, which is why the tools work. | Never fall back to the command line inside a Codex session, and never report "no drift" from a run that could not reach TypeSafe (exit code **3**) — say the check did not run. |
| `--set-key` exits 2 with *asks for the key without echoing it, so run it in your own terminal* | You (an agent, or a pipe) tried to run it where stdin or stdout is not a terminal. | Correct behaviour. Hand the command to the user. |
| `--key-file …: give an absolute path` | The server was registered with a relative `--key-file`. A relative path would be read from inside the project being checked. | Use an absolute path, outside the project. |

Exit codes for the command-line checker, for CI: **0** no drift · **1** at least one DRIFT · **2** setup or map problem · **3** TypeSafe unavailable — do not block on it, and never report "no drift" from such a run.

---

## What happens next

The plugin is installed; the project is not yet set up. A project is set up once, with a `spec_map.json` that pairs each sentence of the spec with the code that implements it. `draft_spec_map` writes it; the user never writes it by hand; every entry then needs review. That is [how-to.md](how-to.md).

What each tool sends and what its labels mean: [tools.md](tools.md). Exactly what leaves the machine and what never does: [../PRIVACY.md](../PRIVACY.md).
