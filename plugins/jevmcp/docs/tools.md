# What jevmcp offers: tools, skill, spec map, command line

This page is the reference for everything the jevmcp plugin gives you — four MCP tools, one
skill, the `spec_map.json` file they all work from, the result labels, and the command-line
checker — with exact arguments, exact output and the errors each can return; it is written for
an agent that has jevmcp installed and only this repository to read.

To install it, see [install.md](install.md). For what each client does differently, see
[clients.md](clients.md). For worked procedures (setting a project up, the routine check, CI),
see [how-to.md](how-to.md). For what leaves the machine, see
[PRIVACY.md](../PRIVACY.md).

---

## At a glance

| Piece | Name | Sends code out? | Costs money? |
|---|---|---|---|
| MCP tool | `check_spec_drift` | **Yes** — the only thing that does | Yes, fractions of a cent |
| MCP tool | `validate_spec_map` | No | No |
| MCP tool | `preview_spec_check` | No | No |
| MCP tool | `draft_spec_map` | No (writes a file in the project) | No |
| Skill | `spec-drift` | — | — |
| File | `spec_map.json` in the project | — | — |
| Command line | `scripts/spec_drift.py` | Yes, on a real run | Yes, on a real run |

One MCP server holds all four tools. It is called `jevmcp` and the client starts it as
`uv run --quiet --script <plugin>/scripts/jevmcp_server.py`. Future tool families (CI failure
triage, code audit) are added to this same server, so there is never a second install or a
second API key.

**Tool names as your client shows them**

| Client | Name you call |
|---|---|
| Claude Code | `mcp__plugin_jevmcp_jevmcp__check_spec_drift` (and the same prefix for the other three) |
| Codex and other Agent Plugins clients | `check_spec_drift` on the server `jevmcp` |

---

## The four MCP tools

### Arguments every tool takes

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `project` | string | the folder the client started the server in | Absolute path of the project folder — your working directory. **Pass it in every call.** Some clients (Codex) start the server in the plugin's own folder and never say which project you are in; where the client does say, this argument is harmless. |

`project` must be an absolute path to an existing folder, inside the project the server was
started for, and not your home or a filesystem root.

### `check_spec_drift`

Checks the code against the spec and returns the results, most important first: DRIFT, then
`review` sorted by P(drifted), then `??`, then a count of `ok`.

**This is the only tool that sends anything.** It is declared a write action
(`readOnlyHint: false`, `openWorldHint: true`) precisely because code leaves the machine, which
is why Codex asks for approval every time you call it.

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `files` | array of strings | the files git reports as changed | Check only claims whose paired code is in these files. Paths relative to the project. |
| `all` | boolean | `false` | Check every claim in the map — a full check. |
| `map` | string | the project's only `*spec_map.json`, found automatically | The spec map to use, relative to the project. |
| `project` | string | see above | Absolute path of the project. |

No argument is required. `files` and `all` are alternatives: with `all: true` the map is checked
end to end and `files` is ignored.

**What it returns — text.** The first line is a summary, then the report:

```
spec-drift check (spec_map.json): 6 of 131 claims, about 2 file(s) git reports as changed | index 0.31s (warm: 2 of 412 files parsed again) | checked 6 in 3.2s | $0.0013

DRIFT 1 · review 2 · ?? 0 · ok 3   full results (with the exact code sent): /tmp/jevmcp-ab12cd/last-check-myproject-9f3a1c22.json

DRIFT - investigate each one (which side is wrong: code or spec?):
  docs/spec.md:24  P(drifted) 0.97  severity 3/3
    claim: An order may contain at most 50 items.
    code:  src/settings.py:12 MAX_ITEMS  (+1 more: src/orders.py:41 place_order)
    why:   drifted, confident
```

`review` items follow, sorted by P(drifted); then `??` items; then a count of `ok`, listing any
whose `value_mismatch` is 0.5 or more.

**What it returns — structured fields.** The server also sends `structuredContent`, and repeats
it as a second text block of JSON for clients that do not read structured output.

| Field | Type | Meaning |
|---|---|---|
| `summary` | string | The first line of the report, plus a reminder of what each label means once a check has actually run (when there was nothing to check, there are no labels to remind you of). |
| `project`, `map` | string | The project folder used, and the map, relative to it. |
| `claims_in_map` | integer | Entries in the map that resolved. |
| `claims_selected` | integer | Of those, how many this call chose to check. |
| `checked` | integer | How many actually got an answer. |
| `counts` | object | `DRIFT`, `review`, `??`, `ok` — a count each. |
| `cost_usd` | number | What this call cost, to 6 decimal places. |
| `complete` | boolean | True only when nothing was skipped: no map problems, nothing stopped, nothing failed. |
| `results_file` | string or null | Path to the full results, **including the exact code that was sent**. |
| `map_problems` | array of strings | Entries that could not be used, so were **not** checked. |
| `not_checked` | array of strings | Claims stopped or failed part-way through. |
| `flagged` | array of objects | Everything that is not `ok`, in the order to work through it: DRIFT by severity, then review by P(drifted), then `??`. |

Each `flagged` item has `label` (`DRIFT` / `review` / `??`), `doc`, `line`, `claim`,
`p_drifted`, `severity` (0–3), `value_mismatch` (may be null), `code_refs` and `why`.

The results file lives in a private folder of the server process (mode 0700) with the file at
mode 0600, and the folder is deleted when the server stops. Read it when you need to see the
exact code a verdict was based on; do not copy it into the repository.

**Cost and duration.** Charged on input tokens only, at $0.042 per million; output is free.
Measured runs:

| Run | Claims | Time | Cost |
|---|---|---|---|
| Real Java project, full check | 131 requirements | 11.5 s | $0.006 |
| The same project after editing 2 files | a handful | 3.2 s | $0.0013 |
| The FastAPI demo in this repository | 8 claims | seconds | $0.0002 |

`validate_spec_map` tells you a full check's cost before you spend anything.

**Errors it can return** (all arrive as a tool result with `isError`, so read the text and act):

| Error text (start of) | What to do |
|---|---|
| `No TypeSafe API key is set for this server, so nothing was sent.` | Nothing was sent. Pass the stored-key command on to the user to run **in their own terminal**. Never ask for the key in chat, never put it in a command you run. See [install.md](install.md). |
| `TypeSafe rejected the API key (HTTP 401/403)` | The key is wrong or revoked. Tell the user to check it at <https://console.typesafe.ai> and store it again. |
| `TypeSafe's credits are used up (HTTP 402)` | Not a fault in the code. Report it, carry on without the check, and never report "no drift". |
| `rate limit: at most 20 checks a minute` | Wait the stated seconds, or check more files in one call instead of looping. |
| `rate limit: at most 120 tool calls a minute` | You are calling too fast. Wait the stated seconds. |
| `this project (...) has no spec map yet (no *spec_map.json)` | Run `draft_spec_map`, then review every entry. Do not invent a map by hand. |
| `this project has several spec maps - say which one with 'map'` | Pass `map` with one of the paths it lists. |
| `map file not found: X (relative to ...)` | The path is relative to the project folder, not to your shell. Fix it. |
| `X is outside the project - refused` | Point at a file inside the project. |
| `this client did not tell the server which project it is working in` | Pass `project` with the absolute path of your working directory. |
| `project must be an absolute path` / `project folder not found` / `is a home or root folder, not a project` | Pass the project's own folder, absolute. |
| `check_spec_drift does not take X; it takes: ...` / `needs X` / `X must be a list of strings` | Fix the arguments and call again. |
| `INCOMPLETE - not everything was checked:` (inside a successful result) | Part of the run did not happen. Say so; never present the run as a clean result. |
| `<map> is not valid JSON: ... A trailing comma or a missing quote is the usual cause.` | Fix the JSON. |
| `the server is shutting down` | The session is ending. Do not retry. |

### `validate_spec_map`

Checks that the map still fits the spec and the code: every reference resolves, nothing is
stale, and — with `strict`, the default — every spec sentence is either mapped or marked
excluded with a reason. Free, sends nothing, read-only.

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `strict` | boolean | `true` | Also report unmapped sentences, unreviewed entries, exclusions without a `why`, and entries whose spec text may have changed. |
| `map` | string | the project's only `*spec_map.json` | The map to validate, relative to the project. |
| `project` | string | see above | Absolute path of the project. |

**Text:**

```
spec_map.json: 42 entries ready to check; 8 marked excluded (not requirements, never sent) | index 0.31s (warm: 0 of 412 files parsed again)
a full check would cost about $0.0031
OK - the map is complete and every entry resolves.
```

If anything is wrong, the last line is replaced by a `PROBLEMS (n) - fix these; the map is not
ready:` block listing each one. With `strict: false` the same findings appear as `note:` lines
instead and do not make the map unready.

**Structured fields:** `project`, `map`, `ready` (boolean — no problems), `entries_to_check`,
`excluded`, `full_check_cost_usd`, `problems` (array), `notes` (array; empty when `strict` is
true, because the notes have become problems).

**Cost and duration:** free. The time is the indexing time, which the tool prints — under a
second on a small project, about 2 s to re-read a 16,000-file repository once the server is warm
(about 20 s the first time).

**Errors:** the map-resolution and `project` errors from the table above. Note that a problem in
one entry is reported, not raised: the tool still returns, with the entry listed and not counted
as ready.

### `preview_spec_check`

Shows exactly what `check_spec_drift` would send to TypeSafe for some claims: the sentence, the
code with comments removed and secrets redacted, any values the tool worked out, and the three
fixed questions. Free, sends nothing, read-only. Use it to show a user what consent covers.

| Argument | Type | Default | Meaning |
|---|---|---|---|
| `files` | array of strings | the files git reports as changed | Claims about these files. |
| `line` | integer | — | Only the claim(s) from this line of the spec. |
| `map` | string | the project's only `*spec_map.json` | The map, relative to the project. |
| `project` | string | see above | Absolute path of the project. |

Give `line` alone, `files` alone, both (line first, then narrowed by file), or neither (the
changed files).

**Text:** the model name and the three questions as JSON, then one block per claim:

```
3 claim(s). Every request is model jev-1.13.0 with these 3 fixed questions:
{ "verdict": {...}, "severity": {...}, "value_mismatch": {...} }

--- docs/spec.md:24  state sent:
{ "claim": "An order may contain at most 50 items.", "code": "# src/settings.py:12\nMAX_ITEMS = 40", "computed_values": "..." }
```

No structured output — this tool returns text only.

If nothing matches, it returns `no claim matches (a line number is the spec line; files are
paths relative to the project).` — check the line number is the one in the spec, not in the map.

### `draft_spec_map`

Sets up a project that has no map: suggests a code location for every sentence of the spec and
writes them to a new map file for review. Free, sends nothing. **Never overwrites a file.**

| Argument | Type | Required | Meaning |
|---|---|---|---|
| `docs` | array of strings | **yes** | The spec file(s) or folder(s), relative to the project. A folder is searched for `.md` and `.rst`. |
| `out` | string | **yes** | The new map file, relative to the project — usually next to the spec, named `spec_map.json`. |
| `project` | string | no | Absolute path of the project. |

**Text:** the index line, then the drafter's own report — how many sentences were written, how
many named a route, config key or code in backticks (usually right), how many are word-overlap
guesses (often wrong, with their line numbers), how many got no suggestion — and then:

```
Nothing is checked until the entries are reviewed. Then validate_spec_map (map: spec_map.json)
must report OK before check_spec_drift.
```

No structured output — text only.

**Errors:** `X already exists and may hold a reviewed map - nothing was written. Draft into a
new file and compare.` · `spec not found in the project: X` · `no .md or .rst files in X` ·
`X is outside the project - refused`.

Reviewing the entries it writes is your job and the user's, not the drafter's. Its suggestions
are guesses.

---

## The skill

| | |
|---|---|
| Name | `spec-drift` (in Claude Code: `jevmcp:spec-drift`) |
| File | [`plugins/jevmcp/skills/spec-drift/SKILL.md`](../skills/spec-drift/SKILL.md) |
| Cost in context | about 230 tokens always loaded; the body (~3k tokens) only when it fires |

**When it fires.** On its own, from the frontmatter description — no one has to mention the
plugin. It is written to trigger when the user asks whether code matches the spec, design or
requirements; after you change code in a project that has a `*spec_map.json`, before you say the
task is done; when a spec is edited; before a release; or when asked to set spec-drift checking
up. In testing, three neutral Codex prompts and a headless Claude Code run all loaded it
unprompted, while a control prompt ("What does this project do?") did not.

**What it makes you do**, in short:

- Let the fast model screen everything; spend your own effort only on what it flags. Do not
  re-read the whole spec and codebase to do its job, and never call the TypeSafe API by hand.
- Get the user's consent once per project before the first real check, because code leaves the
  machine. The free tools need no consent.
- Never print, ask for, or pass the API key.
- Set a new project up in the order: find the spec → `--dry-run` to see what the tool can read →
  `draft_spec_map` → **review every entry** → `validate_spec_map` → with consent, the first full
  check.
- Treat `??` as "not a pass", never as a pass.
- Judge four things yourself whatever the label: settings hard-coded in code, library and
  platform behaviour, arithmetic on variables, and anything spanning several files.
- Report back as a short table — claim (file:line) · label · P(drifted) · what you found · which
  side to fix — then a recommendation.
- Never block the user's task because TypeSafe was unavailable, and never report "no drift" from
  a run that could not reach it.

Read the skill itself before a real job; this is a summary of it, not a replacement.

---

## The spec map

`spec_map.json` lives in the project, next to the spec, and is committed with the code. It pairs
each sentence of the spec with the code that implements it.

**Why it exists.** Without it, checking a spec would mean sending the whole repository to a model
for every sentence. With it, the fast model gets one requirement and the few lines that enforce
it — which is what makes a check take seconds and cost fractions of a cent.

**Who writes it.** `draft_spec_map` (or `--draft-map`) writes it. The user never writes it by
hand. Every entry must then be reviewed by you and the user before a check is worth running.

### File shape

```json
{
  "_readme": ["A map says which code each spec requirement is about. ..."],
  "entries": [
    {
      "spec": "docs/spec.md",
      "line": 24,
      "text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
      "status": "reviewed",
      "why": "the constant is the limit; place_order enforces it",
      "code": ["app/settings.py:SHOP_MAX_ITEMS", "app/services.py:place_order"],
      "spec_text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
      "alternatives": ["app/api.py:create_order"]
    }
  ]
}
```

A bare JSON list of entries also loads, but `draft_spec_map` writes the object form, and
`_readme` explains every field inside the file itself.

### Fields

| Field | Meaning |
|---|---|
| `spec` | The spec file the sentence came from, relative to the project. |
| `line` | Its line in that file. If the sentence moves, the tool finds it again and reports the new line. |
| `text` | The requirement that will be checked, and the only thing sent from the spec. Edit it only to make it clearer. |
| `code` | Where the code for it is: one reference, or a list of several (see below). |
| `status` | `reviewed` or `excluded` once a human has decided. Before that the drafter writes `named in the sentence`, `suggested`, or `NO MATCH - fill in the code or delete this entry`. |
| `why` | Your note: why this code, or why the sentence is excluded. Never sent. |
| `spec_text` | A snapshot of the spec text as reviewed, used only to notice when the spec changes afterwards. Optional but strongly worth having. Markdown and line breaks are fine. |
| `alternatives` | Other candidates the drafter found, for information. Never sent. |

### The two statuses

- **`reviewed`** — someone has checked that `code` points at what actually enforces the
  sentence. Point at the implementation, not only the interface; at the constant, so the value
  is visible; at the wiring, when the claim is about which piece is used.
- **`excluded`** — the sentence is not a requirement (rationale, history, plans, comparisons,
  glossary, examples, lead-ins). It needs no `code`, is never sent, and records that someone
  decided, so the strict check does not report the sentence as unchecked. Say why in `why`. A
  backlog or rationale sentence that constrains today's code *is* a requirement.

### Every form a `code` reference can take

| Form | Example | What it resolves to |
|---|---|---|
| Route | `route:GET /api/orders/{id}` | The endpoint's handler, wherever it lives. Several matches are joined. |
| Config key | `config:app.orders.max-items` | The setting's definitions, defaults, and every place that names the key (`@Value`, `process.env.X`, `os.environ[...]`). Uses through a settings object are **not** found, so point at the code that enforces the setting as well. |
| Symbol in a file | `src/Orders.java:OrderService.place` | A method, class, function or constant. |
| Line range | `src/app.ts:120-160` | Those lines — works for any language, including ones with no parser. |
| Whole file | `src/config.py` | The whole file. Small files only. |
| A list | `["app/settings.py:MAX", "app/services.py:place"]` | All of the above, together. |

File paths are looked up from the folder the checker runs in, then `--src`, then the map's own
folder. A `.env` file, a key or certificate file (`.pem`, `.key`, `.p12`, `.jks`, `.pfx`,
`id_rsa`, `id_ed25519`, `id_ecdsa`), or anything outside those folders is **refused** — a map
can never be used to send a secret. `.env.example`-style templates are read as configuration.
Whatever is sent per claim is capped at 2,600 characters.

Named symbols are found by name in Python, Java, JavaScript and TypeScript; every other language
is paired by line range.

### What `--strict` and `validate_spec_map` enforce

Both run the same checks. These make the map "not ready":

| Reported | Because |
|---|---|
| `N sentences in <spec> are not in the map, so NOT checked: lines ...` | A spec sentence is neither mapped nor excluded. |
| `N map entries are not marked "status": "reviewed"` | A real run would check the drafter's guesses as they are. |
| `N excluded entries do not say why (lines ...)` | An exclusion without a reason is not a decision. |
| `the spec changed since this entry was reviewed - NOT checked` | `spec_text` no longer matches the spec. Re-read the entry, update `text` if the requirement changed, and paste the current paragraph into `spec_text`. |
| `N excluded sentences have changed in the spec (were at lines ...)` | Rewording can turn rationale into a rule. Decide again. |
| `N entries have no spec_text and their text is not word-for-word in the spec` | A spec change cannot be ruled out. Paste the paragraph into `spec_text`. |
| `map entry N has no "code" - NOT checked` | Fill it in, or exclude the sentence with a `why`. |
| `map entry N - NOT checked: k of m code reference(s) could not be resolved` | A rename or a move. The output names the closest match it found. |
| `map entry N: spec file 'X' not found - NOT checked` | The `spec` path is relative to where the checker runs. |

Never delete an entry or blank a `spec_text` to make the strict check pass, and never change an
exclusion without saying so in your report.

---

## The labels and what to do with each

Every claim gets exactly one label. The thresholds are fixed in the source and are not
configurable on purpose: they were measured over repeated identical calls.

| Label | When | Your job |
|---|---|---|
| **DRIFT** | The model says the code and the sentence disagree, with confidence **≥ 0.905** | Investigate **every one**. Read the claim and the code that was sent, then the real code around it. Decide which side is wrong — `git log -p` and `git blame` usually show whether the change was deliberate (the spec is stale) or accidental (a bug). |
| **review** | It leans one way but is not sure enough: a "drifted" below 0.905, or an "accurate" below 0.987, or a confident "accurate" contradicted by a stated value (`value_mismatch ≥ 0.70`) | Sorted by P(drifted). Investigate from **0.3** up; skim below that. |
| **??** | The model answered `not_enough_information` or `unrelated` | **Not a pass.** The code shown cannot settle the claim. Fix that map entry — add the implementation, the constant, the caller — then check again. |
| **ok** | "Accurate" at confidence **≥ 0.987**, with no value conflict | Spot-check a couple, plus any whose `value_mismatch` is 0.5 or more. |

A low-confidence "accurate" is not a clean bill of health, which is why it lands in `review`
rather than `ok`. And `??` is not a threshold at all — it is the model declining to judge.

**Known blind spots — judge these yourself whatever the label:** settings hard-coded in code
(a dict or `Map.of(...)` literal reads as configuration); library and framework behaviour;
arithmetic on variables (only literal expressions are worked out for the model); and anything
spanning several files, such as "only X calls Y". A low P(drifted) on one of these is not a pass.

---

## The command line

`scripts/spec_drift.py` runs the same checks, the same questions and the same thresholds as the
MCP tools — both call the same code, so they judge identically.

```bash
# run it from the root of the project you are checking
uv run --script <plugin>/scripts/spec_drift.py --help
```

### Flags

| Flag | Meaning |
|---|---|
| `--docs PATH [PATH ...]` | The spec: Markdown/`.rst` files or folders. Pairs only sentences that name code in backticks; everything else is listed as not checked. |
| `--map FILE` | A reviewed map. Use this to check every requirement, not only the ones that name code. `--docs` and `--map` are alternatives, never both. |
| `--src DIR` | Folder to read the code from. Default: the current folder. |
| `--ignore NAME [NAME ...]` | More folder names to skip, on top of the defaults. |
| `--no-default-ignore` | Skip only what `--ignore` names (defaults include `.venv`, `node_modules`, `.git`, `build`, `dist`, `target`, `coverage`, `.idea`, `.claude`, `.agents`, `.cursor`). |
| `--dry-run` | Show every claim, its paired code, how much would be sent, and the estimated cost. No API calls. Exit 2 if anything is wrong with the map, so it doubles as a map check in CI. |
| `--show-payload` | With `--dry-run`, also print exactly what would be sent for each claim. |
| `--strict` | Also fail (exit 2) on unchecked spec sentences, unreviewed entries, entries that may be stale, exclusions with no `why`, and exclusions whose sentence has changed. |
| `--draft-map FILE` | Write a first-draft map (with its own `_readme`) and stop. Needs `--docs`. No API calls. Refuses to overwrite. |
| `--out FILE` | Where results go. Default `drift.json`; an existing file is overwritten. With `--dry-run` it writes the plan instead — a CI artefact that costs nothing. |
| `--changed [FILE ...]` | Check only claims whose paired code is in these files. With no file given: what git reports as changed or new (`git diff HEAD`, plus untracked). |
| `--jobs N` | Claims asked about at once. Default 4 on the command line (the MCP server uses 8). |
| `--limit N` | Check only the first N claims, in spec order — a cheap first try. |
| `--key-file FILE` | Read `TYPESAFE_API_KEY=...` from this file and nothing else. |

Paths are relative to the folder you run from, so run it from the project root. Write results to
a temporary folder, not into the repository.

### Exit codes

| Code | Meaning | What to do |
|---|---|---|
| **0** | Every claim was checked; no DRIFT | Report the result. |
| **1** | Every claim was checked; at least one DRIFT | Investigate each DRIFT. |
| **2** | Fix the setup: usage error, missing key or parsers, a map entry that cannot be resolved or is stale — and with `--strict` also unmapped sentences, unreviewed entries, exclusions with no `why` | Fix it. In CI this should fail the job. |
| **3** | TypeSafe could not be used (outage, errors, credits used up) | Not the code's fault. Results produced so far are still written. Say the check did not complete — **never report "no drift" from an exit-3 run** — and do not block on it. |

`review` and `??` never change the exit code. With `--limit`, the codes cover only the claims
checked.

### When to use the command line instead of the tools

| Situation | Use |
|---|---|
| Inside an agent session, any client | **The MCP tools.** They keep the parsed code in memory and hold the key themselves. |
| Inside a Codex session | **The MCP tools only.** Codex's sandbox has no network, so a fall-back to the command line silently reaches nothing and reports no drift. The MCP server runs outside the sandbox, which is why the tools work. |
| CI, or any unattended run | **The command line**, where the network works. It is simpler and safer than forcing MCP approvals through. |
| A one-off from a human's terminal | Either. |

The command line reads a `TYPESAFE_API_KEY=` line from the `.env` of the folder it runs in; the
MCP server never does, so a cloned project cannot supply a key.

---

## Rate limits

The server enforces two limits, both per rolling minute, both set when the client starts it:

| Limit | Default | Flag | Why |
|---|---|---|---|
| `check_spec_drift` calls | 20 a minute | `--max-checks-per-minute N` (0 = no limit) | Each check spends TypeSafe credits; this stops a runaway loop. |
| Tool calls of any kind | 120 a minute | `--max-calls-per-minute N` (0 = no limit) | Each call may re-read a large project. |

When you hit one, the error says how many seconds to wait. Do not retry in a tight loop — check
more files in one call instead.

---

## If you are an agent, do this first

1. **Pass `project`** — the absolute path of your working directory — in every tool call.
2. **Read [`SKILL.md`](../skills/spec-drift/SKILL.md)** before a real job; this
   page is the reference, that is the procedure.
3. **Look for `*spec_map.json` in the project.** No map? The project is not set up: go to
   `draft_spec_map` and the review step, not to `check_spec_drift`.
4. **Run `validate_spec_map` first.** It is free, it tells you whether a check is worth running,
   and it tells you what a full check would cost.
5. **Get consent before the first `check_spec_drift` in a project**, because code leaves the
   machine. Use `preview_spec_check` to show exactly what would go. Both free tools need no
   consent.
6. **Never ask for, print or pass the API key**, and never run the `--set-key` command yourself —
   pass it to the user for their own terminal.
7. **Default to the changed files.** Use `all: true` only for a release or a first full check.
8. **Treat `??` as unfinished work, not a pass**, and never report "no drift" from a run that
   could not reach TypeSafe.
