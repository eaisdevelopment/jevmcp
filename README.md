# jevmcp

Plugins that let coding agents — **Claude Code** and **OpenAI Codex** (both tested; other clients of
the portable [Agent Plugins](https://agent-plugins.org) format may work, see [Known gaps](#known-gaps))
— use TypeSafe's fast model **Jev** as routine tooling across the software lifecycle. The fast model
screens everything in seconds, at a fraction of a cent per item; the agent spends its own effort
only on what the fast model flags. Jev is a classifier from TypeSafe (<https://typesafe.ai>), not a chat model: it picks one of the
answers it is offered and gives a probability for each.

Current release: **1.7.4** (2026-09-26) — [what changed in each release](plugins/jevmcp/CHANGELOG.md).

## One plugin, installed once

Everything lives in a single plugin, **jevmcp**. Install it once; new tools arrive as updates, with
no second install and no second API key.

| Tool | What it does | Status |
|---|---|---|
| **spec-drift** (skill) + tools on the `jevmcp` server (`check_spec_drift`, `validate_spec_map`, `preview_spec_check`, `draft_spec_map`) | Checks code against its design spec or requirements. Jev screens every requirement against the code that implements it; the agent investigates only what it flags and says which side to fix. Java/Spring, JavaScript/TypeScript, Python, and any language by line range. Specs in English and other Latin-alphabet languages, and in Chinese, Japanese and Korean (CJK, see below); specs in other scripts are read a paragraph at a time, and Thai, Lao, Khmer and Tibetan mostly not at all ([details](plugins/jevmcp/README.md#languages)). | available |
| **ci-triage** (skill) + `triage_ci_failure`, `preview_ci_triage` | Reads a failed pipeline and says what actually broke: for each distinct failure, whether the change under test caused it, the error line that says why, and the next step. A GitHub Actions run of your project (read with your own `gh`), or a log from any CI. | available |
| **code-audit** (skill) + `check_code_rules`, `preview_code_audit`, `validate_rule_map`, `draft_rule_map` | Screens a codebase against its own rules and conventions: each rule you approved from CLAUDE.md, AGENTS.md, CONTRIBUTING or a style guide, against each unit of code it covers. | available |

Each tool is its own skill, and all of them share the single `jevmcp` MCP server: one install,
one server process, one API key. Your client can still approve or disable each tool separately.

**What is CJK?** The usual short name for **C**hinese, **J**apanese and **K**orean. The three share
the Han characters (Chinese hanzi, Japanese kanji, Korean hanja, which modern Korean seldom uses),
which is why software and Unicode group them. For reading a spec, what matters is how their
sentences look. Chinese and Japanese put no spaces between words and end a sentence with `。`, `！`
or `？`. Korean has spaces but is written in its own alphabet, Hangul, which has no capital letters.
A splitter built for English (a full stop, a space, a capital letter) therefore misses their
sentences. Since 1.7.3 jevmcp reads all three sentence by sentence.

## What the labels mean

Every result gets a label, and your agent acts on the label:

- **DRIFT** (spec drift), **CHANGE** (CI triage), **BREAKS** (code audit): Jev is sure there is a
  problem — the spec and the code disagree, the change under test caused the failure, or the code
  breaks a rule. The agent investigates each one.
- **review**: Jev leans one way but is not sure. In CI triage this also covers every failure Jev
  blames on something other than the change. The agent reads these from the most likely down,
  within a budget the skill sets.
- **??**: Jev cannot tell from what it was sent. It is never a pass.
- **ok** (spec drift and code audit; CI triage never clears a failure): Jev is sure there is no
  problem. The agent spot-checks a couple.
- **n/a** (code audit): the rule is not about that code. **not checked** (CI triage): TypeSafe did
  not answer. Neither is a pass.

In CI triage, the *lean* is Jev's best guess at the cause: the change, the environment, a
dependency or a flaky test. In spec drift, a *claim* is one spec sentence together with the code
paired with it in the map.

## What it costs, and how fast

Measured on real projects:

| What | Time | Cost |
|---|---|---|
| Spec drift, check after editing two files (a real Java project, 131 requirements; measured before 1.6.0, when each claim was asked once) | 3 s | $0.0013 |
| Spec drift, full check of the same project (same caveat: since 1.6.0 a claim the first answer does not settle is asked up to twice more, so a first check costs more) | 11 s | $0.006 |
| Spec drift, repeating a full check of unchanged code (jevmcp's own docs as of 1.6.0, 180 claims; answers are cached) | 0.3 s (32 s uncached) | $0.0000 ($0.0207 uncached) |
| CI triage, per failure | | about $0.0002 |
| Code audit, Django (1,535 rule/code checks) | | $0.09 |

The fast model is rarely where the money goes. In two real Claude Code sessions on that Java
project, the check cost about $0.001, while the agent's own investigation cost $2.53 and $4.32 as
Claude Code reported it. So the cost that matters is how many flagged items the agent opens, and
the skills set a budget for that.

By our estimate from published prices, Jev's lower price, compared with asking a general-purpose
model the same questions, matters most above roughly 10,000 calls a month. Below that, the reason
to use it is that every answer is one of the options it was offered and comes with a probability,
so jevmcp can apply fixed, measured thresholds instead of reading prose.

## How well it works

Each of the three tools was measured on real repositories before release. Some drifts and rule
violations were planted in real code on purpose, as one-line changes, so the right answer is known.
For CI triage, code audit and CJK reading, jevmcp's thresholds and settings were tuned on some
repositories and then scored on others kept aside (the *held-out* set). Spec drift has no held-out
set: most of its numbers come from one Java project, the same one its decision rule was chosen on.
Where we changed a threshold or fixed a bug after seeing a held-out result, the bullet says so. Full
tables for CI triage, code audit and CJK reading are in the [CHANGELOG](plugins/jevmcp/CHANGELOG.md).

- **CI triage** (52 held-out failed runs from 8 open-source repositories): **CHANGE** was right
  6 times out of 6, with 0 false alarms. It fires on only 6 of the 33 failures the change caused;
  of the other 27, 26 go to review and 1 came back `??`, and the agent decides both. The lean pointed the right way on 43 of 47
  runs. The first held-out run was invalid (the log parser read none of those logs' job headers);
  only the parser was fixed, and the held-out set was run again. On the tuning runs: without the
  change under test, or with only the last 25 lines of the log, every failure came back `??` (14 of
  14), so it says it cannot tell rather than guessing; and the same question asked 20 times gave
  the same verdict every time, on 15 of 15 failures.
- **Code audit** (91 held-out rule/code pairs from 6 repositories): **BREAKS** was right 13 times
  out of 13, and never fired on the 44 compliant pairs. It misses some violations: the list the
  agent reads (every BREAKS, plus the `review` items most likely to break a rule) held 35 of the 47
  real ones. That number is not blind: two thresholds were changed after the held-out set showed
  the gap. Then, on recent real commits of Django and Vite (tuning repositories) and rust-analyzer,
  a reviewer that never saw the tool's labels confirmed 26 of the 29 BREAKS it could judge (21 of 21
  in Django). The noise is in `review`: a sample of review items held a real violation in 1 of 40
  in Django, 0 of 19 in Vite and 9 of 40 in rust-analyzer.
- **Spec drift** (the same Java project as in the cost table, with an earlier map of 115 claims;
  before the run, an AI agent read the code and wrote down the right answer for each, finding 40
  drifts): Jev is a good sorter. It found one drift the agent had missed, and counting it (41), the
  10 claims Jev ranked most likely to have drifted were all real drifts, and it ranks a real drift
  above an accurate claim 81% of the time. It is not a judge on its own: its answer changed between
  identical calls on 32% of these claims. So a claim that one answer does not settle is asked again,
  and decided only when every answer agrees and none is below 0.85 confidence. On this project,
  where the rule was chosen, that labels 18.3% of claims DRIFT or `ok` outright, up from 4.3%, with
  no real drift passed as `ok` and no accurate claim called drifted; the rest are `review`, sorted
  by probability, or `??`. On a small second test (commander.js: 15 accurate claims and 13 planted
  drifts, keyed by us), the rule labelled 2 of the 15 `ok` and passed no planted drift.
- **Chinese, Japanese and Korean specs** (1.7.3; 160 held-out paragraphs, labelled blind by an AI
  agent told to read as a native speaker, with no access to the tool): the share of sentences found
  rose from 0.19 to 0.93 in Japanese, 0.28 to 0.93 in Chinese and 0.53 to 1.00 in Korean. One target
  set in advance was missed: 1.7.3 keeps a few more short fragments (image lines, links, labels)
  than 1.7.2 did, because 1.7.2 dropped nearly every sentence, real ones included. Text without a
  Chinese, Japanese or Korean letter is read exactly as before (3,265 documents gave identical
  output).

## What it cannot do

Some limits come from the model and the service:

- **Jev classifies; it does not write.** It picks an answer from a list and gives a probability.
  It cannot explain code or say how to fix it, and it cannot write a corrected spec, so every DRIFT,
  BREAKS and CHANGE is your agent's call.
- **It is strong on narrow questions when the evidence is in what it is sent.** In our own
  hand-built tests of the model (not real repositories), it sorted 30 of 30 CI failures when given
  the rerun result, the failure history and the diff (86.7% with only a stack trace), and judged 26
  small doc/code pairs correctly 96–100% of the time as a two-option question. Real projects are
  harder: see "How well it works".
- **High confidence does not show that the input held the answer.** In other hand-built tests, with
  the key fact removed from the input, accuracy fell from 95% to 10% while confidence fell only
  from 0.95 to 0.75. That is why every question offers "cannot tell", why `??` is never a pass, and
  why an unsettled claim is asked again.
- **In spec drift, some things the agent must judge itself,** because the model is known to get
  them wrong: settings hard-coded in the code, the behaviour of a library or framework, arithmetic
  on variables, and logic spread across several files. A claim about what the code never does
  cannot be settled by any excerpt of code.
- **It is advisory, not a gate.** As of 21 September 2026 TypeSafe published no uptime commitment,
  and in the 90 days before that date the service was down for 194 minutes in total (about 3
  hours). Do not make a Jev check a mandatory merge gate. Never read a run that could not reach
  TypeSafe as a pass: the tools mark it incomplete, and the command line exits with code 3. Code
  audit is not a linter, a type checker or a security review.
- **Codex blocks unattended sends.** `codex exec` cannot ask for approval, so it blocks every tool
  that sends. `--dangerously-bypass-approvals-and-sandbox` lets it send, but it switches off Codex's
  sandbox and every approval, so use it only where the whole job is already isolated, such as a CI
  container. In CI the better choice is to run the command-line scripts (`spec_drift.py`,
  `ci_triage.py`, `code_audit.py`) directly. Inside a Codex session, use the tools, not the scripts:
  Codex's sandbox has no network, so a script there cannot reach TypeSafe.

Some limits are choices, and can change when the evidence does:

- A spec-drift request carries one requirement and at most 2,600 characters of the code paired
  with it; a code-audit request carries one rule and at most 2,600 characters of one unit of code.
  Neither ever sends a whole repository. The model's accuracy falls when the input holds look-alike
  names or related facts far apart, and a large slice of code has both.
- CI triage never decides "not caused by the change" on its own. A real regression blamed on the
  environment would be retried away and shipped, and no corpus is large enough yet to show that
  this is rare.
- The spec you name is used exactly as named. Guessing which spec is current went wrong when the
  guess overrode the user's choice; "looks newest" is now only a hint when nothing is named.

## Known gaps

- Named functions and classes are found in Python, Java, JavaScript and TypeScript (and OpenAPI
  files); other languages are paired by line range. On the command line, `spec_drift.py` stops with
  "no code found" (exit code 2) in a project that has only such languages, such as C or C++, even
  when every requirement is paired by line range.
- Chinese, Japanese and Korean beyond reading the spec: the list of likely spec files does not
  recognise their spec names (仕様, 要件, 需求, 명세); code audit finds no rules in a Chinese, Japanese
  or Korean style guide, because it knows no rule words such as 必须, べき or 해야; and the free check
  that flags sentences about what code never does knows English words only.
- Codex: the code-audit tools, and a CI triage sent from a Codex session, have not been verified.
- Cursor is not supported (it does not expand `${PLUGIN_ROOT}`). VS Code, GitHub Copilot and Kiro
  may load the portable plugin, but none has been tested end to end.

## What happens the first time (about 5 minutes, once per project)

You do not create or edit any file yourself. In your project, ask your agent:

> Set up spec-drift checking for this project. The spec is in specification/final.

1. **You name the spec** — a file, several files, or a folder — and exactly that is checked. The
   tool never second-guesses it: name `specification/final` and only `final` is used, even if
   `specification/v3` next to it was edited later. If you do not name it, the agent lists the
   files that look like specs — design, requirements, architecture, ADR or RFC documents (Markdown
   or reStructuredText) — with the date each was last committed and hints about old copies (a
   version number or a date in the name, a folder such as `archive/`, a line near its top that
   says "superseded" or "deprecated"), and asks you to choose. The hints never decide.
2. It runs `draft_spec_map` on what you named, which **writes `spec_map.json` for you**: one entry per
   sentence of the spec, each with a suggested place in the code. Nothing is sent anywhere; this
   is free.
3. It reviews the entries with you, fixes the wrong guesses, and marks sentences that are not
   requirements as excluded with a reason. This is the part that needs your knowledge, and it is
   the only part that takes time.
4. `validate_spec_map` confirms the file is complete, and you commit it with your code.

From then on, a check is one sentence — *"Check my changes against the spec"* — and takes seconds
and fractions of a cent, because each requirement is sent with only the code it is about.

**What is `spec_map.json`?** It is the pairing between your spec and your code: for each sentence,
which code implements it. One entry looks like this (the agent writes it, you review it):

```json
{"spec": "docs/spec.md", "line": 6,
 "text": "An order may contain at most 50 items (SHOP_MAX_ITEMS).",
 "status": "reviewed",
 "code": ["app/settings.py:SHOP_MAX_ITEMS", "app/services.py:place_order"]}
```

Without it, checking a spec would mean sending your whole repository to a model for every
sentence. With it, the fast model gets one requirement and the few lines that enforce it.

## Install

You need [`uv`](https://docs.astral.sh/uv/) and a TypeSafe API key
(<https://console.typesafe.ai>).

**Claude Code**

```
/plugin marketplace add eaisdevelopment/jevmcp
/plugin install jevmcp@jev
```

Claude Code asks for the API key when the plugin is enabled and keeps it in its credential store.

**OpenAI Codex**

```
codex plugin marketplace add eaisdevelopment/jevmcp
codex plugin add jevmcp@jev
```

Codex has no prompt for keys. Store it once, in your own terminal:

```bash
uv run --quiet --script "$(ls -d ~/.codex/plugins/cache/jev/jevmcp/*/scripts/jevmcp_server.py | sort -V | tail -1)" --set-key
```

It asks for the key without showing it, writes `~/.config/jevmcp/typesafe.env` (readable only by
you), and survives plugin updates. No file for you to create by hand.

**Other Agent Plugins clients**: `plugins/jevmcp` is a portable Agent Plugins 1.0.0 package
(`plugin.json`, `mcp.json`, `skills/`). See the [plugin's README](plugins/jevmcp) for how it gets
its key.

**Updating**: `claude plugin update jevmcp@jev`, or in Codex
`codex plugin remove jevmcp@jev && codex plugin add jevmcp@jev`.

## Your API key stays yours

No key is stored in this repository, and none should ever be: the plugins' MCP servers read the
key from the client's own settings, from your environment, or from the plugin's data folder on
your machine — never from a file in this repository or in the project being checked. Never paste a
key into an issue or pull request.

## How we test it

- **Real repositories.** For CI triage, the answer key is what really happened: the fix commit, or
  a re-run that passed. For code audit, it is a maintainer's review comment or a one-line change to
  real code. For spec drift and for Chinese, Japanese and Korean reading, it is an AI agent's reading,
  written down before scoring. For CI triage and code audit, a second AI agent re-derived each key
  without seeing the tool's labels; the few it disputed (2 of 73 CI keys, 3 code-audit pairs) were
  left out. A failed run is reported, not hidden: the first CI held-out run was invalid because of a
  parser bug, and the CHANGELOG says so.
- **Real agent sessions** on the installed plugin before a release (38 for 1.7.2, 4 for 1.7.3, and
  earlier ones). Each mistake became a skill fix. On 1.7.0, without the user's yes to send, agents
  judged the previewed CI failures themselves instead of asking; nothing was sent, and 1.7.1 fixed
  it. On 1.5.0, agents told to investigate everything flagged (about a hundred review items) were
  still working after a quarter of an hour, with nothing reported; 1.5.1 set a budget. Agents also
  tried to start multi-agent workflows for a routine check (blocked, as workflows need approval);
  the skill now says to keep a check proportionate.
- **Adversarial review.** Before a release, review agents look for bugs in jevmcp's own changes,
  and a second reviewer tries to refute each one. In 1.7.3: 43 reported, 30 confirmed and fixed, 13
  refuted.
- **Nothing else changes by accident.** The 1.7.3 change for Chinese, Japanese and Korean was run
  over 3,265 other documents and 2,472 map checks on English specs; every result stayed identical.
- **jevmcp checks its own documentation.** Its tool reference and privacy notes are mapped sentence
  by sentence to its own code (563 claims). A free, offline check in CI (no Jev call, no key)
  validates that map on every push that changes the plugin. In 1.7.1, mapping the new documentation
  to the code, sentence by sentence, found four places where the docs and the code disagreed.
- **363 automated tests.**

## Repository layout

```
.claude-plugin/marketplace.json    the marketplace, as Claude Code reads it
.agents/plugins/marketplace.json   the same marketplace, as Codex reads it
plugins/jevmcp/                    the plugin: skills/<family>/SKILL.md, scripts/, one MCP server for every tool
```

## Documentation

Written for an agent that has to install or drive this from the repository alone, and useful to a
human reading over its shoulder:

- [Install and set up](plugins/jevmcp/docs/install.md) — every client, every way to provide the
  key, how to check it worked, troubleshooting.
- [Tools, skills, maps, command line](plugins/jevmcp/docs/tools.md) — every argument, output,
  label and exit code.
- [How each client behaves](plugins/jevmcp/docs/clients.md) — approvals, unattended runs, sandbox
  and network, the verified limits.
- [Recipes](plugins/jevmcp/docs/how-to.md) — set a project up, routine checks, triage a failed
  CI run, audit before a pull request, what to do with each result.
- [AGENTS.md](AGENTS.md) — the short version, and the rules an agent must not break.
- [What is sent, and what never is](plugins/jevmcp/PRIVACY.md).
- [CHANGELOG](plugins/jevmcp/CHANGELOG.md) — every release, with how it was measured.

## Support

- Questions and bugs: [GitHub Issues](https://github.com/eaisdevelopment/jevmcp/issues)
- Security problems: [SECURITY.md](SECURITY.md)

## License

[Apache-2.0](LICENSE)
