# Changelog

## 1.7.3 — 2026-09-25

**Chinese, Japanese and Korean specs are read sentence by sentence.** 1.7.2 read them as if they were
English. A Japanese or Chinese sentence has no spaces, so it counted as one word and the five-word
minimum dropped it; a paragraph was never split at 。！？; Korean, which has spaces but no capital
letters, was never split at all. On real specs with their code, a Japanese spec (YaneuraOu) gave 49
map entries and now gives 199, a Chinese one (brpc) 14 and now 149, and a Korean one (smtm) 93
paragraph-sized entries and now 97 sentences. Now:

- **A sentence ends where a reader ends it.** At 。！？, and at a Latin `.`, `!` or `?` followed by a
  space (`…です. 次は`, `…다. kubelet은`) - never inside brackets, quotes or a code span, never after a
  colon (`(예: 5)`, `` `Unknown`: 诊断失败 ``), never in a name (`SDKMAN!`, `e.g.`, `A vs. B`), a decimal
  (`３．５秒`) or a dotted name with no space (`主版本号.次版本号.修订号`, `ファイル名.拡張子`). A bracket that
  holds a whole sentence ends one (`（…。）次の文`); a quote, which is as often a message inside a sentence
  (`「保存しました。」などのメッセージ`), does not. A table row stays one entry with all its cells: a `。` in a
  description cell no longer cuts off the default value after it. A hard-wrapped Chinese or Japanese line
  joins with no space, and a wrapped list item or definition joins with its own text.
- **Length is measured for each script.** About one and a half Han characters, two and a half hiragana
  or four katakana make a word; punctuation next to them is not a word (`运行以下命令:` is as short as
  `运行以下命令：`); a Chinese, Japanese or Korean sentence that ends with a full stop needs three words
  instead of five. Short rules such as `必须以字母数字开头` and `` `.spec.schedule` 필드는 필수이다. `` are kept;
  katakana labels (`ライフサイクルフック`), link-only lines and questions (`准备好了吗？`) are dropped, as their
  English originals are.
- **Code names next to CJK text are found.** `MAX_SIZEは30日` names `MAX_SIZE` and 30; before, the
  Japanese character hid both.
- **Re-wrapping a CJK spec is not a change.** When a map is checked, a space next to a Chinese or
  Japanese character does not count, decided once for the whole spec file, so moving a line break next to
  a Latin word or a number (`場合は` / `HTTPステータス`) no longer reports the entry as changed. Inside a code
  span the space is part of a literal and does count: `` `YYYY年MM月DD日 HH:mm` `` becoming
  `` `YYYY年MM月DD日HH:mm` `` is reported. A drafted `spec_text` writes such a space as `␣`.
- **Maps drafted by 1.7.2 keep working.** Their entries still match the spec, including their
  `spec_text`. Sentences 1.7.2 never extracted are now reported as not in the map, so a strict check of an
  existing Chinese or Japanese map lists them: decide each one, as the skill says. A sentence that 1.7.2
  cut in two at a colon, with both halves decided, counts as covered.
- **Everything else is read exactly as before.** Text with no Chinese, Japanese or Korean letter - with
  full-width punctuation, `・`, accented capitals (`ÜBERFÄLLIG`) or any other script - gives the same
  sentences, the same names, the same payload and the same map results as 1.7.2.
- **A lead-in ending in the full-width colon `：`** is flagged as likely `??`, as one ending in `:` is.
- **The languages that are still not read properly are named** - in `docs/tools.md`, both READMEs, the
  plugin description and the skill, which now tells the user before drafting. Specs in Cyrillic
  (Russian, Ukrainian, Bulgarian, Serbian, Mongolian), Greek, Arabic, Persian, Hebrew, Hindi and the other
  Indic scripts, Georgian, Armenian, Amharic and Burmese are not split into sentences: each paragraph or
  list item is one entry. Thai, Lao, Khmer and Tibetan write no spaces between words, so most of their
  sentences are dropped as too short. In Turkish, Czech, Slovak, Polish or Swedish a sentence that starts
  with a capital outside A-Z (`Č`, `İ`) stays joined to the one before it. This is how 1.7.2 read them
  too; it was measured on the 38 translations of the SemVer specification (sentences kept against the
  English original: 0.34-0.72 for the first group, 0.86-0.95 for Turkish, Czech, Slovak, Slovenian and Swedish) and on Wikipedia text (a
  lone Thai, Lao or Tibetan sentence is never kept, a Khmer one 23% of the time). The docs give the
  workarounds: one requirement per list item, or entries added by hand.

**How it was tested.**
- **Blind labels.** Native-level readers labelled the sentences of 440 real paragraphs in English,
  Japanese, Chinese and Korean, with no access to the tool. The splitter was tuned on the Kubernetes set
  (280 paragraphs) and then scored once on the held-out set (160 paragraphs from Vue, ShardingSphere,
  RocketMQ and the Rust RFC translations; the expectations were written down first):

  | held-out | sentences found, 1.7.2 → now | of the tool's, right | statements kept | fragments dropped |
  |---|---|---|---|---|
  | Japanese | 0.19 → 0.93 | 0.38 → 0.94 | 15/102 → 102/102 | 21/21 → 18/21 |
  | Chinese | 0.28 → 0.93 | 0.49 → 0.95 | 38/82 → 81/82 | 17/20 → 13/20 |
  | Korean | 0.53 → 1.00 | 0.64 → 0.96 | 37/39 → 39/39 | 8/14 → 8/14 |

  Every pass bar was met except one: "at least as good as 1.7.2 on every number" fails on fragments
  dropped for Japanese and Chinese, because 1.7.2 dropped nearly every sentence. The fragments kept are
  images, links, front matter and label lines, which the review excludes; English keeps the same kinds.
- **Nothing else changed.** 3,265 documents and 918,107 lines with no CJK letter (spec repositories in
  many languages, Kubernetes, Vue, RocketMQ, ShardingSphere and brpc English docs) give identical
  sentences, names and index; 2,472 map validations and line updates on English specs, before and after
  edits, give identical results.
- **Maps on CJK specs.** On 1,079 Chinese, Japanese and Korean documents (65,615 drafted entries):
  1,047 re-wraps reported nothing; 1,079 CJK edits and 1,026 edits to a Latin word or number inside CJK
  text were all reported, each on the right entry.
- **Three adversarial review rounds**, each finding re-run by a skeptic: 43 findings, 30 confirmed and
  fixed, 13 refuted.
- **A live check** of 19 hand-paired Korean requirements from smtm ($0.0020): 5 ok, 12 review, 1 DRIFT,
  1 ??. The DRIFT came from a pairing that left out the code passing the value in; the known rename in
  that spec (`LlmOperator`, now `SystemOperator`) came back ??, which is reported as not a pass.
- **4 real Claude Code sessions** on the installed plugin, each asked to set up spec-drift checking for
  a real project: ginza (Japanese spec, Python), smtm (Korean, Python), DataX mysqlreader (Chinese spec
  and a Chinese prompt, Java) and a Russian spec. Each agent passed exactly the spec named and drafted
  whole-sentence entries (46, 97 and 100); the Chinese session answered in Chinese; the Russian session
  told the user that Russian is read a paragraph at a time and suggested one requirement per list item.
- **363 tests** (335 in 1.7.2).

## 1.7.2 — 2026-09-24

**What you name is what is checked.** 1.7.1 second-guessed the spec you named. A folder that held
several versions of a spec, or a file that looked like an old copy, was refused, and a named file got
warnings from its name or its commit dates. So `specification/v3` was refused because its folder's name
has a version number, and a one-character typo fix in `specification/v3/` made the tool call
`specification/final/` "an older version". Now:

- **A named file or folder is used exactly as named.** Nothing is refused, left out or flagged for its
  name, its date or what its top says. A folder gives every `.md` and `.rst` file on disk in it and below
  it; templates are no longer left out. Name `specification/final` and only `final` is used; name
  `specification` and all of it is. A path is refused only when it cannot be used: missing, outside the
  project, a folder with no `.md` or `.rst` file, or a named file whose name is not valid UTF-8.
- **Nothing in a named folder is dropped without a word** (this was already wrong in 1.7.1). A folder
  lost files silently whenever git listed at least one other file there: a git-ignored file next to a
  tracked one, a tracked file under a folder named like build output (`reqs/target/`), a symbolic link.
  Now every tracked file is used wherever it is; git-ignored files are used with a warning that in a fresh
  clone or CI their entries are problems (commit them, or leave them out); a skipped folder (`node_modules`,
  `build`, ...) that holds other spec files, a link that leads out of the project, to a folder or nowhere,
  and a file that cannot be read are named in a warning. When git cannot list the project at all
  ("dubious ownership" in a CI container, a corrupt index), every file is used and the warning quotes git
  in full, instead of refusing the folder. A named link keeps its own name in the map (`latest.md`,
  `current/`, not what it leads to), so the map follows the link when it is repointed. Naming a skipped
  folder or a link's target too stops its warning. An empty path, or one inside a folder that cannot be
  entered, is refused with a plain message instead of a traceback.
- **A named folder stays the source.** The map's `specs` records what was named, a folder as a folder.
  Before, a folder was frozen into its file list: a spec file added to it later was never checked and
  the strict check still passed. Now its sentences are reported as not in the map, and a spec file it
  holds that the check does not reach (in a skipped folder, behind a link) is named in a new `warnings`
  field of `validate_spec_map`, `preview_spec_check` and `check_spec_drift` every time. A named path that
  is gone, or a `specs` that is not a list of paths, is a problem.
- **A fresh draft covers every sentence** (already wrong before 1.7.2). The drafter skipped a sentence with
  no word in the Latin alphabet, which the strict check then reported as missing: a Russian or Japanese
  spec failed the strict check before anyone had edited its map. Every sentence now gets an entry, and an
  entry the drafter could suggest no code for is reported once ("has no code"), not also as missing.
- **The check uses the spec the map records.** A spec that says at its top that it is superseded no longer
  makes `validate_spec_map` report the map as not ready, and `check_spec_drift` and `spec_drift.py --map`
  no longer refuse it; a newer-looking version next to it is no longer a warning; `preview_spec_check` no
  longer shows the `OUTDATED SPEC` and `SPEC VERSIONS` blocks. The `spec_versions` output field is gone. A map's
  `confirmed_current` list is no longer needed and is ignored; maps that have it still load.
- **The candidate list stays, for when nothing is named.** `draft_spec_map` without `docs`
  (`--find-specs`) still lists every file that looks like a spec, with its last commit date and hints
  about old copies, and says which of several versions looks newest. It now says that these are hints to
  help the user choose, not a decision. Files whose names are not in the Latin alphabet (`требования.md`,
  `要件定義.md`) are no longer grouped as versions of one document, and a project folder that an enclosing
  repository ignores is listed instead of "no file looks like a spec".
- **The skill tells the agent to pass what the user named, a folder included, without listing candidates
  first.** 1.7.1's skill covered only named files, so when a user said "use the docs/spec folder" the agent
  listed candidates instead, and the folder path was never exercised in a real session.
- **A map written inside a folder link gets a warning.** `current/spec_map.json`, with `current/` a link to
  `specification/final/`, really lands in `specification/final/` and stays there when the link is
  repointed. `draft_spec_map` and `--draft-map` now say so, and the skill writes the map outside the link.

**How it was tested.**
- **335 tests** (321 in 1.7.1), including the layout that started this: `specification/v1`, `v2`, `v3` and
  `final`, with `v3` edited after `final`.
- **38 real agent sessions** on the installed plugin, 27 in Claude Code and 11 in Codex. Cases: a folder named,
  a file named, the parent folder named, nothing named, the `v3` folder named while `final` is newer (1.7.1
  refused this), a check of a spec whose top says "Superseded" (1.7.1 refused this), a file added later to a
  named folder, a git-ignored file in a named folder, a skipped folder with a spec in it, a folder link.
  Every session used exactly what the user named, or listed the candidates and asked when nothing was named.
  One Codex session wrote its map inside a folder link, which led to the warning above; both clients then
  wrote it outside.
- **Three rounds of independent review**, each finding re-checked by a second reviewer who tried to refute
  it: 39 findings confirmed (14, 17 and 8) and all fixed; 1 refuted; 2 left without a verdict, both
  repeats of confirmed findings, reproduced and fixed.
- **Real open-source repositories**: named folders in OpenAPI (`versions/`, 23 files), rust-lang/rfcs (651),
  python/peps (761 files, 95,977 map entries, validated in 11 s), GraphQL, JSON Schema, semver, CloudEvents,
  OpenTelemetry and ADR collections gave exactly the files `find` lists, with no warning on an unmodified
  repository. The slowest run was `--find-specs` on the full PEPs history: 25 s.

## 1.7.1 — 2026-09-24

**Spec drift now knows which spec is the current one.** A project can hold several spec documents, or
several historical versions of one spec. Before, a folder given to `draft_spec_map` was read whole, so a
`specs/` folder with `v1.md`, `v2.md` and an `archive/` put obsolete requirements into the map, and nothing
said so later. Now:

- **`draft_spec_map` without `docs` drafts nothing.** It lists every file that looks like a spec, with its
  last commit date. It flags any that look like an old copy (a version number or date in the name, a folder
  such as `archive/` or `old/`, a history word, or a line near the top that says it is superseded,
  deprecated, withdrawn or reverted), and groups the files that look like versions of one document, with the
  newest named. The agent shows this list and asks the user which file(s) are current. Command line:
  `spec_drift.py --find-specs`.
- **A folder that holds old copies or several versions of one spec is refused**, with the files and the
  reasons listed, and the files nothing flags named. Nothing is written. A file the user names is always
  used, with a warning if it looks old or a newer version exists.
- **Staleness is checked on every run.**
  - If a spec the map checks says near its top that it is superseded or out of date, the map is not ready:
    `validate_spec_map` reports a problem, `check_spec_drift` sends nothing, and the command line exits 2.
  - If the line is about something else and the user confirms the spec is current, the map's new
    `confirmed_current` list turns it into a warning.
  - If a newer version of a mapped spec appears, every check, validate and preview warns, and names both files.
- The map records the spec files it was drafted from (`specs`).

**Tested on real repositories before release:** OpenAPI-Specification (`versions/` holds 12 versions of one
spec: all but the newest flagged, and 3.2.1 chosen as newest), rust-lang/rfcs (numbered RFCs are not treated
as versions of each other; withdrawn and superseded RFCs are caught), python/peps (102 superseded or withdrawn
PEPs flagged, 0 wrongly), the GraphQL and JSON Schema specs, and ADR collections (superseded, reverted ADRs).
That testing found, and 1.7.1 fixes:
- a regular expression that took about 10 minutes on a Sphinx title underline;
- hard-wrapped prose ("replaced by terminal characters.") that wrongly blocked the real GraphQL spec;
- 19 files wrongly called old copies by their name alone.

**Map upkeep.**
- `validate_spec_map` reports how many entries' sentences moved to another line.
- `spec_drift.py --update-lines` rewrites only those line numbers.
- `preview_spec_check` finds an entry by its stored or its current line.
- Entries that share a line are listed once among the likely `??`.

**CI triage.**
- A job log is read a piece at a time, and only its end is kept.
- Reading stops at a total budget across jobs. A triage that could not read every job's log says so and
  reports `complete: false`.
- The skill now tells the agent two things. When a run of another repository is refused, stop: do not read
  that run another way. Without the user's yes to send, stop after the free preview, show what would be sent
  and the cost, and ask. Real Claude Code sessions on 1.7.0 did neither.

**Also fixed.**
- Non-UTF-8 file names no longer stop the server.
- A spec checked from another folder is found for the staleness check.
- `codex exec` behaviour is documented for Codex 0.156.1: the free, read-only tools run, and only the tools
  that send need approval.
- `--log` and `--junit` say they must be inside `--src`.

## 1.7.0 — 2026-09-23

**Two new tool families, in the same plugin and on the same server: CI failure triage and code
audit.** One install, one key, one skill per family. The server now holds ten tools.

**CI failure triage** — what actually broke in a failed CI run? `preview_ci_triage` (free) reads a
GitHub Actions run, job or pull-request URL of the project's own repository with the user's own
`gh` login, or log files and JUnit reports from any CI, and shows exactly what would be sent.
`triage_ci_failure` sends it: Jev reads each distinct failure — facts computed in code, the
candidate error lines, the end of the failed step's output and an excerpt of the change under
test — and says whether the change caused it. Labels: **CHANGE** (the change broke it; when the
lean is "update the test", the agent must confirm with the user before editing any assertion),
**review** (sorted by P(caused by the change), with a lean: environment, dependency, flaky, change)
and **??** (not a pass). "Not the change" is never decided automatically: a real regression
blamed on the environment gets retried away and shipped, and no corpus is large enough yet to show
that mistake is rare enough. Command line: `scripts/ci_triage.py`, exit codes 0/1/2/3.

**Code audit** — does the code break the project's own written rules? `draft_rule_map` collects
the rule sentences from the project's CLAUDE.md, AGENTS.md, CONTRIBUTING and style guides into
`rule_map.json`; the agent reviews every entry with the user, rewriting each into one positive
condition with the files it covers. `check_code_rules` then asks about one reviewed rule and one
unit of code at a time — never one broad "does this follow our conventions?" question. Labels:
**BREAKS**, **review** (sorted by P(breaks); read from 0.3 up), **??**, **ok** and **n/a** (the
rule is not about that unit, and P(breaks) is below 0.3). By default only the units the change
touches are audited. `validate_rule_map` and `preview_code_audit` are free. Command line: `scripts/code_audit.py`, exit codes 0/1/2/3.

**Measured on real projects before release, not on examples.** Everything below comes from popular
open-source repositories. We split them by repository: tuning used only the development set, and each
held-out set was scored once. The exception: the first CI held-out run was invalid, because the parser
did not know the job-log headers those logs used and read none of them. We fixed the parser only
and ran it again. Intervals are 95%, from resampling whole repositories.

*CI triage.* We collected 73 real failed GitHub Actions runs from 13 repositories: Flask, Werkzeug,
Click, cli/cli, Gin, Pydantic, FastAPI, Express, Fastify, Vite, Tokio, Commons Lang and Django. They
cover Python, Go, JavaScript/TypeScript, Rust and Java. Each run's answer key comes from what happened
next: the fix commit, or a re-run of the same commit that passed. A second reviewer then derived each
key again, blind. Of the 73 keys, 71 were confirmed and 2 disputed; the disputed ones are left out.

Results on the 52 held-out runs (8 repositories, 33 caused by the change):
- **CHANGE was right 6 times out of 6, with 0 false alarms.** CHANGE fires on 6 of the 33
  change-caused runs; the other 27 go to review, where the agent decides.
- **The lean pointed the right way on 43 of 47 runs** (86–98%). Always blaming the change would be
  right on 33 of 52.
- **P(caused by the change) ranks change-caused failures above the rest with AUC 0.98** (0.94–1.0).
- **The root error line was right on 26 of 41 runs.** Taking the first error-looking line was right
  on 21 of 44.
- **Cost: about $0.0002 per failure.**

A second gate that also fires when the error names a file the change edits was set down in advance.
It fired 17 times with 1 false alarm. Its precision's lower bound was 0.73, below the 0.80 we set
beforehand, so it was rejected and the gate above ships.

Robustness, on the development runs:
- **Asking the same question 20 times with the cache off gave the same verdict every time** on 15 of
  15 failures.
- **Fabricated benign text in the log never produced a false CHANGE.** We tested three kinds: a
  "passed on retry" line, a fake network reset, and a fake traceback into a file the change did not
  touch. But the text can move the lean: the "passed on retry" line turned 2 of 14 change-caused
  failures towards "flaky". The lean is an opinion, not evidence.
- **Without the change, or with only the last 25 lines of the log, every failure came back ??**
  (14 of 14). The tool says it cannot tell rather than guessing.
- **Logs from another CI, with no GitHub markers, gave the same lean** on 17 of 19 runs, and no
  false CHANGE. The 4 automatic CHANGE labels became review.
- **A 35 MB log is read in about 12 s.**

*Code audit.* We tested 123 rule/code pairs from 8 repositories: Django, Vite, scikit-learn, Airflow,
Spring Boot, Grafana, Tokio and Codex. Each rule is quoted from the project's own files. The code
either broke the rule (a maintainer's review comment, or a one-line mutation of real code) or kept
it (the fix, or clean code). A second reviewer confirmed each label blind.

Results on the 91 held-out pairs (6 repositories):
- **BREAKS was right 13 times out of 13; 0 of 44 compliant pairs were called BREAKS.**
- **The list to read (BREAKS, plus review from P(breaks) 0.3) held 35 of 47 real violations**
  (62–83%). It also held 12 of the 44 compliant pairs.
- **One violation was called ok.**

Two changes were made after the held-out set showed a gap, so these held-out numbers are not blind:
- n/a now needs P(breaks) below 0.3. Before, it hid 12 of the 47 violations.
- The review list is read from P(breaks) 0.3 up.

**The blind check came after these changes, on real code.** We drafted each project's rule map from
its own docs and reviewed it. We then audited the code touched by recent merged commits: Django (30
commits), rust-analyzer (10) and Vite (60). A reviewer who never saw the tool's labels judged every
BREAKS and a random sample of every other label.
- **BREAKS was confirmed 26 times out of 29 decided,** with 3 false BREAKS in 171 changed units.
  All 21 in Django were real. The 3 false ones: one came from a rule written without its condition
  ("Import X from Y", applied to a file that never uses X), and two were rules applied to code that
  lacks their subject.
- **The review list is where the noise is.** In the random samples of review from P(breaks) 0.3, a
  real violation was found in:
  - Django: 1 of 40 (it was the highest-ranked);
  - Vite: 0 of 19;
  - rust-analyzer: 9 of 40.
- **In rust-analyzer, about 1 in 8 of the lower-P(breaks) reviews was a real violation.** That is
  why "stop when the items stop being informative" is a judgement, not a rule.
- **No ok or n/a sample held a violation** (0 of 68).
- **The drafter now offers 94% of the code rules reviewers found** in those three projects, up from
  67%. This is measured on the projects that showed the gaps. Reviewers read about 20% more entries.
- **Cost: $0.09 for Django's 1,535 checks.**

**What each family sends, and how it is kept to that.** Each kind of data needs its own consent,
and for CI logs and source code only the user in the conversation can give it — never a file in
the repository.

- CI triage reads GitHub with GET requests only, only for a GitHub remote of the project, with
  prompts off, without the TypeSafe key in `gh`'s environment, and with `gh`'s cache in the
  server's private folder. A run URL is parsed strictly, and a `base` ref can never be read as a
  git option.
- Log lines are cleaned before they are sent or shown: timestamps, colour codes, control and
  invisible characters, runner paths, home folders and email addresses removed, and secrets
  redacted — the existing shapes (now also GitLab, npm, PyPI, Slack-webhook and Vault tokens) plus
  authorization headers, login passwords, `.netrc` lines and any `name=value` whose name says it
  is a secret.
- The change under test leaves out secret files (only their name is mentioned, paths with spaces
  or quoting included) and comment-only lines. jevmcp never adds the commit message or the pull
  request's text: an author's own description of a change steers a verdict about it. A CI step
  that prints them puts them in its log like any other line.
- Log files are read only inside the project or the server's private inbox (a 0700 folder
  removed with the server); links, `.git`, secret files, other users' files and other sessions'
  temporary folders are refused.
- `preview_ci_triage` returns a snapshot, and `triage_ci_failure` with that snapshot sends exactly
  what was previewed.
- Code audit reads only files git tracks or would commit — never ignored files — and never links,
  secret files or files over 1.5 MB. Comments are removed, except for rules about comments, which
  are asked in requests of their own with links and email addresses removed.
- `preview_code_audit` reports the units, files, bytes of code and their share of the project. An
  audit of more than 400 requests, or of the whole project, is refused until `confirm_units`
  repeats the count.
- Log text and code in any result are data: the skills tell the agent never to follow an
  instruction found in them, and a fork's pull request is marked `trusted: false`.

**Server.** Results are kept per family, so a triage never overwrites the last spec-drift check.
One rate limit covers every tool that sends. Every new tool declares all four annotation hints and
a complete output schema. Arguments are checked against the full input schema (enums, patterns,
lengths, ranges, list sizes) before a tool runs. A git or `gh` failure, and an answer from GitHub
that cannot be read, now come back as a tool error the agent can act on, never as a protocol
error. The server's instructions were rewritten for three families, with the key and consent
rules first.

**Also better for spec drift.** Two sessions saving the answer cache at the same time no longer
drop each other's answers. Secret redaction no longer slows to a crawl on long lines: a 2.6 MB log
took 55 s, and now takes 2 s, with the same output on 1.4 million real log lines. Comments are no
longer found inside Rust raw strings (`r#"..."#`) or multi-line strings. `gh` and `git` are never
run from a relative PATH entry such as `.`.

**Documentation.** Every page covers the new tools: arguments, output, labels, exit codes, costs
and errors in `docs/tools.md`, recipes in `docs/how-to.md`, and what each family sends in
`PRIVACY.md`. The repository's own spec map now also pairs the new PRIVACY.md and tools.md
sentences with the code in `ci_triage.py`, `code_audit.py` and the server, and five references
that pointed at line ranges — which had drifted onto unrelated code — now name symbols.
`claude_how_to_jevmcp.md` and `codex_how_to_jevmcp.md` are generated by a script from the shipped
plugin, so their quoted text and hashes can no longer go stale.

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
