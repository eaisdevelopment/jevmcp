# Recipes

Task-first procedures for an agent working in a project with jevmcp installed: follow the
numbered steps literally. For what each tool takes and returns see [tools.md](tools.md); for
installing the plugin see [install.md](install.md); for client-specific behaviour (approvals,
sandboxes, unattended runs) see [clients.md](clients.md).

## What costs money, and what does not

Only one action sends anything out of the machine. Everything else is free and needs no consent.

| Action | MCP tool | Command line | Sends code? |
|---|---|---|---|
| Draft a spec map | `draft_spec_map` | `--docs ... --draft-map FILE` | no — free |
| Validate the map | `validate_spec_map` | `--map FILE --dry-run --strict` | no — free |
| See exactly what would be sent | `preview_spec_check` | `--map FILE --dry-run --show-payload` | no — free |
| Check the code against the spec | `check_spec_drift` | `--map FILE` (no `--dry-run`) | **yes** — fractions of a cent |

What a check sends, and what is never sent, is in
[PRIVACY.md](../PRIVACY.md). Get the user's consent once per project before the
first check.

## Where the command-line script lives

The MCP tools are the normal route. Use the command line only where the tools are absent, or in
CI. The script is `scripts/spec_drift.py` inside the plugin:

| Situation | Path |
|---|---|
| Claude Code session | `${CLAUDE_PLUGIN_ROOT}/scripts/spec_drift.py` |
| The variable is not expanded | `../../scripts/spec_drift.py`, relative to `skills/spec-drift/SKILL.md` |
| Codex install | `$(ls -d ~/.codex/plugins/cache/jev/jevmcp/*/scripts/spec_drift.py \| sort -V \| tail -1)` |
| A clone of this repository | `plugins/jevmcp/scripts/spec_drift.py` |

Every command below assumes this shell variable, and that you run from the root of the project
being checked (not from the plugin, and not from a clone of this repository):

```bash
SD="uv run --quiet --script ${CLAUDE_PLUGIN_ROOT}/scripts/spec_drift.py"
$SD --help          # free: every option, explained
```

Write results outside the repository: `--out` defaults to `drift.json` in the folder you run in,
which would leave a file in the user's project.

---

## 1. Set a project up from nothing

The result is one reviewed file, `spec_map.json`, committed with the code. Steps 1–4 and 6 are
free; only step 7 sends anything.

1. **Check there is no map already.** If `find . -name '*spec_map.json' -not -path '*/node_modules/*'`
   finds one, this recipe does not apply — go to recipe 2. `check_spec_drift` on a project with no
   map fails with `this project (<path>) has no spec map yet (no *spec_map.json)`.

2. **Find the spec.** Look for a design, specification, requirements or architecture document in
   Markdown or reStructuredText — `docs/`, `README.md`, `ARCHITECTURE.md`, `SPEC.md`, `docs/adr/`.
   If there are several candidates, ask the user which one is the source of truth. Do not write a
   spec yourself, and do not point the drafter at a whole `docs/` tree of mixed material unless the
   user says all of it is normative.

3. **See what the checker can read (free).** From the project root:

   ```bash
   $SD --docs docs/spec.md --dry-run --out /tmp/jevmcp-plan.json
   ```

   Read the first line — `read the code in <dir> (0.3s): 412 functions, classes and constants
   (Python 412), 18 routes, 7 config keys`. Then read the notes:

   | Line | Meaning |
   |---|---|
   | `note: N .go files can only be paired by line range (file:120-160)` | that language has no parser; recipe 7 |
   | `PROBLEM: N .java files were NOT read - the parser is missing` | run the `pip install` line it prints, then repeat |
   | `PROBLEM: no code found in <dir>` | you are in the wrong folder, or nothing in this project parses (recipe 7) |
   | `not paired, so NOT checked` + a list of lines | normal at this stage: that is what the map is for |

4. **Draft the map (free).** It suggests a code location for every sentence and writes a new file;
   it never overwrites an existing one.

   ```json
   {"name": "draft_spec_map",
    "arguments": {"docs": ["docs/spec.md"], "out": "docs/spec_map.json",
                  "project": "/absolute/path/to/project"}}
   ```

   Command line: `$SD --docs docs/spec.md --draft-map docs/spec_map.json`.

   The output tells you how many entries name code in backticks (usually right), how many are
   word-overlap guesses (often wrong) and which lines they are on. The file is
   `{"_readme": [...], "entries": [...]}`; `_readme` explains every field and stays in the file.

5. **Review every entry.** This is the step that needs judgement and it is your job. Work section
   by section for a long spec, and tell the user what you changed.

   An entry after review:

   ```json
   {"spec": "docs/spec.md", "line": 6,
    "text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
    "status": "reviewed",
    "why": "the constant holds the value, place_order enforces it",
    "code": ["app/settings.py:SHOP_MAX_ITEMS", "app/services.py:place_order"],
    "spec_text": "An order may contain at most 50 items (SHOP_MAX_ITEMS)."}
   ```

   What goes in `code`:

   | Form | Use it for |
   |---|---|
   | `route:GET /api/orders/{id}` | an endpoint — its handler, wherever it lives |
   | `config:app.orders.max-items` | a setting: its definitions, defaults and the places that name the key |
   | `src/Orders.java:OrderService.place` | a method, class, function or constant in a file |
   | `src/app.ts:120-160` | a line range, any language (line numbers as written in the file) |
   | `src/config.py` | a whole file — small files only |
   | `["...", "..."]` | several of the above, when one piece cannot settle the sentence |

   What makes a **good** reference:

   - It points at what **enforces** the sentence, not at what merely mentions it. An interface, a
     DTO or a test name is not enforcement.
   - A sentence that states a value ("at most 50", "one hour", "EUR") must include the place the
     value is written, so the number is visible in what is sent — usually the constant or the
     config key, plus the code that applies it.
   - `config:` finds the key's definitions, defaults and the places that name the key
     (`@Value`, `process.env.X`, `os.environ[...]`). It does **not** follow uses through a settings
     object, so add the enforcing function as a second reference.
   - A sentence about which component is used ("orders go through the outbox") needs the wiring —
     the module that registers or injects it — not just the component.
   - Keep it small. Everything paired with one sentence shares a budget of 2,600 characters and is
     cut off beyond it; a 400-line range wastes the budget and produces `??`.
   - Nothing may point at `.env`, `.env.*`, or a key/certificate file (refused, never sent), or at
     anything outside the project folder (refused).

   What to **exclude** — set `"status": "excluded"` and write a `"why"`:

   - thesis and rationale, history and changelog prose, comparisons with other systems, glossary
     entries, examples and lead-ins ("This document describes...").
   - the backlog and future plans — **unless** the sentence constrains today's code ("until v2,
     the queue is in memory" is a requirement).

   Two more cases the drafter cannot handle: tables, byte layouts and configuration examples
   **inside code blocks** are skipped, so add those entries by hand with the requirement written
   out in `text` and the block's lines pasted into `spec_text`.

   Set `"status": "reviewed"` on each entry you have checked. (An entry with no `status` field at
   all is treated as reviewed; the drafter always writes one — `named in the sentence`,
   `suggested`, or `NO MATCH - fill in the code or delete this entry` — so anything you have not
   touched is caught by step 6.)

6. **Validate (free).** Repeat until it says OK.

   ```json
   {"name": "validate_spec_map", "arguments": {"strict": true, "project": "/absolute/path"}}
   ```

   Command line: `$SD --map docs/spec_map.json --dry-run --strict --out /tmp/jevmcp-plan.json`
   (exit 2 while anything is wrong). A clean result reads:

   ```
   docs/spec_map.json: 131 entries ready to check; 44 marked excluded (not requirements, never sent)
   a full check would cost about $0.0061
   OK - the map is complete and every entry resolves.
   ```

7. **Ask for consent, then run the first full check.** State plainly: each requirement's sentence
   and the code paired with it (comments removed, secret-looking values redacted, paths relative)
   goes to `api.typesafe.ai`, and the estimate from step 6. On a yes:

   ```json
   {"name": "check_spec_drift", "arguments": {"all": true, "project": "/absolute/path"}}
   ```

   Then work the labels (recipe 4) and report.

8. **Finish the setup.** Suggest committing `spec_map.json` with the code, and adding the free
   strict validation to CI (recipe 6) so a new spec sentence cannot go unmapped. Record the
   consent and any project-specific lesson in the project's `CLAUDE.md` or `AGENTS.md` under
   "Spec drift".

---

## 2. The routine check after changing code

Do this before you tell the user a coding task is done, in any project that has a `*spec_map.json`.

1. **Check the code you changed is in the map's world.** No `*spec_map.json` in the project means
   there is nothing to check; say so and stop (do not set one up unasked).

2. **Run the check on the changed files.** With no `files`, the tool uses what git reports:

   ```json
   {"name": "check_spec_drift", "arguments": {"project": "/absolute/path"}}
   ```

   Name them yourself when you know exactly what you touched (paths relative to the project):

   ```json
   {"name": "check_spec_drift",
    "arguments": {"files": ["src/orders/service.ts", "src/config.ts"], "project": "/absolute/path"}}
   ```

   Command line: `$SD --map docs/spec_map.json --changed --jobs 8 --out /tmp/jevmcp-drift.json`,
   or `--changed src/orders/service.ts src/config.ts`.

   The default set is what `git diff --name-only HEAD` reports plus untracked files — that is
   **uncommitted** work only. Work you have already committed on the branch is not in it: name
   those files explicitly, or use `all: true`.

3. **Read the head line** before anything else:

   ```
   spec-drift check (docs/spec_map.json): 7 of 131 claims, about 2 file(s) git reports as changed | index 0.21s (warm: 2 of 1631 files parsed again)
   ```

4. **`nothing to check - no claim in the map is about those files`** is a valid result. Say that no
   requirement covers what you changed. Do not escalate to `all: true` to produce something to
   report; that spends the user's credits for nothing.

5. **Work the labels** (recipe 4), then report. Keep it proportionate: investigate flagged items in
   the repository, do not start sub-agents or build and run code unless the user asks for a deep
   review.

6. **Never report "no drift" from a run that did not complete.** If the result says
   `INCOMPLETE - not everything was checked` (or the command line exits 3), say the check did not
   run and carry on with the user's task.

---

## 3. A full check before a release

1. **Validate first (free)** — recipe 1, step 6. A stale map produces noise, and the validation
   output also gives you the cost estimate for step 3.

2. **Fix any map problems before checking.** Entries that cannot be resolved are *not* checked, and
   a check that skips entries is not a release gate.

3. **Tell the user the cost and confirm** if this is the first check in this project or this
   session: `a full check would cost about $0.0061`.

4. **Run it.**

   ```json
   {"name": "check_spec_drift", "arguments": {"all": true, "project": "/absolute/path"}}
   ```

   Command line: `$SD --map docs/spec_map.json --jobs 8 --out /tmp/jevmcp-drift.json`
   (exit 0 = no drift, 1 = at least one DRIFT, 2 = setup or map problem, 3 = TypeSafe unavailable).

5. **On a very large map, try `--limit 20` first** (command line) to see the shape of the results
   cheaply before the full run.

6. **One call is enough.** The server allows 20 `check_spec_drift` calls a minute and 120 calls of
   any kind a minute; re-running the same check is wasted money, not a second opinion — the
   thresholds are fixed.

7. **Report** as in recipe 4, and say explicitly whether every claim was checked
   (`complete: true` in the structured result).

---

## 4. What to do with each label

On a large map a full check can flag dozens of claims. Investigate every DRIFT, the ten or so
highest-P `review` items, and the `??` items that matter for the task at hand; report the rest as
counts and say how many you did not open. A first reply the user can act on beats a complete one
they never see.

The fast model screens; you investigate only what it flags.

| Label | What it means | What you do |
|---|---|---|
| **DRIFT** | verdict "drifted", confidence ≥ 0.905 | Investigate every one. Decide which side is wrong. |
| **review** | the model leans one way without enough confidence (a "drifted" below 0.905, an "accurate" below 0.987, or an "accurate" contradicted by a stated value) | Sorted by P(drifted): investigate from 0.30 up, skim below. |
| **??** | verdict "not enough information" or "unrelated" | **Not a pass.** The code shown cannot settle the claim. Fix the map entry, then check that file again. |
| **ok** | verdict "accurate", confidence ≥ 0.987 | Spot-check two, plus every one whose `value_mismatch` is ≥ 0.5 (the report lists them). |

Each flagged item carries `severity` 0–3 (how badly a reader following the spec would be misled)
and `value_mismatch`. Use severity to order your work, not to decide whether to look.

**Deciding whether the spec or the code is wrong**, per DRIFT item:

1. Open the results file named in the output and read the **exact code that was sent** for that
   claim. Half of all "drift" is a map entry pointing at the wrong place — if the code sent is not
   the code that enforces the sentence, this is a map fix (recipe 5), not a finding.
2. Read the real code around it in the repository, including what the sent excerpt left out.
3. Ask the history: `git log -p -L :<symbol>:<file>` or `git blame` on the enforcing lines, and
   `git log -1 --format=%s` on the commit that changed them.

   | What the history shows | Conclusion |
   |---|---|
   | A deliberate change with a commit message, issue or test that states the new behaviour | The **spec** is stale — propose the wording change. |
   | An incidental edit (refactor, rename, a constant changed in passing), no test covering the new behaviour | The **code** drifted — propose the fix. |
   | The spec sentence is newer than the code | The code was never updated — propose the fix, and check it is not simply unimplemented work. |
   | Both sides were changed deliberately and disagree, or the sentence is a policy question (a limit, a price, a retention period) | **Ask the owner.** Do not choose. |
4. Check the tests: a test asserting the current behaviour is strong evidence the change was
   deliberate; a test asserting the spec's behaviour and failing is a code bug.
5. Report as a short table — claim (`spec file:line`) · label · P(drifted) · what you found · which
   side to fix — then your recommendation. If an earlier drift report exists in the project, say
   which findings are new. Do not change the spec or the code without the user's word.

For **`??`**, the fix is always in the map: add the implementation, the constant, the caller, or a
line range that contains the behaviour, then re-run the check for that file. Never count `??` as a
pass, and never leave it silent in a report.

---

## 5. Keeping the map honest when code or spec moves

Run `validate_spec_map` (free) after any refactor, any spec edit, and before any full check. Each
message has one correct fix.

| Message | What happened | Fix |
|---|---|---|
| `route 'GET /api/x' not found among 18 routes. Did you mean: ...` | the endpoint moved or was renamed | Point at the new route; if it is gone, the spec sentence is the thing to settle with the user. |
| `config key 'app.x' not found. Did you mean: ...` | the setting was renamed | Update the key in `code`. |
| `'OrderService.place' not found in src/Orders.java. Did you mean: ...` / `It has: ...` | the symbol was renamed or moved file | Update the reference to the new name or file. |
| `file 'src/x.ts' not found (looked in: ...)` | the file moved | Update the path. |
| `line range 120-160 is outside src/x.go (95 lines)` | the file shrank | Re-anchor the range (recipe 7). |
| `the spec changed since this entry was reviewed - NOT checked` | `spec_text` no longer appears in the spec | Re-read the entry against the current spec, update `text` if the requirement itself changed, and paste the current spec paragraph into `spec_text`. |
| `N sentences in docs/spec.md are not in the map, so NOT checked: lines ...` | the spec gained sentences | Decide each one as in recipe 1, step 5: map it, or exclude it with a `why`. |
| `N excluded sentences have changed in the spec` | an excluded sentence was reworded | Decide again — rewording often turns rationale into a rule — then update its `spec_text`. |
| `N map entries are not marked "status": "reviewed"` | drafted entries never reviewed | Review them; a word-overlap guess is often wrong. |
| `N excluded entries do not say why` | an exclusion with no reason | Add the `why`, so the next reader sees it was a decision. |
| `N entries have no spec_text and their text is not word-for-word in the spec` | a spec change cannot be ruled out for those entries | Paste the spec paragraph each one is about into its `spec_text`. |

Rules that hold whatever the message says:

- **Never delete an entry** to make the strict check pass — the sentence then shows up as unmapped,
  and if you delete it from the spec too, the requirement is silently gone.
- **Never blank or fake a `spec_text`** to clear "the spec changed": that is the only thing that
  notices a requirement was rewritten.
- **Never change an exclusion** without saying so in your report.
- When a moved sentence is the only change, the tool says
  `note: N entries' sentences moved to a new line in the spec` and uses the new line number — no
  edit needed.
- A lesson specific to the project (a blind spot seen twice, a file every claim needs) belongs in
  the project's `CLAUDE.md` or `AGENTS.md` under "Spec drift".

---

## 6. Running it in CI

Two separate jobs. The first is free and belongs on every merge request; the second costs a
fraction of a cent and needs network access and a key.

**Job A — the free gate (no key, no network to TypeSafe, nothing sent).**

```bash
uv run --quiet --script "$PLUGIN/scripts/spec_drift.py" \
  --map docs/spec_map.json --dry-run --strict --out "$CI_ARTIFACTS/spec-plan.json"
```

Exit 2 fails the job. It fails when a spec sentence is neither mapped nor excluded, when an entry
is not reviewed, when an exclusion has no `why`, when an entry's spec text changed since review, and
when any reference no longer resolves. `spec-plan.json` is a useful artefact: it holds every claim,
its code references, exactly what would be sent, and a `problems` array.

**Job B — the real check, where the network works.**

```bash
export TYPESAFE_API_KEY="$CI_TYPESAFE_KEY"        # from the CI secret store; never in the repo
FILES=$(git diff --name-only "$MERGE_BASE"...HEAD)
if [ -n "$FILES" ]; then
  uv run --quiet --script "$PLUGIN/scripts/spec_drift.py" \
    --map docs/spec_map.json --changed $FILES --jobs 8 --out "$CI_ARTIFACTS/drift.json"
fi
```

Points that decide whether this works:

- **`--changed` with no file list is wrong in CI.** It means "what git reports as uncommitted or
  untracked", and a fresh checkout has nothing uncommitted — the job would pass while checking
  nothing. Compute the list against the merge base, as above, and skip the step when it is empty.
  For a release pipeline, drop `--changed` entirely and check everything.
- **The key.** `--key-file /abs/path/typesafe.env` (absolute path), else `TYPESAFE_API_KEY` in the
  environment, else a `TYPESAFE_API_KEY=` line in the `.env` of the folder the command runs in.
  Use the CI secret store; never commit a key, and never echo the variable in a log.
- **Exit codes and the policy the tool itself recommends:**

  | Exit | Meaning | Suggested CI policy |
  |---|---|---|
  | 0 | everything checked, no DRIFT | pass |
  | 1 | at least one DRIFT | report, do not block the merge |
  | 2 | setup or map problem — something was **not** checked | **fail the job** |
  | 3 | TypeSafe could not be used (outage, credits) | report, do not block; never call this "no drift" |

- **Do not run an agent in CI to do this.** In Codex, `codex exec` uses approval policy "never",
  which blocks every MCP tool, and `--approve-for-me` does not help because the automatic reviewer
  refuses a tool that sends code to a third party. Codex's sandbox also has no network, so a
  fallback to the command line inside a session reaches nothing and reports nothing. Run the script
  directly, as above. See [clients.md](clients.md) for the one flag that does work and why it is
  only for an already isolated container.
- **One gotcha for repositories where nothing parses** (everything mapped by line range): job A
  also fails with exit 2 on `no code found in <dir>`, because the command line checks the index as
  well as the map. Read `problems` in `spec-plan.json` and fail only on problems other than that
  one message, or run the validation through the MCP tool instead, which does not apply that check.

---

## 7. Checking a project in a language without a parser

Symbols, `route:` and `config:` references work for Java, JavaScript/TypeScript and Python.
Everything else — Go, Ruby, PHP, shell, COBOL, SQL — is paired by **line range** or by a small whole
file. The check itself works exactly the same; only the pairing is manual.

1. **Confirm the situation.** `$SD --docs docs/spec.md --dry-run --out /tmp/plan.json` prints
   `note: N .go files can only be paired by line range (file:120-160)`. If instead it says a parser
   is **missing**, that is a different problem — run the `pip install` line it prints.

2. **Draft the map anyway** (`draft_spec_map`). The suggestions will be poor or empty, but you get
   one entry per spec sentence with `spec`, `line`, `text` and `spec_text` filled in, which is the
   tedious part.

3. **Fill in each `code` by hand as a range.** Line numbers are the file **as written** — count them
   in the file itself:

   ```json
   {"spec": "docs/spec.md", "line": 12,
    "text": "An order may contain at most 50 items.",
    "status": "reviewed", "why": "the cap and the check that applies it",
    "code": "internal/orders/orders.go:14-31"}
   ```

   - Make the range the smallest span that contains the whole behaviour, including the constant.
   - Everything paired with one sentence shares a 2,600-character budget and is cut off beyond it,
     so two tight ranges beat one wide one: `["internal/orders/config.go:8-9", "internal/orders/orders.go:20-31"]`.
   - A small whole file (`internal/config.rb`) is fine; a large one wastes the budget.
   - Comments are removed before sending for Go, Rust, C/C++, C#, Kotlin, Scala, Swift and the rest
     of the C family; PHP, Ruby and shell are sent as written. Either way the range refers to the
     file as it is on disk.

4. **Validate (free)** and fix `line range 120-160 is outside <file> (95 lines)` errors.

5. **Expect ranges to go stale faster than symbols.** A rename does not move a range, so nothing
   complains while the range slides onto the wrong code. After any refactor of those files,
   re-read each range's entry and re-anchor it; `preview_spec_check` (free) shows you exactly what
   each entry would now send, which is the quickest way to spot a slid range.

6. **Know the one CI difference:** the command line reports `no code found in <dir>` and exits 2 in
   a project where nothing at all parses, even though every line-range entry resolves and
   `validate_spec_map` (MCP) reports the map ready. Recipe 6 says how to handle it.

---

## 8. The fast model's blind spots — judge these yourself

A low P(drifted) on any of these is **not** a pass, whatever the label says. Check them by hand
whenever a claim touches them.

1. **Settings hard-coded in code.** `Map.of("cache.backend", "redis")` or a dict literal reads as
   "configuration" to the fast model. Any claim that something is *configurable*, *selected by a
   setting* or *changeable without a rebuild* needs your own look at whether a real setting exists.
2. **Library and platform behaviour** — what a JDK call, a framework default or an ORM actually
   does. The model sees the call, not its implementation.
3. **Arithmetic on variables.** The tool computes literal expressions only (`15*60*1000`) and puts
   the result in `computed_values`; `timeout / 2` or a value assembled at runtime is not worked out.
4. **Anything spanning several files** — module dependencies, who calls what, "only X may do Y",
   "no other service writes to this table". The model sees one excerpt at a time; an "only" or
   "never" claim can be confirmed by the excerpt and still be false elsewhere in the repository.
5. **Claims that only a comment or a docstring documents.** Comments and docstrings are stripped
   before sending, so the evidence never arrives; expect `??`, and fix the entry to point at code
   that shows the behaviour.
6. **Settings reached through a settings object.** A `config:` reference finds the key's
   definitions and the places that name it, not `settings.max_items` twenty files away — so a
   claim can look unenforced when it is enforced, or the reverse.

When you report one of these, say which of them you checked by hand rather than implying the tool
confirmed it.

---

## 9. When something is missing — what to tell the user

Never ask for the API key in chat, never put it in a command you run, never run `--set-key`
yourself (it refuses anyway unless stdin and stdout are a terminal), and never read the project's
`.env`.

**No key.** `check_spec_drift` fails with `No TypeSafe API key is set for this server, so nothing
was sent.` Say, in one message:

> The spec-drift check needs a TypeSafe API key, which only you can set — I never see it.
>
> - **Claude Code:** run `/plugin manage`, open jevmcp, and set "TypeSafe API key". Claude Code
>   keeps it in its credential store, out of settings files. Restart when it asks.
> - **Codex or another client:** in your own terminal, run
>   `uv run --quiet --script <plugin>/scripts/jevmcp_server.py --set-key` — it asks for the key
>   without showing it and writes `~/.config/jevmcp/typesafe.env` (mode 600), which survives plugin
>   updates. Then restart the agent.
>
> A key comes from <https://console.typesafe.ai>. `validate_spec_map` and `preview_spec_check` need
> no key, so I can still validate the map and show you what a check would send.

Then carry on with their actual task. `jevmcp_server.py --show-key-source` (free, never prints the
key; exit 0 if a key is found, 1 if not) tells you which source would be used if you need to
diagnose it.

**No spec.** `draft_spec_map` needs a document. Say what you looked for and where, name any
candidates you found, and ask which is the source of truth. If there is genuinely no written spec,
say so plainly: the check compares code against a document, so with no document there is nothing to
check. Offer to set it up later, and do not write a spec yourself unless asked.

**No map.** The tools fail with `this project (<path>) has no spec map yet (no *spec_map.json)`.
Offer recipe 1 and say what it costs the user: mostly their time reviewing entries, roughly five
minutes of it for a short spec, plus fractions of a cent for the first check. Do not draft and
review a map unasked in the middle of another task.

**Several maps.** `this project has several spec maps - say which one with 'map'`, followed by the
paths. Ask the user which one, or pass `map` explicitly if the right one is obvious from the files
you changed.

**No `uv` on PATH.** The server cannot start at all: the client shows the jevmcp server as failed.
Point the user at <https://docs.astral.sh/uv/> and [install.md](install.md); the dependencies are
declared in the scripts themselves, so nothing is installed into their project.

---

## Never

- Send code without consent, or before the map validates.
- Ask for, print, pass or store the API key, or read the project's `.env`.
- Treat `??` as a pass, or report "no drift" from an incomplete run or an exit 3.
- Overwrite a reviewed map, delete entries or blank a `spec_text` to make a check pass.
- Change the checker's questions or thresholds, or call the TypeSafe API by hand.
- Commit anything, or edit the spec or the code to resolve a DRIFT, without the user's word.

Related: [install.md](install.md) · [tools.md](tools.md) · [clients.md](clients.md) ·
[the plugin README](../README.md) · [PRIVACY.md](../PRIVACY.md)
