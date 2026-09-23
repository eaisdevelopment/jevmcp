<!-- Generated 2026-09-23 from the shipped plugin, jevmcp 1.5.3.
     Verbatim sources: plugins/jevmcp/skills/spec-drift/SKILL.md (sha256 413773695c920bdd...),
     tools/jevmcp_server.py (INSTRUCTIONS and TOOLS).
     Everything quoted is verbatim unless the text says it was reflowed. -->

# OpenAI Codex: the jevmcp spec-drift instruction

**The instruction is one file**, shipped inside the plugin at
`plugins/jevmcp/skills/spec-drift/SKILL.md`. OpenAI Codex and the other supported client read the
**same bytes** — sha256 `e0a6241c8c73f3fb...` — and nothing inside it is written for one client. What
differs is the *envelope*: how the text reaches the model, what the tools are called, whether
`project` is mandatory, when approval is asked, and where the API key comes from. That is in
[section 5](#5-what-is-different-in-openai-codex), and it is the only reason a second file exists.



There are **four layers**, and they load at different moments — which matters, because only
layers 1 and 2 sit in context permanently.

| Layer | What | Size | When it loads |
|---|---|---|---|
| 1 | The MCP server's `instructions` | ~1.2 kB, ~300 tokens | once, when the server connects |
| 2 | The skill's frontmatter `description` | 825 characters, ~200-230 tokens | at session start, always present |
| 3 | The skill body — the audit instruction | ~10.7 kB, ~3,000 tokens | only when the skill fires |
| 4 | Tool descriptions and JSON schemas | — | at call time |

In Codex the wrapper is thicker than in Claude Code, and three of its differences change what the
agent must actually do: **`project` must be passed on every call**, **every check asks for
approval**, and **the sandbox has no network**, so a command-line fallback inside a session is a
silent false pass rather than a fallback. Read section 5 before section 3 if you are debugging a
session.

---

## 1. Layer 1 — the server's instructions

Served at `initialize` / `server/discover` and shown to the model while the server is connected.
Verbatim from `jevmcp_server.py`:

```text
jevmcp puts TypeSafe's fast model Jev to work: it screens, you spend your effort only on what
it flags. Today it holds one family of tools, spec drift - does the code still match its
design spec or requirements document?

These tools work off a SPEC MAP: a file in the project (spec_map.json, committed with the
code) that pairs each sentence of the spec with the code that implements it. The user never
writes it by hand - draft_spec_map writes it and you review the entries with the user.
- No spec map in the project yet: draft_spec_map, then review every entry before any check.
- check_spec_drift after changing code (default: claims about the files git reports as
  changed); all=true for a full check. Labels: DRIFT = investigate each one; review = sorted
  by P(drifted), investigate from 0.3 up; ?? = NOT a pass (the code shown cannot settle the
  claim - fix that entry of the spec map); ok = spot-check a couple.
- validate_spec_map after editing the spec or the map (free, sends nothing).
- preview_spec_check to see exactly what would be sent for some claims (free).
Never pass or ask for the API key; the server holds it. If it is missing, the error says the
one command the user runs to store it.
```

---

## 2. Layer 2 — the trigger

This one paragraph is the whole discovery mechanism: it is all the model sees until the skill
fires, and it is why nobody has to name the plugin. Verbatim (reflowed to fit the page; it is a
single line in the file):

```text
Check whether a project's code still matches its design spec or requirements document. A fast
model (TypeSafe's Jev) screens every requirement in seconds; you investigate only what it
flags. A project is set up once with a spec map (spec_map.json), which pairs each requirement
sentence with the code that implements it; the draft_spec_map tool writes it, the user never
writes it by hand. Use when the user asks whether code matches the spec, design or
requirements; after changing code in a project that has a *spec_map.json (before you finish the
task); when a spec is edited; before a release; or to set up spec-drift checking for a project.
Works with Java/Spring, JavaScript/TypeScript (Node, NestJS, Express, Hono, Fastify, Next.js)
and Python (FastAPI, Flask, Django), and with any other language through line ranges.
```

Note what it does: it names **symptoms and moments** ("after changing code in a project that has a
`*spec_map.json`", "before a release"), not a product. That is what makes an agent reach for it
unprompted.

---

## 3. Layer 3 — the audit instruction in full

Everything below this line is the body of `SKILL.md`, verbatim. This is the instruction proper.

---

# Spec drift check

**Division of labour.** The fast model screens every spec requirement against the code that
implements it and labels each one. **You** spend your effort only on what it flags, on what it
cannot judge, and on its known blind spots. Do not re-read the whole spec and codebase yourself
to do its job, and never call the TypeSafe API by hand: the checker's questions and thresholds
are measured, pinned and tested.

A project is set up once: a **spec map** — the file `spec_map.json` (usually next to the spec,
committed with the code) that pairs each requirement sentence with the code that implements it, or
marks it excluded with a reason. **The user never writes it by hand**: `draft_spec_map` writes it
and you review the entries with the user. After that, every check is seconds and fractions of a cent.

## The tools

**Use the MCP tools when they are available** (server `jevmcp`): `check_spec_drift`,
`validate_spec_map`, `preview_spec_check`, `draft_spec_map`. They keep the parsed code in memory and hold the
API key themselves. Pass `project` with the absolute path of the project (your working
directory) in every call: some clients do not tell the server which project it is in. Where the
client does tell it (Claude Code starts the server in the project), `project` must be that same
folder or one inside it - another project is refused.

Otherwise use the command line, from the project's root. It needs network access to reach
TypeSafe (and, the first time, to install its Python dependencies); in a sandbox without network
- Codex's default sandbox is one - the command line silently reaches nothing, so use the MCP
tools, which run outside the sandbox. **Never report "no drift" from a run that could not reach
TypeSafe** (exit 3): say the check did not run.

```bash
DD="uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/spec_drift.py"
$DD --help                      # every option, explained
```

If `${CLAUDE_PLUGIN_ROOT}` above is not already a real path, the plugin's `scripts/` folder is
two folders above this SKILL.md: `../../scripts/spec_drift.py`, relative to this file.

| Job | MCP tool | Command line |
|---|---|---|
| Check claims about changed files | `check_spec_drift` (default: git's changed files; `files: [...]` to name them) | `$DD --map <map> --changed --jobs 8 --out <tmp>/drift.json` |
| Full check | `check_spec_drift` with `all: true` | `$DD --map <map> --jobs 8 --out <tmp>/drift.json` |
| Validate the map (free) | `validate_spec_map` | `$DD --map <map> --dry-run --strict` |
| See exactly what is sent (free) | `preview_spec_check` | `$DD --map <map> --dry-run --show-payload` |
| Draft a map for a new project (free) | `draft_spec_map` | `$DD --docs <spec> --draft-map <spec folder>/spec_map.json` |

Write results to a temporary folder, not into the repository. Exit codes: **0** no drift ·
**1** at least one DRIFT · **2** setup or map problem, fix it (the output names each broken
entry, usually with "Did you mean") · **3** TypeSafe unavailable: say so, carry on without it,
never block the user's task on it.

## Before any code is sent

- **Consent, once per project.** A check sends each spec sentence and its paired code (comments
  removed, secret-looking values redacted, paths relative) to `api.typesafe.ai`. Before the first
  real check in a project, tell the user that and get a yes, unless they have already said so
  in this conversation or the project's CLAUDE.md or AGENTS.md records it. The dry-run and
  `preview_spec_check` send nothing and need no consent.
- **The key.** The MCP server gets it from the plugin's settings (Claude Code asks for it when
  the plugin is enabled), from `TYPESAFE_API_KEY` in the environment that starts the agent, or
  from the file the user stored with `jevmcp_server.py --set-key`; never from the project's own
  `.env`. If it is missing, the tool error names the one command the user runs in their own
  terminal — pass that on, and never run it yourself or ask for the key in chat. The command line uses `--key-file` if given, otherwise
  `TYPESAFE_API_KEY`, otherwise a `TYPESAFE_API_KEY=` line in the `.env` of the folder it runs
  from. If the key is missing, tell the user where to set it and stop. Never ask for the key in chat, never print it, never pass it on a command line you
  show.

## A. Setting up a project that has no spec map

1. **Find the spec.** Look for design, specification, requirements or architecture documents
   (Markdown or reStructuredText). If there are several candidates, ask which one is the source
   of truth.
2. **See what the tool can read:** `$DD --docs <spec> --dry-run`. It reports the languages,
   routes and config keys it found, and lists the sentences it cannot pair on its own. If it
   says a parser is missing or a language can only be paired by line range, note it.
3. **Draft the map** with `draft_spec_map` or `--draft-map`. It suggests code for every sentence;
   the suggestions are guesses.
4. **Review every entry. This is the important step, and it is your job.**
   - The code could contradict the sentence (a number, a name, a format, an ordering, a
     must/never/only, what ships in this version): point `code` at what **enforces** it, and set
     `"status": "reviewed"`. Point at the implementation, not only the interface; at the
     constant, so the value is visible; at the wiring, if the claim is about which piece is used.
     Code references:
     `route:GET /api/orders/{id}` · `config:app.orders.max-items` · `src/Orders.java:OrderService.place`
     · `src/app.ts:120-160` (a line range, any language) · `src/config.py` (a small whole file)
     · or a list of several.
   - It is not a requirement (thesis, rationale, history, comparisons, glossary, examples,
     lead-ins, backlog): set `"status": "excluded"` and say why in `"why"`. A backlog or rationale
     sentence that constrains today's code *is* a requirement.
   - Tables, byte layouts and config examples inside code blocks are skipped by the drafter: add
     those entries by hand, with the requirement written out in `text` and the block's lines
     pasted into `spec_text`.
   - A sentence about what the code **never** does cannot be settled by pairing (blind spot 5):
     exclude it with a `why` that says how you checked it, or reword the spec.
   - For a long spec, work section by section. If the user wants it done thoroughly, offer a
     second pass that tries to refute each exclusion; it finds real requirements hidden in
     rationale and backlog.
5. **Validate:** `validate_spec_map` or `--dry-run --strict` must report no problems.
6. **With consent, run the first full check**, then report (below). Suggest committing the map,
   and adding the free `--dry-run --strict` check to CI so new spec sentences cannot go unmapped.

## B. The routine check (the project has a map)

- **After changing code**, before you say the task is done: check claims about the changed
  files. Nothing in the map is about them? Then there is nothing to check; say so.
- **After editing the spec or the map:** validate the map.
- **Before a release, or when asked:** the full check.

## What to do with each result

| Label | Your job |
|---|---|
| **DRIFT** | Investigate every one. Read the claim and the code that was sent, then the real code around it. Decide which side is wrong: the history of the code (`git log -p`, `git blame`) usually shows whether the change was deliberate (the spec is stale) or accidental (a bug). |
| **review** | Sorted by P(drifted). Investigate from 0.3 up; skim below that. |
| **??** | **Not a pass.** The code shown cannot settle the claim. Fix the map entry (add the implementation, the constant, the caller), then check that file again. |
| **ok** | Spot-check two, plus any whose `value_mismatch` is 0.5 or more. |

## Always judge these yourself: the fast model's blind spots

1. **Settings hard-coded in code.** `Map.of("cache.backend", "redis")` or a dict literal reads
   as "configuration" to the fast model. A claim that something is "configurable", "selected by
   a setting" or "changed without a rebuild" needs your judgement whatever its label.
2. **Library and platform behaviour** (what a JDK call or a framework default actually does).
3. **Arithmetic on variables** (`avg / 2`). The tool works out literal expressions only.
4. **Anything spanning several files**: module dependencies, who calls what, "only X does Y".
5. **A claim about what the code does NOT do** - "never", "only", "no telemetry", "to nobody but".
   No excerpt can settle it: code that does not do X proves nothing, and the one place that does
   X reads as a refutation. Pairing "sends no telemetry" with the single function that makes a
   request returned a confident DRIFT against correct code. Exclude such a sentence with a `why`
   recording how you verified it by hand, or reword the spec into a positive claim about the one
   place involved ("the only request the tool makes is the check itself").

A low P(drifted) on one of these is not a pass.

## Keep it proportionate

A routine check exists so that you do not have to review everything. Investigate the flagged
items in the repository. Do not start workflows or sub-agents, search outside the repository,
or build and run code to prove a finding unless the user asks for a deep review; say what you
would verify and how instead.

**A big spec flags a lot.** A full check on a few hundred sentences can return dozens of
`review` items; opening every one takes longer than the user is waiting for. In one pass do:
every **DRIFT**; the highest-P **review** items until they stop being informative (about ten is
usually plenty); and the **??** items that matter for what the user is doing, since those are
map problems to fix. Give counts for the rest and say plainly how many you did not open, so the
user can ask for another pass. One reply beats twenty minutes of silence.

## Keeping the map honest

- **Code renamed or moved:** the tool names the broken entry and suggests the closest name.
- **"the spec changed since this entry was reviewed":** re-read the entry against the current
  spec, update `text` if the requirement changed, and paste the current paragraph into
  `spec_text` (markdown and line breaks are fine).
- **"N sentences ... are not in the map":** decide each one, as in step A4.
- **"excluded sentences have changed":** decide again; rewording can turn rationale into a rule.
- Never delete an entry or blank a `spec_text` to make the strict check pass, and never change
  an exclusion without saying so in your report.
- A lesson specific to this project (a blind spot seen twice, a file every claim needs) belongs
  in the project's CLAUDE.md or AGENTS.md under "Spec drift". Suggest adding it; read it if present.

## How to report back

A short table: claim (spec file:line) · label · P(drifted) · what you found · which side to fix
(spec / code / ask the owner). Then your recommendation. If an earlier drift report exists in
the project, say which findings are new and which are already known.

**Never:** send code without consent, print or ask for the key, treat `??` as a pass, overwrite
a reviewed map, change the checker's questions or thresholds, commit without asking, or block the
user's task on exit 3.

---

*(End of the verbatim skill body.)*

---

## 4. Layer 4 — the four tools

Read at call time, from the server's `tools/list`. Descriptions and schemas verbatim.

### `check_spec_drift`

*Check the code against the spec* · `readOnlyHint: false` · `openWorldHint: true` · **sends code to `api.typesafe.ai`**

> Check code against the spec with TypeSafe's fast model and return the results, most important first: DRIFT, then 'review' sorted by P(drifted), then '??' (not a pass), then a count of 'ok'. By default only claims about the files git reports as changed are checked (a few seconds, fractions of a cent). Sends the spec sentence and the paired code (comments removed, secrets redacted) to TypeSafe.

| Argument | Type | Description |
|---|---|---|
| `files` | array | Check only claims about these files (paths relative to the project). Leave out to use the files git reports as changed. |
| `all` | boolean | Check every claim in the map - a full check. Default false. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `validate_spec_map`

*Validate the spec map (spec-to-code pairings)* · `readOnlyHint: true` · `openWorldHint: false` · free — sends nothing

> Check that the spec map still fits the spec and the code - every reference resolves, nothing is stale, and (strict, the default) every spec sentence is either mapped or marked excluded with a reason. Free: sends nothing. Run after editing the spec or the map.

| Argument | Type | Description |
|---|---|---|
| `strict` | boolean | Also report unmapped sentences, unreviewed entries, exclusions without a 'why'. Default true. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `preview_spec_check`

*Show what a check would send* · `readOnlyHint: true` · `openWorldHint: false` · free — sends nothing

> Show exactly what check_spec_drift would send to TypeSafe for some claims: the sentence, the code with comments removed and secrets redacted, any computed values, and the 3 fixed questions. Free: sends nothing.

| Argument | Type | Description |
|---|---|---|
| `files` | array | Claims about these files. Leave out (and leave out 'line') for the files git reports as changed. |
| `line` | integer | Only the claim(s) from this line of the spec. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `draft_spec_map`

*Draft the spec map (pair each requirement with code)* · `readOnlyHint: false` · `openWorldHint: false` · free — sends nothing

> Set up a project that has no spec map yet: suggest a code location for every sentence of the spec(s) and write them to a new map file for review. Every entry must then be reviewed - point 'code' at what enforces the sentence and set status 'reviewed', or set status 'excluded' with a 'why' - before check_spec_drift is worth running. Free: sends nothing. Never overwrites a file.

| Argument | Type | Description |
|---|---|---|
| `docs` **(required)** | array | The spec file(s) or folder(s), relative to the project. |
| `out` **(required)** | string | The new map file, relative to the project - usually next to the spec, named spec_map.json. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |


Every tool also accepts `project`; see section 5 for whether it is optional here.

---

## 5. What is different in OpenAI Codex

### Install

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jev
```

Codex reads `.agents/plugins/marketplace.json` at the repository root, then the **portable**
package: `plugins/jevmcp/plugin.json` (its store listing sits under
`extensions."com.openai".interface`) and `plugins/jevmcp/mcp.json`, which starts the server with
`${PLUGIN_ROOT}/scripts/jevmcp_server.py`. `plugins/jevmcp/.codex-plugin/plugin.json` is an overlay
adding only key forwarding and timeouts:

```json
{"command": "uv", "args": ["run", "--quiet", "--script", "./scripts/jevmcp_server.py"],
 "cwd": ".", "env_vars": ["TYPESAFE_API_KEY"],
 "startup_timeout_sec": 120, "tool_timeout_sec": 600}
```

Codex merges an overlay entry only when it is a complete server definition; the portable `mcp.json`
still decides the command (checked with `codex mcp list --json`). Installed copies live at
`~/.codex/plugins/cache/jev/jevmcp/<version>/`, and `~/.codex/config.toml` gains
`[plugins."jevmcp@jev"] enabled = true`.

### How the instruction reaches the model

**Codex injects the skill's frontmatter `description` verbatim into a `<skills_instructions>`
developer message at session start.** That text is the whole trigger — layer 2 above, unchanged.
The body is read from disk when the skill fires. The server's `instructions` block is served at
`initialize` / `server/discover` as usual.

### Tool names

The tools keep their **plain names** on server `jevmcp`:

```
check_spec_drift   validate_spec_map   preview_spec_check   draft_spec_map
```

In `~/.codex/config.toml` their table is `[plugins."jevmcp@jev".mcp_servers.jevmcp]`. If a tool was
approved by name before 1.3.0 that approval no longer matches (`check_drift` -> `check_spec_drift`,
`validate_map` -> `validate_spec_map`, `show_payload` -> `preview_spec_check`, `draft_map` ->
`draft_spec_map`): approve the new name once.

### The API key — there is **no** prompt

Codex has no mechanism for asking for a secret. Two options, both in the user's own terminal —
never inside a Codex session, and never as a command-line argument:

**1. Store it once (recommended).**

```bash
uv run --quiet --script \
  "$(ls -d ~/.codex/plugins/cache/jev/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" \
  --set-key
```

`--set-key` asks without echoing, **refuses to run unless stdin and stdout are both a terminal** so
an agent cannot run it, writes `~/.config/jevmcp/typesafe.env` mode 0600 inside a 0700 directory,
and survives plugin updates.

**2. Or `export TYPESAFE_API_KEY=...`** in the shell that starts Codex; the overlay's `env_vars`
forwards it. The cost: Codex's shell tool inherits the user's environment, so the model *could*
read the key with `env`. The stored key file cannot be read that way.

Check without printing it: `... jevmcp_server.py --show-key-source` (exit 0 if a key is found,
1 if not).

### `project` is **mandatory on every call**

The overlay sets `cwd: "."`, so Codex starts the server **inside the plugin's own folder**, and
Codex does not tell the server which project the session is in. The server detects this — its
working folder is under its own plugin root — and refuses to guess:

```
this client did not tell the server which project it is working in - pass project:
the absolute path of the project folder (your working directory).
```

A relative path is refused (`project must be an absolute path`); a home folder or `/` is refused
(`is a home or root folder, not a project`). This is why the skill body says to pass `project` in
every call.

### Approval — **every check, by design**

`check_spec_drift` is a write action (`readOnlyHint: false`, `openWorldHint: true`) because it
sends code to `api.typesafe.ai`, so **Codex prompts before each call**. That prompt *is* the user's
consent for that check. Do not try to route around it.

The three free tools can run unattended if the user adds to `~/.codex/config.toml`:

```toml
[plugins."jevmcp@jev".mcp_servers.jevmcp]
default_tools_approval_mode = "auto"
```

### Network — the trap that matters most

**Codex's sandbox has no network.** A fallback to the command line *inside* a Codex session
therefore reaches nothing: the run cannot call TypeSafe and comes back having found no drift. That
is a **silent false pass**. Use the MCP tools, which work because the MCP server is started outside
the sandbox — and never report an exit-3 run as "no drift".

Codex passes the server a minimal environment — `HOME`, `LANG`, `LOGNAME`, `PATH`, `SHELL`, `TERM`,
`USER`, plus the declared `TYPESAFE_API_KEY` — along with `PLUGIN_ROOT` and `PLUGIN_DATA`.

### Update, and two quirks

`codex plugin remove jevmcp@jev && codex plugin add jevmcp@jev` — Codex caches the marketplace
snapshot, so removing the marketplace too is sometimes needed.

- **Skill paths.** Codex's skill catalogue lists a root plus a path under it, and a model can
  shorten that wrongly when the two repeat a name. Up to 1.4.1 the marketplace and the plugin were
  both called `jevmcp`, and the first read of `SKILL.md` failed on a duplicated segment in **every**
  session before the retry succeeded. Since 1.5.0 the marketplace is `jev`, so the path is
  `.../plugins/cache/jev/jevmcp/<version>/skills/...` with nothing repeated. If you still see the
  old failure, the plugin came from the old marketplace: remove it and add it again.
- **First start can time out** while uv downloads the tree-sitter parsers. Run
  `uv run --script ~/.codex/plugins/cache/jev/jevmcp/<version>/scripts/jevmcp_server.py --help`
  once so uv caches them, then start Codex again. Codex's `config.toml` cannot change a plugin
  server's startup timeout; the overlay already asks for 120 s.

---

## 6. Verified behaviour

Checked on 2026-09-22 against `codex-cli 0.155.1`.

- **Discovery works with no mention of the plugin: 3/3.** Three neutral prompts loaded the skill;
  a control prompt ("What does this project do?") correctly did not.
- **A fresh install from GitHub in an isolated Codex home, end to end**: skill loaded unprompted,
  `draft_spec_map` wrote the map, the agent reviewed and corrected the drafter's guesses,
  `validate_spec_map` passed, the agent **stopped for consent**, and with consent found all 4
  planted drifts with no false alarms. ~25k tokens per session.
- **The key never appeared in any transcript** (0 occurrences across four session logs).
- **On a real project** (131 mapped claims, ~12 s, $0.006): 4 DRIFT, 104 review, 21 `??`, 2 ok.
  The repository was not modified.
- **Unattended / CI — exactly what fails:**

| Command | Result |
|---|---|
| `codex exec '...'` | Every MCP tool is blocked: *"MCP tool call requires approval, but approval policy is never"*. `codex exec` runs with approval policy `never`. |
| `codex exec --approve-for-me '...'` | Still refused. Codex's automatic reviewer rejects `check_spec_drift` because it *"may transmit project spec and code to the untrusted TypeSafe destination"*. |
| `codex exec --dangerously-bypass-approvals-and-sandbox '...'` | **Works** (verified: 3 DRIFT on the demo project). It switches off the sandbox *and* all approvals, so use it only where the whole job is already isolated, such as a CI container. |

  Better for CI: skip the agent and run the checker where the network works —
  `uv run --script <plugin>/scripts/spec_drift.py --map spec_map.json` (exit codes 0/1/2/3).

---

## 7. Where this came from

Three rules in the skill body exist because a session went wrong, which is worth knowing when you
read them:

- **"Keep it proportionate"** (the triage budget) was added in 1.5.1 after both clients, told to
  investigate everything flagged on a 131-claim spec, ran for more than fifteen minutes and
  reported nothing.
- **"Never report 'no drift' from a run that could not reach TypeSafe"** exists because a
  sandboxed shell has no network, so the command-line fallback silently reached nothing and looked
  like a pass.
- **The blind-spots list** is measured, not guessed. Blind spot 1 (a `Map.of(...)` literal reads as
  "configuration") is exactly why the most important drift found in a real-project pilot scored
  *accurate* at
  0.87-0.94 and was caught only by the clean-gate threshold.

## 8. Related

| Page | What is in it |
|---|---|
| `plugins/jevmcp/docs/install.md` | Installing, step by step, per client |
| `plugins/jevmcp/docs/tools.md` | The four tools, arguments and output in detail |
| `plugins/jevmcp/docs/clients.md` | Every client difference, side by side |
| `plugins/jevmcp/docs/how-to.md` | Recipes: first set-up, routine check, CI |
| `plugins/jevmcp/PRIVACY.md` | What is sent, what never is |
