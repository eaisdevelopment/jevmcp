# Questions and answers

Short answers, each with the page that has the whole story. For steps to follow, see
[how-to.md](how-to.md); for every argument and output, [tools.md](tools.md); for installing,
[install.md](install.md); for how each client behaves, [clients.md](clients.md).

- [The plugin](#the-plugin)
- [Cost and the API key](#cost-and-the-api-key)
- [What leaves the machine](#what-leaves-the-machine)
- [Reading the results](#reading-the-results)
- [Setting a project up](#setting-a-project-up)
- [Doc claims and change claims](#doc-claims-and-change-claims)
- [CI triage](#ci-triage)
- [Codex](#codex)
- [Updates and support](#updates-and-support)

## The plugin

**What is jevmcp?**
One plugin for coding agents that puts TypeSafe's fast model, Jev, to work on narrow checks: does
the code still match its spec (spec drift), what actually broke in a failed CI run (CI triage),
and does the code follow the project's own rules, do its docstrings and test names still hold, and
does a pull-request description match the change (code audit). Jev screens everything; your agent
investigates only what it flags. See the [plugin README](../README.md).

**What is Jev, and why not let my agent's own model do it?**
Jev is a classifier, not a chat model: it picks one of the answers it is offered and gives a
probability for each. That lets jevmcp apply fixed, measured thresholds instead of reading prose,
and it costs fractions of a cent a question. It cannot explain code, write a fix or decide on its
own: every DRIFT, CHANGE, BREAKS, STALE and UNSUPPORTED is your agent's call.

**Which clients does it work with?**
Claude Code and OpenAI Codex, both tested. Other clients of the [Agent Plugins](https://agent-plugins.org)
1.0.0 format can load it, untested end to end. Cursor is not supported: it does not expand
`${PLUGIN_ROOT}`. See [clients.md](clients.md).

**Do I install something new for each kind of check?**
No. One plugin, one MCP server (`jevmcp`), one API key. New tools arrive as updates of the same
plugin.

**What do I need besides the plugin?**
`uv` 0.4.19 or newer and `git` on the `PATH`, a TypeSafe API key for the tools that send, and the
GitHub CLI `gh` only to triage a GitHub Actions run by its URL. See [install.md](install.md#1-what-you-need).

## Cost and the API key

**What does it cost?**
Fractions of a cent per item: a spec-drift check after editing two files of a real Java project
cost $0.0013, a CI failure about $0.0002, a code audit of Django (1,535 rule/code checks) $0.09.
Unchanged requests are answered from a local cache and cost nothing. The fast model is rarely where
the money goes: your agent's own investigation of what it flags costs far more, so the skills keep
that proportionate. Every check has a free preview that shows the estimate first.

**Which tools cost money?**
Only the five that send: `check_spec_drift`, `triage_ci_failure`, `check_code_rules`,
`check_doc_claims` and `check_change_claims`. The other ten (drafting and validating maps,
previews, recording verdicts) are free, send nothing and need no key.

**Where does my API key go, and why will the agent not take it in chat?**
The MCP server holds it, so the agent never sees it. In Claude Code you set it with
`/plugin configure jevmcp@jev`; anywhere else you run the server's `--set-key` in your own
terminal, which stores it in `~/.config/jevmcp/typesafe.env` (mode 0600). An agent must never ask
for the key, accept it in chat or put it in a command, and `--set-key` refuses to run where it
cannot ask you without echoing. See [install.md](install.md#5-the-api-key).

**How do I check the key is found without spending anything?**
Run the server with `--show-key-source`: it lists every place it looks, marks the one it would use
and never prints the key. A free `validate_spec_map` call proves the install, but says nothing
about the key.

**Does it read my project's `.env`?**
The MCP server never does, so a cloned repository cannot supply a key. The spec-drift command line,
`spec_drift.py`, reads a `TYPESAFE_API_KEY=` line from the `.env` of the folder it is run in; the CI
triage and code-audit scripts never do.

## What leaves the machine

**What is sent to TypeSafe?**
Four kinds of data, each only by the tool that needs it: spec sentences with the code paired with
them (spec drift); CI log excerpts with an excerpt of the change (CI triage); units of source code
(code audit and doc claims); a change's description with its hunks (change claims). A request
carries at most 2,600 characters of code, never a whole repository; secrets, private keys, email
addresses and home folders are redacted first. Exactly what is sent, and what never is, is in
[PRIVACY.md](../PRIVACY.md); every preview shows the real requests.

**Why does the agent ask my consent again for a different check?**
Consent is per kind of data and per project: agreeing to send spec sentences does not cover CI logs
or source code. For CI logs, source code and changes, only you, in the conversation, can agree; a
file in the repository never counts as consent for those.

**Is anything stored on my machine?**
Earlier answers, in `~/.cache/jevmcp/verdicts.json`, so an unchanged request is not paid for twice.
It holds digests, never your code. The maps (`spec_map.json`, `rule_map.json`) and the code-audit
verdicts you record belong to your project and are committed with it.

## Reading the results

**What do the labels mean?**
A confident problem is **DRIFT** (spec drift), **CHANGE** (CI triage), **BREAKS** (code audit),
**STALE** (doc claims) or **UNSUPPORTED** (change claims): investigate each. **review**: Jev leans
one way but is not sure; read from the most likely down. **ok**: Jev is sure there is no problem;
spot-check a couple. **vague**: the doc or sentence is too general to compare. **n/a**: the rule is
not about that code. **not checked**: TypeSafe did not answer.

**Is `??` a pass?**
No. It means what was sent cannot settle the question, and such items often hold real problems. In
spec drift the fix is almost always in the map: pair the claim with the code that enforces it.
Neither `n/a`, "nothing to check", "nothing to audit" nor an incomplete run is a pass either.

**TypeSafe could not be reached. What now?**
Say the check did not run. The tools mark the run incomplete and the command-line scripts exit with
code 3; never report a pass from either. jevmcp is advisory: do not make a Jev check a required
merge gate.

**Why did the same claim get a different answer the second time?**
Jev's answer can change between identical calls; on one Java project it did for 32% of claims. So a
claim the first answer does not settle is asked up to twice more, and is decided only when every
answer agrees and none is below 0.85 confidence; otherwise it stays `review`.

**Can I use it in CI?**
Yes, through the command-line scripts, with the exit codes **0** nothing found · **1** at least one
DRIFT, CHANGE or BREAKS · **2** setup or map problem · **3** TypeSafe unavailable. Fail the job on 2;
do not block on 3. `spec_drift.py --map spec_map.json --dry-run --strict` checks the map for free
and is safe as a required step. See [how-to.md](how-to.md#6-running-it-in-ci).

## Setting a project up

**Do I write `spec_map.json` or `rule_map.json` by hand?**
No. `draft_spec_map` and `draft_rule_map` write them; you and the agent review every entry, and only
reviewed entries are ever sent. A draft tool never overwrites a file. See
[how-to.md](how-to.md#1-set-a-project-up-from-nothing) and [recipe 12](how-to.md#12-set-up-code-audit).

**Which languages does it understand?**
Named functions and classes in Python, Java, JavaScript and TypeScript (and OpenAPI files); any
other language by line range. Specs are read sentence by sentence in English and other
Latin-alphabet languages, Chinese, Japanese and Korean; other scripts a paragraph at a time, and
Thai, Lao, Khmer and Tibetan mostly not. See [the plugin README](../README.md#languages).

**The code moved and the map points at the wrong lines. What do I do?**
Run `spec_drift.py --map spec_map.json --update-lines` (free), then `validate_spec_map`, which lists
moved and stale entries. See [recipe 5](how-to.md#5-keeping-the-map-honest-when-code-or-spec-moves).

## Doc claims and change claims

**Do these need a map?**
No. Doc claims reads the docstrings, comments above functions and test names of the units your
change touches; change claims reads the description you pass, or the commit messages. Both are MCP
tools only, with a free preview each. See [recipes 14 and 15](how-to.md#14-check-docstrings-comments-and-test-names-against-the-code).

**Doc claims flagged a docstring that is right.**
Expected now and then: on 60 held-out cases it flagged 27 of 30 stale claims and 5 of 30 accurate
ones. Read the unit and decide; a docstring that only leaves details out is not stale.

**Change claims called a true sentence UNSUPPORTED.**
Read the change before you trust it. Each file a sentence names gets a share of 2,600 characters,
and only the whole hunks that fit are sent, without a note that the rest was left out, so on a large
change the hunk that proves the sentence may not have been sent. A sentence about process ("tested
on Windows", "faster") is nothing hunks can show. Change claims was measured on short one-file
changes only; real multi-file pull requests are not measured.

## CI triage

**Why does it never say a failure was not caused by my change?**
By design. A real regression blamed on the environment would be retried away and shipped, so
"not the change" is never decided for you: those failures go to `review`, with Jev's lean (the
environment, a dependency, a flaky test) for the agent to check.

**Does it work with CI other than GitHub Actions?**
Yes, from log files and JUnit reports saved in the project. A GitHub Actions run can also be read
by its URL with your own `gh` login, for a repository the project has as a GitHub remote.

## Codex

**Codex asks before every check that sends. Is that right?**
Yes. The sending tools are declared write actions because data leaves the machine, so Codex asks
each time, and that approval is your consent for the call. The free tools can be allowed to run
without asking; see [install.md](install.md#9-troubleshooting).

**A check in a Codex session came back clean suspiciously fast.**
If it ran the command line inside Codex's sandbox, it reached nothing: that sandbox has no network.
Use the MCP tools, which run outside it, and never report a pass from a run that could not reach
TypeSafe.

## Updates and support

**Which version is current, and what changed?**
The first lines of the [repository README](https://github.com/eaisdevelopment/jevmcp#readme) name
the current release; the [CHANGELOG](../CHANGELOG.md) lists every release with how it was measured.

**How do I update?**
Claude Code: `claude plugin update jevmcp@jev`, then restart. Codex: `codex plugin marketplace
upgrade`, then remove and add `jevmcp@jev` again. Your key and your maps are not touched. See
[install.md](install.md#7-updating).

**Where do I ask something not answered here, or report a bug?**
Questions: the [Q&A discussions](https://github.com/eaisdevelopment/jevmcp/discussions/categories/q-a), where an answer can be marked as the answer. Bugs:
[GitHub Issues](https://github.com/eaisdevelopment/jevmcp/issues). Security problems: see
[SECURITY.md](https://github.com/eaisdevelopment/jevmcp/blob/main/SECURITY.md).
