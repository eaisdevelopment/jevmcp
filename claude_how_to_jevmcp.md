<!-- Generated 2026-09-23 from the shipped plugin, jevmcp 1.5.2.
     Verbatim sources: plugins/jevmcp/skills/spec-drift/SKILL.md (sha256 e0a6241c8c73f3fb...),
     tools/jevmcp_server.py (INSTRUCTIONS and TOOLS).
     Everything quoted is verbatim unless the text says it was reflowed. -->

# Claude Code: the jevmcp spec-drift instruction

**The instruction is one file**, shipped inside the plugin at
`plugins/jevmcp/skills/spec-drift/SKILL.md`. Claude Code and the other supported client read the
**same bytes** — sha256 `e0a6241c8c73f3fb...` — and nothing inside it is written for one client. What
differs is the *envelope*: how the text reaches the model, what the tools are called, whether
`project` is mandatory, when approval is asked, and where the API key comes from. That is in
[section 5](#5-what-is-different-in-claude-code), and it is the only reason a second file exists.



There are **four layers**, and they load at different moments — which matters, because only
layers 1 and 2 sit in context permanently.

| Layer | What | Size | When it loads |
|---|---|---|---|
| 1 | The MCP server's `instructions` | ~1.2 kB, ~300 tokens | once, when the server connects |
| 2 | The skill's frontmatter `description` | 825 characters, ~200-230 tokens | at session start, always present |
| 3 | The skill body — the audit instruction | ~10.7 kB, ~3,000 tokens | only when the skill fires |
| 4 | Tool descriptions and JSON schemas | — | at call time |

In Claude Code the wrapper is thin: the client starts the server in your project, asks you for the
key when you enable the plugin, and applies its ordinary MCP permission to the one tool that sends
data. Most of what follows is therefore the instruction itself.

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

### `mcp__plugin_jevmcp_jevmcp__check_spec_drift`

*Check the code against the spec* · `readOnlyHint: false` · `openWorldHint: true` · **sends code to `api.typesafe.ai`**

> Check code against the spec with TypeSafe's fast model and return the results, most important first: DRIFT, then 'review' sorted by P(drifted), then '??' (not a pass), then a count of 'ok'. By default only claims about the files git reports as changed are checked (a few seconds, fractions of a cent). Sends the spec sentence and the paired code (comments removed, secrets redacted) to TypeSafe.

| Argument | Type | Description |
|---|---|---|
| `files` | array | Check only claims about these files (paths relative to the project). Leave out to use the files git reports as changed. |
| `all` | boolean | Check every claim in the map - a full check. Default false. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `mcp__plugin_jevmcp_jevmcp__validate_spec_map`

*Validate the spec map (spec-to-code pairings)* · `readOnlyHint: true` · `openWorldHint: false` · free — sends nothing

> Check that the spec map still fits the spec and the code - every reference resolves, nothing is stale, and (strict, the default) every spec sentence is either mapped or marked excluded with a reason. Free: sends nothing. Run after editing the spec or the map.

| Argument | Type | Description |
|---|---|---|
| `strict` | boolean | Also report unmapped sentences, unreviewed entries, exclusions without a 'why'. Default true. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `mcp__plugin_jevmcp_jevmcp__preview_spec_check`

*Show what a check would send* · `readOnlyHint: true` · `openWorldHint: false` · free — sends nothing

> Show exactly what check_spec_drift would send to TypeSafe for some claims: the sentence, the code with comments removed and secrets redacted, any computed values, and the 3 fixed questions. Free: sends nothing.

| Argument | Type | Description |
|---|---|---|
| `files` | array | Claims about these files. Leave out (and leave out 'line') for the files git reports as changed. |
| `line` | integer | Only the claim(s) from this line of the spec. |
| `map` | string | The spec map (spec_map.json: which code implements which spec sentence) to use, relative to the project. Leave out: the project's only *spec_map.json is found automatically. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |

### `mcp__plugin_jevmcp_jevmcp__draft_spec_map`

*Draft the spec map (pair each requirement with code)* · `readOnlyHint: false` · `openWorldHint: false` · free — sends nothing

> Set up a project that has no spec map yet: suggest a code location for every sentence of the spec(s) and write them to a new map file for review. Every entry must then be reviewed - point 'code' at what enforces the sentence and set status 'reviewed', or set status 'excluded' with a 'why' - before check_spec_drift is worth running. Free: sends nothing. Never overwrites a file.

| Argument | Type | Description |
|---|---|---|
| `docs` **(required)** | array | The spec file(s) or folder(s), relative to the project. |
| `out` **(required)** | string | The new map file, relative to the project - usually next to the spec, named spec_map.json. |
| `project` | string | Absolute path of the project folder - your working directory. Needed when the client does not tell the server which project it is in (Codex). Where the client does tell it, this must be that same folder or one inside it - another project is refused. |


Every tool also accepts `project`; see section 5 for whether it is optional here.

---

## 5. What is different in Claude Code

### Install

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jev
```

The marketplace is `jev` and the plugin inside it is `jevmcp`, so the install id is `jevmcp@jev`.
Claude Code reads the Claude-specific manifests — `.claude-plugin/marketplace.json` at the
repository root, `plugins/jevmcp/.claude-plugin/plugin.json` and `plugins/jevmcp/.mcp.json`. It
does **not** read the portable `plugin.json` / `mcp.json`, which is why both sets exist.

Installed copies live at `~/.claude/plugins/cache/jev/jevmcp/<version>/`.

### How the instruction reaches the model

The skill is `jevmcp:spec-drift`. Claude Code lists its **name and frontmatter description** at
session start, and reads the body only when the skill is used. The server's `instructions` block
appears separately under "MCP Server Instructions" while the server is connected.

### Tool names

```
mcp__plugin_jevmcp_jevmcp__check_spec_drift
mcp__plugin_jevmcp_jevmcp__validate_spec_map
mcp__plugin_jevmcp_jevmcp__preview_spec_check
mcp__plugin_jevmcp_jevmcp__draft_spec_map
```

The shape is `mcp__plugin_<plugin>_<server>__<tool>`; plugin and server are both `jevmcp`.

### The API key — there is a prompt

`.claude-plugin/plugin.json` declares one `userConfig` entry, `typesafe_api_key`
(`"sensitive": true`, `"required": true`), so **Claude Code asks for the key when the plugin is
enabled** and keeps it out of every settings file (macOS Keychain, otherwise
`~/.claude/.credentials.json`). `.mcp.json` passes it to the server:

```json
"env": { "TYPESAFE_API_KEY": "${user_config.typesafe_api_key}" }
```

Change it later with `/plugin manage`. Do **not** use `claude plugin install --config ...` — the
key would land in shell history. The model never sees the value.

### `project` is optional

Claude Code starts the server **in the project** and sets `CLAUDE_PROJECT_DIR`, which the server
uses as its `--root` default. So calls may leave `project` out. One boundary rule still applies: if
`project` points outside the folder the server was started for, the call is refused —

```
project /x/y is outside the project this server was started for (/a/b) - refused
```

A home folder or a filesystem root is refused as a project anywhere.

### Approval

`check_spec_drift` is annotated `readOnlyHint: false`, `openWorldHint: true` because code leaves
the machine, so Claude Code applies its normal MCP tool permission. **That prompt is about the
tool, not about the data** — the consent for *sending code* is the skill's own rule: ask once per
project before the first real check, unless `CLAUDE.md` / `AGENTS.md` already records it.

### Network

Claude Code's own shell **has** network access, so the command-line fallback genuinely works inside
a session. The MCP tools are still the better route: the server keeps parsed code in memory (a
16,000-file repository re-indexes in ~2 s instead of ~20 s) and holds the key.

### Update, and the one quirk

`claude plugin update jevmcp@jev`. Afterwards Claude Code says **"Restart to apply changes"** — the
MCP server process is only replaced on restart, so tool names and skill text do not change until
then.

---

## 6. Verified behaviour

Checked on 2026-09-22 against Claude Code 2.1.278.

- **Discovery works with no mention of the plugin.** A headless session given an ordinary request
  loaded the skill on its own. The trigger is the layer-2 description alone.
- **A fresh install from GitHub end to end**: skill loaded unprompted, `draft_spec_map` wrote the
  map, the agent reviewed every entry and corrected 2-3 of the drafter's guesses,
  `validate_spec_map` passed, the agent **stopped and asked for consent**, and with consent the
  check found all 4 planted drifts with no false alarms. Cost: $0.93 to set up, $0.88 to check.
- **The key never appeared in any transcript** (0 occurrences across four session logs).
- **On a real project** (131 mapped claims, ~12 s, $0.006): 3 DRIFT, 105 review, 21 `??`, 2 ok.
  The repository was not modified — working tree and map checksum identical before and after.
- **Not established:** which permission flags a fully unattended Claude Code run needs before
  `mcp__plugin_jevmcp_jevmcp__check_spec_drift` will execute. For CI, do not drive an agent — run
  `spec_drift.py` directly (exit codes 0/1/2/3).

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
