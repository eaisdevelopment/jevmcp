---
name: spec-drift
description: Check whether a project's code still matches its design spec or requirements document. A fast model (TypeSafe's Jev) screens every requirement in seconds; you investigate only what it flags. A project is set up once with a spec map (spec_map.json), which pairs each requirement sentence with the code that implements it; the draft_map tool writes it, the user never writes it by hand. Use when the user asks whether code matches the spec, design or requirements; after changing code in a project that has a *spec_map.json (before you finish the task); when a spec is edited; before a release; or to set up spec-drift checking for a project. Works with Java/Spring, JavaScript/TypeScript (Node, NestJS, Express, Hono, Fastify, Next.js) and Python (FastAPI, Flask, Django), and with any other language through line ranges.
---

# Spec drift check

**Division of labour.** The fast model screens every spec requirement against the code that
implements it and labels each one. **You** spend your effort only on what it flags, on what it
cannot judge, and on its known blind spots. Do not re-read the whole spec and codebase yourself
to do its job, and never call the TypeSafe API by hand: docdrift's questions and thresholds are
measured, pinned and tested.

A project is set up once: a **spec map** (`spec_map.json`, usually next to the spec) pairs each
requirement sentence with the code that implements it, or marks it excluded with a reason.
After that, every check is seconds and fractions of a cent.

## The tools

**Use the MCP tools when they are available** (server `jevmcp`): `check_drift`,
`validate_map`, `show_payload`, `draft_map`. They keep the parsed code in memory and hold the
API key themselves. Pass `project` with the absolute path of the project (your working
directory) in every call: some clients do not tell the server which project it is in, and it
is harmless where they do.

Otherwise use the command line, from the project's root. It needs network access to reach
TypeSafe (and, the first time, to install its Python dependencies); in a sandbox without
network, use the MCP tools instead.

```bash
DD="uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/docdrift.py"
$DD --help                      # every option, explained
```

If `${CLAUDE_PLUGIN_ROOT}` above is not already a real path, the plugin's `scripts/` folder is
two folders above this SKILL.md: `../../scripts/docdrift.py`, relative to this file.

| Job | MCP tool | Command line |
|---|---|---|
| Check claims about changed files | `check_drift` (default: git's changed files; `files: [...]` to name them) | `$DD --map <map> --changed --jobs 8 --out <tmp>/drift.json` |
| Full check | `check_drift` with `all: true` | `$DD --map <map> --jobs 8 --out <tmp>/drift.json` |
| Validate the map (free) | `validate_map` | `$DD --map <map> --dry-run --strict` |
| See exactly what is sent (free) | `show_payload` | `$DD --map <map> --dry-run --show-payload` |
| Draft a map for a new project (free) | `draft_map` | `$DD --docs <spec> --draft-map <spec folder>/spec_map.json` |

Write results to a temporary folder, not into the repository. Exit codes: **0** no drift ·
**1** at least one DRIFT · **2** setup or map problem, fix it (the output names each broken
entry, usually with "Did you mean") · **3** TypeSafe unavailable: say so, carry on without it,
never block the user's task on it.

## Before any code is sent

- **Consent, once per project.** A check sends each spec sentence and its paired code (comments
  removed, secret-looking values redacted, paths relative) to `api.typesafe.ai`. Before the first
  real check in a project, tell the user that and get a yes, unless they have already said so
  in this conversation or the project's CLAUDE.md or AGENTS.md records it. The dry-run and
  `show_payload` send nothing and need no consent.
- **The key.** The MCP server gets it from the plugin's settings (Claude Code asks for it when
  the plugin is enabled) or from `TYPESAFE_API_KEY` in the environment that starts the agent
  (Codex forwards that variable to the server), or from `typesafe.env` in the plugin's data
  folder (other Agent Plugins clients; the error message names the path); never from the
  project's own `.env`. The command line uses `--key-file` if given, otherwise
  `TYPESAFE_API_KEY`, otherwise a `TYPESAFE_API_KEY=` line in the `.env` of the folder it runs
  from. If the key is missing, tell the user where to set it and stop. Never ask for the key in chat, never print it, never pass it on a command line you
  show.

## A. Setting up a project that has no map

1. **Find the spec.** Look for design, specification, requirements or architecture documents
   (Markdown or reStructuredText). If there are several candidates, ask which one is the source
   of truth.
2. **See what the tool can read:** `$DD --docs <spec> --dry-run`. It reports the languages,
   routes and config keys it found, and lists the sentences it cannot pair on its own. If it
   says a parser is missing or a language can only be paired by line range, note it.
3. **Draft the map** with `draft_map` or `--draft-map`. It suggests code for every sentence;
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
5. **Validate:** `validate_map` or `--dry-run --strict` must report no problems.
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
a reviewed map, change docdrift's questions or thresholds, commit without asking, or block the
user's task on exit 3.
