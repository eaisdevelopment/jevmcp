# Changelog

## 1.6.0 — 2026-09-23

Four changes to how a claim is decided, every one measured against a corpus of 115 claims whose
right answer was written down before the model ever saw them. The harness that does the measuring
ships in the repository (`tools/score_eval.py` in the maintainers' tree), so a scoring change is
now an experiment rather than an argument.

**A claim one answer cannot settle is asked again.** The verdict itself moves between identical
calls on 32% of claims — measured, not assumed — so one confidence crossing a line was the noisiest
possible thing to gate on. A claim is now decided by agreement: every answer must match and none
may be below 0.85. On the graded corpus that takes the share of claims decided without a human from
**4.3% to 18.3%, with no real drift passed as `ok` and no accurate claim called drifted**. On this
repository's own documentation `ok` went from 3 of 180 to 15. Claims the first answer already
settled are never asked again, so the extra cost falls only on the uncertain middle. `--samples 1`
restores the old behaviour exactly.

**Answers are cached, so unchanged code is never paid for twice.** A verdict is a pure function of
what was asked, so it is keyed by a SHA-256 digest of the request — never your code, never your
spec, never your key — in `~/.cache/jevmcp/verdicts.json`. A repeat of this repository's own full
check went from 32 s and $0.0207 to **0.3 s and $0.0000**, with identical labels. The cache keeps
several independent answers per claim, because replaying one answer three times would make
unanimity meaningless.

**Claims that cannot be judged are named before anything is sent.** A `??` costs a request and
answers nothing, and 42% of this project's own claims came back that way. `--dry-run` and
`validate_spec_map` now say which entries will probably do so and why: a sentence about what the
code does *not* do, a lead-in ending in a colon, or code far larger than the 2,600 characters that
are sent. On our own map that is 30 of 180, found locally and for free.

**Code that does not fit is cut where the claim is looking.** Sending the first 2,600 characters of
a large function handed the model the top of it and called it the whole thing — the single biggest
cause of `??` in our own audit. The lines the claim names are kept instead, with context, and every
cut is marked so the model knows it is judging an excerpt.

Also: a run now reports **map health** — how many claims came back `??`, which symbol they were
paired with most often, and for each one what the sentence's own words suggest pairing it with
instead — and every `DRIFT` carries the decision to make, since Jev answers questions and cannot
write the corrected sentence itself.

*Measured and not shipped:* packing several claims into one request would save 39% of tokens (26%
of a run is the fixed per-request charge), but it agreed with one-claim-at-a-time on only 63% of
verdicts — against a 68% floor set by the model's own run-to-run variation. The experiment cannot
tell "batching hurts" from "the model wobbles", and the cache already removes repeat cost, so it
stays out until there is evidence.

## 1.5.3 — 2026-09-23

**jevmcp now checks itself.** `spec_map.json` at the repository root pairs every guarantee in
`PRIVACY.md` and every claim in `docs/tools.md` with the code that keeps it — 288 sentences, 180
checked, 108 excluded each with a written reason. A GitHub Actions job validates it on every push:
free, offline, no API key, and it fails when a symbol the map points at is renamed or a new
documentation sentence goes undecided. `AGENTS.md` tells an agent to run the check before
finishing a change to `scripts/`.

Running it on ourselves found four things, all fixed here:

- **Markdown table rows were drafted as fragments** — "The spec sentence | as written in your spec
  map", cell separator and all — which no model can judge. The drafter now joins a row's cells into
  a sentence and skips the header row.
- **List items lost the heading that carried their predicate.** "Code that no requirement in the
  map points at." means nothing on its own. When a heading is a statement rather than a label, it
  is put back on the front of the item's first sentence. Nested items are left alone: their
  predicate comes from the item above, not the heading.
- **`build_questions(claim)` never used its argument.** The documentation promises "three fixed
  questions, identical for every requirement"; a function that takes a claim said otherwise to any
  reader, and the model abstained on that very sentence. It now takes nothing.
- **A sentence the reader assembles counted as unmapped forever.** A joined table row and a
  heading-carrying item appear nowhere word-for-word, so `--strict` reported them missing even when
  they were in the map. An entry now always covers its own sentence.

One real drift in our own docs, found by the tool: `check_spec_drift` returns early when there is
nothing to check, with `summary` set before the label reminder is appended — so `docs/tools.md`
overstated what that field always contains. Corrected.

The skill gains a fifth blind spot: **a claim about what the code does *not* do** ("never", "only",
"no telemetry") cannot be settled by pairing. Code that does not do X proves nothing, and the one
place that does X reads as a refutation — which is exactly how "sends no telemetry", paired with
the single function that makes a request, produced a confident DRIFT against correct code.

## 1.5.2 — 2026-09-23

Documentation only; the tools, the server and the skill are unchanged.

Four releases after the marketplace was renamed to `jev`, two pages still described the old
layout: `install.md` said "version 1.3.1" and "the marketplace is also called `jevmcp`",
`clients.md` contradicted itself in one sentence ("the marketplace is named `jevmcp` ... so the
install id is `jevmcp@jev`"), both gave installed-copy example paths under an old version, and the
uninstall table told people to run `marketplace remove jevmcp` instead of `remove jev`. Anyone
following those lines would have recreated the duplicated-skill-path bug that 1.5.0 fixed.

Seven spots corrected, and two tests added so this cannot recur: one checks that every version a
page claims as current matches the server's `VERSION`, the other that no page calls the
marketplace `jevmcp` — except where it is explaining how to migrate away from the old one.

Also new, at the repository root: `claude_how_to_jevmcp.md` and `codex_how_to_jevmcp.md` — for each
client, the complete instruction it works from (the server's `instructions`, the skill's trigger,
the skill body in full, and all four tool schemas), followed by what that client does differently:
tool names, whether `project` is required, when approval is asked, where the key comes from, and
whether the shell has network. The instruction body is the same file in both, so the pages exist to
make the envelope explicit rather than the text.

## 1.5.1 — 2026-09-22

Found by running a full check on a real 131-requirement Java project: with about a hundred
`review` items, an agent that investigates everything flagged runs for a quarter of an hour and
reports nothing in the meantime. The skill and the recipes now set a budget — every DRIFT, the
ten or so highest-probability `review` items, the `??` items that matter, and counts for the
rest, with an honest note of how many were not opened.

## 1.5.0 — 2026-09-22

**The marketplace is now called `jev`, so installing is `jevmcp@jev`.** The plugin, the server
and the tools are unchanged.

```
/plugin marketplace add eaisdevelopment/jevmcp     # Claude Code
/plugin install jevmcp@jev
codex plugin marketplace add eaisdevelopment/jevmcp # Codex
codex plugin add jevmcp@jev
```

Why: a marketplace and a plugin with the same name put it twice in the installed path
(`…/plugins/cache/jevmcp/jevmcp/<version>/…`), and Codex's skill catalogue shortens that
ambiguously — in every session the first read of the skill file failed on a duplicated segment
before the retry succeeded. With `jev` the path has nothing repeated and the failure is gone.

If you installed an earlier version: remove it (`codex plugin remove jevmcp@jevmcp`, or
`/plugin uninstall jevmcp@jevmcp`), remove the old marketplace, then add it again and install
`jevmcp@jev`. A per-tool approval pinned to `jevmcp@jevmcp` in `~/.codex/config.toml` has to be
set again under the new id.

## 1.4.1 — 2026-09-22

Found by running a first-time setup in a fresh Codex session: an entry the drafter could not pair
was labelled "NO MATCH - fill in the code or delete this entry", which contradicts every other
instruction — a sentence that is not a requirement should be marked `excluded` with a reason, not
deleted, or `--strict` reports it as unmapped for ever. It now says: "point 'code' at what
enforces this, or set 'excluded' with a why".

## 1.4.0 — 2026-09-22

**Documentation an agent can act on, shipped with the plugin.** Everything needed to install,
understand and drive jevmcp now lives in the repository — and inside the installed plugin, so an
agent that can only see its own plugin folder can still read it.

- `docs/install.md` — every client, the four places the key can come from and the exact
  `--set-key` command per client, how to check the install, updating, uninstalling, and a
  troubleshooting table.
- `docs/tools.md` — each tool with every argument, its output fields, cost, and the errors it can
  return; the skill; the spec map format in full; the labels and thresholds; the command line.
- `docs/clients.md` — what Claude Code and Codex each do, and their verified limits: approvals,
  unattended runs (`--approve-for-me` is refused for a tool that sends code out), the sandbox with
  no network, tool naming, known quirks.
- `docs/how-to.md` — nine recipes, from setting a project up to CI, each a numbered procedure.
- `AGENTS.md` at the repository root: the short version and the rules an agent must not break
  (never ask for the key, consent before the first check, `??` is not a pass, never report "no
  drift" from a check that could not run).
- Corrections found while writing them: the marketplace card still advertised the pre-1.3.0 tool
  names; `project` must be the folder the server was started for, or one inside it, not "harmless"
  anywhere; a test now fails if a doc names a tool that does not exist.

## 1.3.1 — 2026-09-22

The last traces of the old name: a check's own report said "docdrift check", and so did several
error and help messages. Everything a user or a model reads now says jevmcp or spec drift.

## 1.3.0 — 2026-09-22

**Names say what they mean, and the key is set in one command.**

- Tools renamed so the name carries the subject: `check_drift` → **`check_spec_drift`**,
  `validate_map` → **`validate_spec_map`**, `draft_map` → **`draft_spec_map`**, `show_payload` →
  **`preview_spec_check`**. If you had approved a tool by name in `~/.codex/config.toml`, approve
  the new name once.
- Every place that says "spec map" now says what it is: the file `spec_map.json` that pairs each
  sentence of your spec with the code that implements it, written for you by `draft_spec_map`.
  That definition is in the server's instructions, in each tool's description, in the skill and in
  both READMEs.
- **`--set-key`**: store your TypeSafe API key once, from your own terminal. It asks without
  echoing, writes `~/.config/jevmcp/typesafe.env` (mode 600), survives plugin updates, and is read
  by any client that cannot hold the key itself — no file to create by hand. `--show-key-source`
  says where the key would come from, without printing it. When a check finds no key, the error
  names the exact command instead of talking about environment variables.
- Codex, unattended: `--approve-for-me` is refused for `check_spec_drift` (Codex's automatic
  reviewer blocks a tool that sends code to a third party). The README now gives the per-tool
  approval that does work.
- The command-line checker is `scripts/spec_drift.py` (was `docdrift.py`); the name "docdrift" is
  gone from everything a user or a model sees.

## 1.2.1 — 2026-09-22

Documentation: the README now explains what happens the first time you use it, and what
`spec_map.json` is. **You never create or edit that file yourself** — `draft_spec_map` writes it and
the agent reviews it with you. The skill's own description says so too, so an agent explains it
the same way.

## 1.2.0 — 2026-09-22

**One server for every Jev tool.** The MCP server is now called `jevmcp` (it was `docdrift`), and
the tools of every future family — CI failure triage, code audit — will be offered by that same
server rather than by a server each. One install, one server process, one API key.

- The server script is `scripts/jevmcp_server.py`; its four tools are unchanged
  (`check_spec_drift`, `validate_spec_map`, `preview_spec_check`, `draft_spec_map`), as is everything they do.
- In Claude Code the tools are now `mcp__plugin_jevmcp_jevmcp__<tool>`; in `~/.codex/config.toml`
  the table is `[plugins."jevmcp@jev".mcp_servers.jevmcp]`.

## 1.1.0 — 2026-09-22

**The plugin is now `jevmcp`: install once, get every Jev tool.** It was published earlier today as
`docdrift`, a plugin per tool. That would have meant a new install for each tool, so the packaging
changed before anyone depended on it: spec-drift checking is now the first tool inside `jevmcp`,
and the next ones (CI failure triage, code audit) arrive in the same plugin as updates, each with
its own skill and its own MCP server.

- Install: `/plugin install jevmcp@jev` (Claude Code), `codex plugin add jevmcp@jev` (Codex).
- Nothing else changed: the same skill `spec-drift`, the same MCP server `docdrift` with its four
  tools, the same API key, the same behaviour as 1.0.0 below.
- If you installed `docdrift@jevmcp` earlier today, remove it and install `jevmcp@jev`.

## 1.0.0 — 2026-09-22

First public release.

- **Skill `spec-drift`**: set up a project (find the spec, draft and review a spec map), check
  after every change, read the results, the fast model's blind spots, reporting.
- **MCP server `docdrift`**: `check_spec_drift`, `validate_spec_map`, `preview_spec_check`, `draft_spec_map`. Finds the
  project's spec map on its own; keeps the parsed code in memory and re-reads only changed files.
- **MCP 2026-07-28**, and still serving clients of earlier revisions (dual-era): stateless
  requests with per-request `_meta`; `server/discover`; `resultType` and the server's identity on
  every result; caching hints on `tools/list` and `server/discover`; `UnsupportedProtocolVersion`
  (-32022) and invalid-request errors as specified; tool titles, annotations, and structured
  results with a declared `outputSchema`; progress notifications; cancellation stops a running
  check from sending further claims, including retries; the server shuts down promptly when the
  client closes its input, and survives malformed input. Clients that open with `initialize` (2025-11-25 and earlier) are served with the shapes
  of their revision. Roots and Logging (deprecated in 2026-07-28) are not used: the project is a
  tool argument, and the server logs only to stderr.
- **Safety**: a client-named project is a boundary (never your home folder); rate limits on
  checks (`--max-checks-per-minute`, default 20) and on all calls (`--max-calls-per-minute`,
  default 120); the MCP server takes the key only from the client's settings, the environment,
  the plugin's data folder or an absolute `--key-file`, never from the project; results go to a
  private temporary folder that is removed when the server stops.
- **Packaging**: an Agent Plugins 1.0.0 portable core (`plugin.json` with the Codex listing under
  `extensions["com.openai"]`, `mcp.json` using `${PLUGIN_ROOT}`), plus `.claude-plugin/` and
  `.mcp.json` for Claude Code (the key is asked for at install and kept in its credential store)
  and `.codex-plugin/` for Codex (forwards `TYPESAFE_API_KEY`). Dependencies are declared inline
  and installed by `uv`.
- **Languages**: Java/Spring, JavaScript/TypeScript (NestJS, Express, Hono, Fastify, Next.js),
  Python (FastAPI, Flask, Django), OpenAPI, config files; any other language by line range.
- **Spec maps**: entries can be marked `excluded` with a reason, and `--strict` counts them as
  decided; it fails on unmapped sentences, unreviewed entries, exclusions without a reason, and
  entries whose spec text has changed since they were reviewed.
- **Redaction**: secret-looking values are removed by shape everywhere and by name in code and in
  configuration files, quoted or not; see PRIVACY.md.
