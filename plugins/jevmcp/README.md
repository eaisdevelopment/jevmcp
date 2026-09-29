# jevmcp — TypeSafe's fast model as routine tooling for your coding agent

**One plugin, installed once.** It gives **Claude Code** and **OpenAI Codex** (both tested) the
tools that put TypeSafe's fast model **Jev** to work: the fast model screens everything in seconds
and for fractions of a cent, and your agent spends its own effort only on what was flagged. Built
on the portable [Agent Plugins](https://agent-plugins.org) format, so other clients of that format
can load it too.

New tools are added to this same plugin — you do not install or configure anything again, you
update it (`claude plugin update jevmcp@jev`).

## What is in it

Three tool families, each with its own skill, all on one MCP server:

- **Spec drift** — does the code still match the project's design spec or requirements
  document? Your agent checks after it changes something, and before a release. On a real Java
  project (131 requirements), measured before 1.6.0, when each claim was asked once: a check after
  editing two files took 3 seconds and cost $0.0013; a full check took 11 seconds and cost $0.006.
  Since 1.6.0 a claim the first answer does not settle is asked up to twice more, so a first check
  costs more; a repeat on unchanged code is answered from the cache. Tools: `check_spec_drift`,
  `validate_spec_map`, `preview_spec_check`, `draft_spec_map`; skill `spec-drift`.
- **CI failure triage** — what actually broke in a failed CI run? Jev reads each distinct
  failure with the change under test and says whether the change caused it; "not the change" is
  never decided for you. Reads a GitHub Actions run of your project with your own `gh` login, or
  a log from any CI. Tools: `triage_ci_failure`, `preview_ci_triage`; skill `ci-triage`.
- **Code audit** — does the code break the project's own written rules (CLAUDE.md, AGENTS.md,
  CONTRIBUTING, style guides)? Jev checks one reviewed rule against one unit of code at a time.
  Tools: `check_code_rules`, `preview_code_audit`, `validate_rule_map`, `draft_rule_map`; skill
  `code-audit`.

**One MCP server** (`jevmcp`) holds all ten tools. It keeps the parsed code in memory, so after an
edit only the changed files are read again (a 16,000-file repository: ~2 s instead of ~20 s), and
it holds your API key so the agent never sees it. Every tool that sends has a free preview, and
the skills ask for your consent before the first send of each kind of data in a project.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) 0.4.19 or newer on your PATH (an older uv stops with
  `unexpected argument '--script'`). The first run installs the Python dependencies (tree-sitter,
  PyYAML), and a Python if yours is older than 3.10, into uv's cache; nothing is installed into
  your project.
- `git` on your PATH. The marketplace install already needs it. The tools use it to find the
  changed files for a routine check, which files git ignores (without it no code-audit tool works
  in a git project), the change under test for CI triage with `base`, this project's GitHub remote
  to triage a run by its URL, and the last commit of each spec. Without it, name the files for a
  spec check, and triage a saved log without `base`.
- A TypeSafe API key — get one at <https://console.typesafe.ai> — for the three tools that send
  data. The draft, validate and preview tools work without it. One key serves every tool in the
  plugin.
- Linux, macOS or Windows. On all three, CI starts the server from an empty uv cache on every
  change to the plugin, runs the seven free tools and checks that the three that send refuse without a key. The
  three that send have been run with a real key on Linux only. Every file is read and written as
  UTF-8, and a CI log or rule file that Windows PowerShell 5.1 saved as UTF-16 is read too, so
  specs, rules and logs in any language work on Windows too; so do non-ASCII file names on Linux
  under a locale whose file names are not UTF-8 (an 8-bit one, or C with Python's UTF-8 mode off),
  where the tools start themselves again in Python's UTF-8 mode. Under an 8-bit locale, a file
  whose name was saved in that locale's own encoding is then not found: rename it in UTF-8, or set
  `JEVMCP_NO_UTF8_RESTART=1` to turn the restart off (in Claude Code, in the shell that starts it;
  Codex does not pass it to the server, so there it reaches only the command lines). The key
  command for Codex below
  is for bash or zsh; on Windows, give the full path of `jevmcp_server.py` instead.
- Optional: the GitHub CLI, [`gh`](https://cli.github.com), logged in — only to triage a GitHub
  Actions run by its URL. A CI log saved as a file needs nothing extra.

## Install

**Claude Code**

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jev
```

When you install or enable the plugin in the interactive `/plugin` screen, Claude Code shows a
*TypeSafe API key* field. It is optional: leave it empty to use only the free tools, and set or
change it any time with `/plugin configure jevmcp@jev`. Claude Code keeps it out of every settings file (in the macOS
Keychain, or `~/.claude/.credentials.json` on other systems). `claude plugin install` from a shell
never asks; enter the key in `/plugin configure` rather than with `claude plugin install --config`,
which would leave it in your shell history.

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

The three tools that send (`check_spec_drift`, `triage_ci_failure`, `check_code_rules`) are marked as
write actions, because data leaves your machine: Codex asks you before each call — that is your
consent. The free tools can run without asking if you add to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jev".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

**Unattended runs in Codex** (tested 2026-09-22 with Codex 0.155.1 and 2026-09-24 with 0.156.1):
`codex exec` runs with approval policy "never", which blocks every tool that sends ("MCP tool call
requires approval"); with 0.156.1 the free, read-only tools such as `preview_ci_triage` still ran.
`--approve-for-me` does not help — Codex's automatic reviewer refuses a tool that sends code to a
third party. Two honest options:

- `codex exec --dangerously-bypass-approvals-and-sandbox '...'` — the check then runs (verified).
  The flag switches off Codex's sandbox and all approvals, so use it only where the whole job is
  already isolated, such as a CI container.
- Better for CI: skip the agent and run the scripts directly, where the network works:
  `uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json` (exit 1 on drift, 2 on a
  map problem, 3 if TypeSafe is unavailable), and likewise `ci_triage.py` and `code_audit.py`.

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

## First run in a project: the maps

You never write or edit a file yourself. Ask your agent, in the project:

> Set up spec-drift checking for this project. The spec is in specification/final.

1. **You name the spec** — files or a folder — and exactly that is checked, never second-guessed.
   If you do not name it, the agent lists the files that look like specs (design, requirements,
   architecture, ADR or RFC documents), each with its last commit date and hints about old copies
   (a version number or date in the name, a folder such as `archive/`, a line near its top that
   says "superseded"), and asks you to choose.
2. `draft_spec_map` **writes `spec_map.json` for you** from what you named — one entry per sentence of
   the spec, each with a suggested place in the code. Free: nothing is sent anywhere.
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

**Code audit works the same way, with `rule_map.json`.** Ask *"Set up a code audit for this
project"*: `draft_rule_map` collects the rules from your own rule files, and the agent reviews
them with you — it rewrites each into one plain condition, says which files it covers, and leaves
out rules about process, rules a linter already checks, and instructions to the assistant itself. Only the rules you approve are ever sent.

**CI triage needs no set-up.** Give the agent a failed run's URL, or a CI log.

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

- *"Set up spec-drift checking for this project"* — it lists the files that look like specs and
  asks you which is current, drafts a **spec map** from the file(s) you name that pairs each
  requirement with the code that implements it, reviews every entry with you, and validates it.
  The map (`spec_map.json`) belongs in your repository.
- *"Check my changes against the spec"* — after that, a check is seconds.
- *"Why did CI fail on this pull request?"* or *"Triage https://github.com/OWNER/REPO/actions/runs/123"*
  — it reads the failed run, shows you what would be sent, and with your yes says for each failure
  whether your change caused it and what to do next.
- *"Set up a code audit for this project"*, then *"Audit my branch against our rules before I open
  the pull request"* — it checks the units your branch touches against each rule you approved.
- *"Run a full spec-drift check before the release"* — every requirement, with a report of what
  to fix and on which side (code or spec).

The agent also checks by itself after changing code in a project that has a spec map. It never
runs a code audit after every edit: only when you ask, or before a pull request.

## Languages

| Language | Understood |
|---|---|
| Java | classes, methods, constants; Spring routes (class and method mappings, constant paths, API-first interfaces), `@Value`, `@ConfigurationProperties`, `application*.yml/.properties` per profile |
| JavaScript / TypeScript | functions, classes, constants; NestJS, Express, Hono, Fastify (mounts followed across files), Next.js file routes; `process.env`, `import.meta.env` |
| Python | functions, classes, constants; FastAPI, Flask, Django routes; `os.environ`, pydantic settings |
| Also | OpenAPI files; `.env` templates (never a real `.env`) |
| Any other language | by line range (`src/main.go:120-160`) or a small whole file |

**Spec languages.** Specs in English, the other languages written in the Latin alphabet, Chinese,
Japanese and Korean are read sentence by sentence. Other languages are not processed properly:

| Spec written in | What happens |
|---|---|
| Turkish, Czech, Slovak, Polish, Swedish and other Latin-alphabet languages whose sentences can start with `Č`, `Ş`, `İ`, `É`, `Ö`, `Ł` | such a sentence stays joined to the one before it |
| Russian, Ukrainian, Bulgarian, Serbian Cyrillic, Mongolian, Greek, Arabic, Persian, Hebrew, Hindi, Bengali, Tamil, Sinhala, Georgian, Armenian, Amharic, Burmese | sentences are not split: each paragraph or list item is one entry, so a drift in one of its requirements can be missed |
| Thai, Lao, Khmer, Tibetan | a sentence with no spaces counts as one word and is dropped; most of the spec is not checked |

Workarounds and the measurements are in [docs/tools.md](docs/tools.md#the-spec-map).

## What is sent, and what never is

Three tools send data to `api.typesafe.ai`, each a different kind, and the agent asks for your
consent before the first send of each kind in a project:

- **Spec drift**, per requirement: the spec sentence; the code paired with it, with **comments
  removed** (Python, Java, JavaScript/TypeScript and other C-family languages; other files are
  sent as written), **secret-looking values redacted** and **paths relative to your project**;
  and three fixed questions.
- **CI triage**, per distinct failure: facts about the run, the failed step's error lines and the
  end of its output, and an excerpt of the change under test — log lines cleaned of GitHub's line
  timestamps, workspace paths, home folders, email addresses and secret-looking values; secret
  files and comment-only lines left out of the change. Never the commit message or the pull request's text.
- **Code audit**, per rule and unit of code: the rule you approved and the unit, with comments
  removed (except for rules about comments) and secret-looking values redacted. Only files git
  tracks or would commit, never ignored ones.

A `.env` file, key and credentials files (`.netrc`, `.npmrc`, `kubeconfig`, Terraform state, ...),
and anything outside the project (apart from CI logs you save in the server's private inbox) are
refused, never sent. Each sending
tool has a free preview — `preview_spec_check`, `preview_ci_triage`, `preview_code_audit` (or
`--dry-run --show-payload`) — that shows exactly what would be sent, without sending it.
[PRIVACY.md](PRIVACY.md) has the details, including exactly which values are redacted.

## Command line

The same checks run without an agent, from the folder of the project you are checking:

```bash
uv run --script <path to this plugin>/scripts/spec_drift.py --help
uv run --script <path to this plugin>/scripts/ci_triage.py --help
uv run --script <path to this plugin>/scripts/code_audit.py --help
```

(In a clone of this repository the scripts are in `plugins/jevmcp/scripts/`.) They work in CI
too: `spec_drift.py --dry-run --strict` validates the map for free (exit 2 if a spec sentence is
neither mapped nor excluded); a real run exits 1 on a finding (DRIFT, CHANGE, BREAKS) and 3 when
TypeSafe is unavailable. `spec_drift.py` reads the key from `--key-file`, else `TYPESAFE_API_KEY`,
else a `TYPESAFE_API_KEY=` line in the `.env` of the folder you run it from; `ci_triage.py` and
`code_audit.py` never read a `.env`.

## Standards

- **Agent Plugins 1.0.0**: root `plugin.json` and `mcp.json` validate against the official schemas;
  client-specific settings sit under `extensions` (`com.openai` for the Codex listing) or in the
  clients' own folders (`.claude-plugin/`, `.codex-plugin/`).
- **Agent Skills**: `skills/spec-drift/SKILL.md`, `skills/ci-triage/SKILL.md` and
  `skills/code-audit/SKILL.md` use only the portable frontmatter fields.
- **MCP 2026-07-28**: stateless requests with `server/discover`, per-request `_meta`, `resultType`,
  caching hints, structured tool output, progress and cancellation, and prompt shutdown when the
  client closes the connection; clients of earlier MCP revisions (which open with `initialize`)
  are served too.

## Documentation

- [Install and set up](docs/install.md) · [Tools, skills and maps](docs/tools.md) ·
  [Client behaviour and limits](docs/clients.md) · [Recipes](docs/how-to.md) ·
  [Privacy](PRIVACY.md)
- These pages ship with the plugin, so an agent can read them after installing it.

## Support

Questions and bugs: <https://github.com/eaisdevelopment/jevmcp/issues>. Security problems: see
[SECURITY.md](https://github.com/eaisdevelopment/jevmcp/blob/main/SECURITY.md).

## License

Apache-2.0 — see [LICENSE](LICENSE).
