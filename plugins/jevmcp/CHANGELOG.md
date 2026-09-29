# Changelog

## 1.7.7 — 2026-10-01

**Found by running jevmcp on its own code.** Every tool of 1.7.6 was run on jevmcp itself: a full
spec-drift check of its own tool reference and privacy notes (565 claims: DRIFT 3, review 349, ?? 119,
ok 94), a triage of its only failed CI run and of four staged failures with known causes, and a code audit
with the rules in its repository and with six engineering rules written for the test. Every flagged item
was judged by an AI agent reading the code, and every "this is wrong" verdict was re-checked by a second
agent told to refute it. TypeSafe spend for all of it: about $0.21. This release fixes what that found.

**Windows, and text in any language.** In 1.7.6, 23 reads and writes of text files, two `os.fdopen`
calls and several `git` calls used the system's code page, which is cp1252 on Windows. Under it,
`draft_rule_map` on a rule with Cyrillic or Chinese text failed with `UnicodeEncodeError` and left an
empty `rule_map.json` behind, so the next draft said the map already existed, while a rule with a
typographic quote, a dash or an accent was written in cp1252; a UTF-8 rule map made on Linux or macOS
failed to load; source code and git diffs with non-ASCII text were sent garbled; and the three command
lines crashed printing to a pipe. Now every file the tools read or write, and every `git` and `gh`
output, is UTF-8; each command line prints UTF-8 whatever the console's code page and never crashes on
the text it prints (a console set to another code page may show non-ASCII text garbled; only part of a
file name that is not UTF-8 becomes `?`); a key file, or the `.env` that `spec_drift.py` reads, is read
when saved as UTF-8 with a byte-order mark or as UTF-16 (Notepad's "Unicode", `>` in Windows PowerShell
5.1), where 1.7.6 said it held no key, and so is a rule file saved as UTF-16, from which 1.7.6 drafted no
rule, and a CI log or JUnit report saved as UTF-16, which 1.7.6 misread; a map that is not UTF-8 is
refused with a message that says so; a rule file whose name is not UTF-8, which a map cannot record, is
refused when named, and left out with a warning when found or inside a named folder, in a git
repository too (1.7.6 recorded it there under a name no file has); in a project folder whose name is
not UTF-8, the results and previews come back, under a file name with `_` for what is not UTF-8 (1.7.6
failed with `UnicodeEncodeError`, the three tools that send only after sending); and a map write that
fails leaves no file behind, from the tools and the command lines alike. Where the system's file names
are not UTF-8 (on Linux, the C locale with Python's UTF-8 mode off, or an 8-bit locale), Python names
files in the locale's encoding while git, the maps and the arguments name them in UTF-8, so a file with a
non-ASCII name (`订单.py`, `docs/спец.md`, `ci/журнал.log`) was not found, left out of an audit without a
word, misnamed or failed the tool. There the server and the three command lines now start themselves
again once, in Python's UTF-8 mode, with the same command line, Python's own options included, before
they read anything, and such a file is read under its own name; macOS, Windows and a Python already in UTF-8 mode are left as they are. The cost is under an
8-bit locale: a file whose name was saved in that locale's own encoding (`café.py` under Latin-1 or
cp1252) is then not found, or fails the tool. Rename such a file in UTF-8, or turn the restart off,
which brings the old problem back for names in UTF-8: `JEVMCP_NO_UTF8_RESTART=1` in the environment
the server or the command line starts with (for the server, the shell that starts Claude Code; Codex
passes its server only a minimal environment, so under Codex it reaches only the command lines), or
`python -X utf8=0` for a command line started with `python`.
The Linux, macOS and Windows smoke job now uses Cyrillic, Chinese and typographic quotes and a CI log
named in Cyrillic. It runs a second time in the C locale on Linux and macOS: on macOS that run checks,
as the Windows run does in cp1252, that every file is read and written as UTF-8; on Linux the server
restarts itself there, so that run checks the restart.

**Upgrading on Windows.** A rule map that 1.7.6 or earlier drafted on Windows with a typographic quote, a
dash or an accent in it is in that system's code page (cp1252 on Western European Windows), which 1.7.7
does not read. On that system the message names the code page, shows the map's first line that is not
plain ASCII read in it, from 60 characters before its first such character to 60 after, and, if that is
as written, gives a one-line `uv run --no-project --quiet python -c "..."` command that converts the
map to UTF-8, once: through uv, which jevmcp already needs, since a bare `python` is often missing on
Windows or is the Microsoft Store's stub. The command takes the map's path as its argument, in forward
slashes, so it also runs in bash, the shell Claude Code uses on Windows; a path a shell would change
(one with a `"`, a `$` or a backtick) gets the Python statement instead. Then check that its rules read as
written, and never re-save it from an editor that opened it as UTF-8, which loses every character it
could not read. A rule map that does not read as text in this system's code page (read on Linux or
macOS, or written on a Windows with another code page, Cyrillic or Greek) gets no command, since which
code page it is in cannot be told, and one converted from the wrong one loads with every rule garbled:
convert it on the system that wrote it, or with its code page named. A spec map is handled the same
way.

**Secret redaction closes the gaps PRIVACY.md did not admit.** Sent as written in 1.7.6, now redacted (the
rules for code apply to the units a code audit sends and to the change a CI triage sends too):
- in code, Go's `password := "..."` and `var password string = "..."`, and a string type declared before
  the `=` where a declaration or a parameter starts: a type whose name ends in `str` or `string`
  (`password: str = "..."`, `Optional[str]`, `SecretStr`, `const token: string = "..."`,
  `let token: &str = "..."`, Kotlin's and Swift's `String`). A value of any other type
  (`password: HashStrategy = "bcrypt"`), and the next value on a line after a `case` label, an `if`, or
  a secret word inside a quoted value that no `:` or `=` follows, are not taken for one. A quoted text
  that ends in a secret word and `:` or `=` (`label="Password:" placeholder="..."`) still has what follows
  it redacted up to the next quote, as in 1.7.6. Also in code: a value with a string prefix
  (`b"..."`, `u"..."`, C#'s `@"..."`, `r"..."` unless it holds `\`, `(` or `[`, which make it a
  pattern, and `f"..."` unless it holds `{`), a C array (`char password[] = "..."`,
  `char pass[64]`) or a table element whose subscript is a number or an upper-case name
  (`TokenName[1] = "..."`), and a one-word value holding one quote of the other kind (`"p'ssw0rd"`);
- in configuration files, a `.properties` key and value separated by spaces (`db.password hunter2`), every
  line of a YAML block value (`password: |`) or of a `.properties` value continued with a backslash, a
  value that starts with `|` or `>` but is not a YAML block header (`password=>Xk9q`, `token: |abc`),
  and a quoted key (`"password": ...`). A line that continues a `.properties` value is read as a setting
  of its own only in the `key=value` or `key: value` form, so `password=...` on the next line of a JDBC
  URL is still redacted, as in 1.7.6, a placeholder's default there too, while words there (`password to
  continue`) are not taken for a setting (one that continues a key, after `db.\`, is read in every
  form), and a line with nothing to redact is sent exactly as written;
- a default written into a placeholder (`${DB_PASSWORD:hunter2}`, `${DB_PASSWORD:-hunter2}`, and the
  shell's and Docker Compose's `${DB_PASSWORD-hunter2}` and `${DB_PASSWORD=hunter2}` after an upper-case
  name, though not in a JavaScript template string, where `${A-B}` is code), after an editor variable's
  name too (Log4j2's `${env:DB_PASSWORD:-hunter2}`, the Serverless Framework's
  `${env:DB_PASSWORD, 'hunter2'}`), and text glued to one (`${PREFIX}hunter2`), from four characters, as
  for a quoted value, in configuration files and in a quoted secret value in code. `${DB_PASSWORD}`
  itself, GitHub Actions expressions (`${{ ... }}`), an editor variable's name (`${env:TOKEN}`) and the
  message of `${1:?message}` are kept, as before, and so is a path in or after a placeholder that names
  a folder or a file (`${WORK_DIR}/token.json`, `${KEY_FILE:-/etc/app/key.pem}`);
- a spec-map entry pointing at `.netrc`, `.npmrc`, `.pypirc`, `.git-credentials`, `*.env` (`prod.env`),
  `kubeconfig`, a Terraform state or variable file, `credentials*.json` or a service-account JSON file is
  refused, as CI triage already refused all of them but `*.env` and code audit never read them. A
  spec map and a code audit refuse them whatever the case of the name (`.ENV`, `ID_RSA`,
  `server.PEM`), since on a disk that ignores case (macOS's default) `.ENV` opens `.env`; CI triage
  matches the names in lower case, as 1.7.6 did. CI triage
  now leaves `*.env` files out of the change it sends too (1.7.6 sent a `prod.env` hunk, its secret-looking
  values redacted). Python stub files (`.pyi`) lose their comments and docstrings, as `.py` files do.

What these rules change in what is sent, and that existing spec maps send what they sent otherwise, was
measured offline over public repositories, the test corpora and the maintainers' own projects: see
*Measured on this release's code* below.

**An answer that could not be asked again is never a pass.** A claim or rule the first answer does not
settle is asked up to twice more (a CI failure is asked once). In 1.7.6 a failed extra answer was
dropped, the remaining answers decided the label, and the run still reported `complete` and exit 0; the
code audit with jevmcp's own rule found this. Credits running out while asking again gave exit 2 (a setup
problem) instead of 3. Now an item is decided by agreement only when every answer came back. When asking
again fails, the item keeps its first answer's label and why, with `samples` 1 (that answer alone
decided it), gets a `note`, the failure is listed, and the run is not complete (exit 3,
`complete: false`); and credits running out at any point is exit 3.
Every reply, in all three tools, is now read once before it is used: each question asked has an answer,
a choice is one of the options offered, its confidence and probabilities are numbers, and a score is a
number. A reply without answers, or one that fails this (a confidence of null, a choice that was not
offered), is an API error for that item, first or asked again: never a pass, never a crash of the run
(in 1.7.6 a confident spec-drift answer with a choice it was not offered read as `ok`); a token count
that is missing or is not a number counts 0. Such an answer
is never kept in the cache of answers, and one an earlier version kept is not replayed: the next run
asks again. After a cancellation, a rejected key or credits running out, no new request starts;
requests already in flight finish. In 1.7.6 a rejected key or used-up credits still sent every
remaining claim, rule or failure once: 40 of 40 in a test that asks four at a time, now at most four.

**Spec drift: the reply is a reading plan, and `??` is read, not excluded.**
- **The reply is capped.** One full check returned 462,896 characters, about 115,000 tokens, into the
  agent's context. The reply now lists every DRIFT, then `review` from P(drifted) 0.3 up grouped by the code
  each claim pairs with (one group is one place to open), then `??` counted by reason, and counts of the
  rest, cut to fit; everything is in the results file. New structured fields: `flagged_total`,
  `to_read`, `review_groups`, `unverifiable_by_reason`, `map_health.entries_to_fix_total`. The most
  likely place is cut to fit what the DRIFT rows leave rather than dropped whole, and `flagged` and its
  schema say so. The list of places is cut to fit too, never below the places the reply lists with
  their claims; when it stops short, the text says how far it goes ("lists the first K of N places")
  and that the rest are only in the results file. What was not checked is listed in the text up to
  20 lines, and in full in `not_checked`. An error reply (TypeSafe rejected the key, or no claim was
  answered) has no structured fields, so its text points only at files: one that lists every claim
  not checked (1.7.6 listed every one in the text) and, when claims were left out, one that lists
  every place to read; the error replies of `triage_ci_failure` and `check_code_rules` name the
  results file alone for the rest. Credits running out part way (HTTP 402) give no error reply, in
  all three tools: the reply keeps its structured fields, with `complete: false` and a line in
  `not_checked` saying the run, or the re-asking, stopped early.
- **Each `??` claim gets its own reasons.** `map_health` found a `??` result's claim by its spec line
  alone, and one line often holds several claims (322 of the 644 claims of jevmcp's own map, as it was
  measured): each got the reasons and pairing suggestion of the line's last claim, and was counted under
  that claim's reason. With every claim of that map taken as `??`, 118 were wrong. The MCP tool and the
  command line now work each out from its own claim, in `map_health`, in the results file and in the
  count by reason.
- **The skill no longer says "about ten is usually plenty".** On the self-check, the ten highest-P
  `review` items held 2 of the 28 real problems; the rest were spread across the list. The agent now reads
  group by group and says how far it got: "read N of G groups / K of R claims".
- **Sentences about what the code does not do, and lead-ins, are kept.** `validate_spec_map`, the dry run
  and the skill told users to exclude them, because they tend to come back `??`. On the self-check, such
  claims held 18 of the 28 real problems. They are now kept and paired with the code that enforces them.
- **A partly superseded document is not flagged as old** (`Part of this spec is superseded by ADR-9`,
  `Section 3 of this spec has been superseded`, `This document has been superseded in part`), as the docs
  already said. In `This spec is superseded ...` only words that limit the declaration to a part count,
  so `This spec is superseded by ADR-12, part of the platform set` is still flagged, as in 1.7.6; in
  `This spec was later (since, eventually) superseded ...` any `part`, `partly`, `mostly` or `largely`
  later in the sentence keeps it from being flagged, as in 1.7.6.
- `--changed` stops with a message when git takes more than 60 s, reads file names with spaces or
  accents correctly, and, run from a folder inside a repository, finds new files where they are (1.7.6
  looked for them at the top of the repository, so their claims were silently left out).

**CI triage: facts from before the failure, and facts about time.** Thresholds are unchanged; the state
sent changed (`ci-state-3`), so a preview made by 1.7.6 must be made again.
- **No facts from the future.** "The same job passed on the default branch" came from the latest run there,
  which for jevmcp's own failed run was made five hours later and already held the fix; for a scheduled or
  manual run, the change was diffed against a newer green run, which could state "no code changed". Both now
  use only runs made before the failed one, a note names that run, and the change is "not known" rather
  than empty when the green run tested a newer commit. When the default branch's recent runs all tested
  the failed run's own commit (a nightly run with no new commit), the note says so, rather than that
  there was no earlier run. Both runs are now the branch's own: GitHub lists a pull request's runs under
  its head branch's name, so a fork's pull request from its own `main` could be taken for the default
  branch's record ("likely pre-existing") or for the last green run, whose commit the change was then
  diffed against. Pull-request runs and forks' runs are skipped, up to 20 runs are read from each list,
  and when all of them are skipped the note says so and the record, or the change, is not known. And
  each failure is told how its own job ended there: 1.7.6 decided it for the whole run, so when `lint`
  had already failed on the default branch, a `test` job that passed there was told it "also failed"
  and given "likely pre-existing". A job that run did not have is not known, and a failure shared by
  several jobs (a matrix) reads "also failed" when any of them failed there.
- **New facts:** how long the failed step ran and its longest silence; that GitHub reports the job as
  cancelled, or as stopped at its time limit (read from the job's annotations, a new GET request); that the
  step was still running when the job was cancelled; and the other jobs of the matrix where the same step
  passed. jevmcp's own Windows hang is now described as a 14 min 50 s step, silent for 14 min 49 s, stopped
  at the 15-minute limit, that passed in 0-1 s on Linux and macOS. GitHub's record outweighs the log: for
  a job it reports as failed, neither a time limit printed in the log nor "The operation was canceled" is
  taken; nor is a time limit printed in the log when the job's annotations were read and name none
  (GitHub names it there when the limit stopped the job); a time limit is taken only when the job's
  run fits it (not more than a minute short of it, nor more than ten minutes past it by the end of the
  failed step), and a job GitHub reports as timed out is still said to have timed out; and in a log
  only the runner's own `##[error]` line says the step was still running (a .NET program prints the
  same words). When GitHub reports the job as cancelled but its record of the failed step says the step
  failed (a later step, `if: always()` or a debug session, ran on until the cancel or the time limit),
  the facts name the failed step and its exit code and say "GitHub reports the job as cancelled later;
  its record says this step had already failed.", never that it did not finish, a time limit or a
  hang; an action that fails with only an `##[error]` line and no exit code keeps its own error
  line and run time, not the later step's. A step whose start was cut off with the head of a log
  longer than 25 MB takes its run time from GitHub's record of the step. A line with no timestamp of
  its own (the rest of a multi-line `with:` input) no longer costs the next line of the same second
  its time: a step then had no run time, or one that read 0 s for a 15-minute hang.
- **A name or message the change adds or removes.** When an error line offered to the model contains a
  name in code (6 characters or more, snake_case, camelCase or dotted) or 12 characters or more of a
  string's text that the change adds or removes, a fact says so: "Line L4 contains `place_order`, which
  this change removes in src/orders.py". At most three, taken from the change's redacted lines (never
  comments or secret files), common names and file names skipped (`json_schema.py:808` is not the name
  `json_schema`), and never read by the gate. In a staged case with 1.7.7's first facts, a test calling a
  renamed tool fell from P(change) 0.92 to 0.71 once "None of the files the errors name is edited by this
  change" was said, and a rewritten message read as "environment" at 0.91, though in both the error lines
  held words the change wrote.
- **Better error lines:** the innermost frame of a Python traceback in the project's own code, with its
  source line; a bare exception name (`KeyboardInterrupt`); `Caused by:` lines. Code under the runner's
  own `_actions`, `_temp` and `_tool` folders beside the workspace (an action's own script, a Python or
  Node installed there) is not the project's: its path is kept whole, and it is neither that frame nor
  one of the files the errors name. `FAILED` counts only in capitals and never inside a file name such
  as `failed.log`; lower-case "failed" only in the shapes errors take. The runner's post-job cleanup is
  no longer counted as the failed step's output.
- **Jobs whose logs were not read are not sent.** 1.7.6 sent a placeholder for each and labelled it,
  although the note said they were not covered. Now nothing is sent for them, and `jobs_not_checked`
  names them in the preview, the triage and `triage.json`.
- **Next steps that fit what is known.** `??` names only the evidence that is really missing: not a JUnit
  report given with the log, and the failed step's whole output only for the job or file whose own log was
  cut. There is no `gh run rerun` for a log from a file. "If it fails again, treat it as the change's"
  became "run the same job on the base commit, with the user's approval". For a lean to the
  environment or a flaky test whose root error line says a command or a file is missing, when no
  later attempt of the same commit passed, the next step says a re-run tells nothing, and to check
  that the job installs the command, or to find what should create the file (the job or the code
  under test); another line of the step that names a missing file does not count. A command is
  missing on a shell's `command not found` or `sh: 1: x: not found` (also
  `/bin/sh: eval: line 9: x: not found`), Windows' `is not recognized as an internal or external
  command` and PowerShell's `is not recognized as the name of a cmdlet` (`a name` in newer
  versions, GitHub's default Windows shell among them), which 1.7.6 never offered as an error line, or
  `executable file not found`; a bare `Not Found` (an HTTP 404, a Docker image, a file missing from
  Docker's build context) gets the re-run advice. A job stopped at its time limit reads as a likely
  hang. A lean to the change below the gate says "leans to the change at 0.88 (CHANGE needs 0.905)"
  instead of showing a P(change) above the gate, and only when the confidence held it back, not the
  kind of cause. When the two answers disagree (not the change, but a kind of cause that is the
  change's), `why` and the triage's text say so instead of "leans away from the change". For a GitHub
  run whose test step names no test, `??` asks for the JUnit report saved as a file with the log, since
  a run takes no report.
- **Logs from any CI:** a log with no step markers is named `(whole log)`, not `(setup)`; paths inside the
  project folder become relative, so the facts can name the project's files; apt's and uv's "Failed to
  fetch" are install failures (a browser test's `TypeError: Failed to fetch` is not); a log cut at 25 MB
  says so; the workspace folders of Travis CI, GitLab's shell executor, Buildkite and TeamCity are
  removed, and GitLab's `/builds/` no longer cuts the middle out of other paths. A log or JUnit report
  saved as UTF-16 with a byte-order mark (`>` and `Out-File` in Windows PowerShell 5.1) is read as
  UTF-16; 1.7.6 read a log as UTF-8, losing its steps, its exit code and its non-ASCII text.
- **Cancelled jobs are named.** On a GitHub run, a job cancelled next to a failed one is now named in a
  note (1.7.6 said nothing of them there): as cancelled after the failure (fail-fast) when it belongs to
  the failed job's matrix and ended between 5 seconds before and 5 minutes after a failed job of it,
  otherwise with how long it ran and no cause, since GitHub also cancels a job that reaches its time
  limit. So a job of a matrix without fail-fast, stopped at its time limit minutes after another job
  failed (the shape of jevmcp's own smoke job), is not called fail-fast. On the 73-run corpus, all 100
  cancelled jobs in a failed job's matrix ended 0-105 s after it.
- What this changes in the states sent was measured offline on a corpus of 73 real runs: see *Measured
  on this release's code* below.

**Code audit: setting up a rule map finds the rules.** Which files the drafter reads, which sentences it
takes and how it flags them are still guesses from names and wording: every entry is reviewed with the
user before anything is checked.
- **The rule-file finder takes agent files by their exact names**, capitals included (`CLAUDE.md`,
  `CLAUDE.local.md`, `AGENTS.md`, `AGENTS.override.md`). In 1.7.6 it took any file whose name started with
  `claude` or `agents`, in any capitals: on jevmcp, a user how-to gave 184 of the 204 drafted sentences,
  and an SDK's `docs/agents.md`, a page about its `Agent` class, was read as rules. Other rule files are
  found by a rule word in their own name, as a word of its own (`python-style-guide.md` and
  `coding-conventions.md`, which 1.7.6 missed, and camel-case names such as `ContributingGuide.md`,
  `CodeStyle.md` and `JSStyleGuide.md`), never by a word elsewhere in a docs path; an extensionless
  `CONTRIBUTING` is found. `validate_rule_map` lists other documents named after an agent
  (`claude_notes.md`, `docs/agents.md`) as `candidate_rule_files`, for the user to name if they hold
  rules; when `draft_rule_map` finds no rule file at all, its error names them instead (`Claude.md`),
  while the command line writes a map with no entries.
- **Rules written as facts are drafted.** "Every call to `subprocess.run` passes `stdin`." — the form the
  review step asks for — was dropped for having no "must"; sentences of that form are now rules. A file
  the user names keeps every sentence, list items and lines that look like code included (one with no
  rule wording is flagged `descriptive`). Some Chinese, Japanese and Korean rule words (必须, 必ず, 해야,
  ...) count.
- **Drafted rules read as written.** A numbered list item no longer becomes a fragment "<heading>: 1."
  plus the item without its heading, and bold and bold-italic marks are taken out of the rule text
  (`**must not**`, `you ***must not*** delete`, `_**must not**_`, `__*must not*__`), in Chinese,
  Japanese and Korean text too (`__*...*__` there only with a space on each side): 1.7.6's draft of
  jevmcp had 24 such fragments and 65 entries with stray `**`. A Python splat inside a sentence
  (`**kwargs`, `f(**opts)`), at its end too, and a mask of stars (`显示为***，`, `sk-***,`, `"***"`)
  are not taken for marks. A few shapes can still lose or leave a mark, so the review step reads
  the text: an item that opens with an italic word keeps one, a splat that opens a sentence
  (`**kwargs must not be logged`) loses its `**`, and a mask that ends the rule's text with no stop
  after it (`print as sk-***`) loses its stars, all as in 1.7.6; a mask written between two
  letters with no space (`用户名***和密码***`) is taken for bold-italic, and a lone two-star mask
  right after a letter or a digit (`显示为**，`; `12**,`, which 1.7.6 kept) for the closing mark of a
  bold span. A
  comment in a reStructuredText code block no longer heads the rules below it, and an RST `#.` list
  item, which 1.7.6 took for a heading, is read as a numbered item. Spec drift's own sentence reading is
  unchanged.
- **New flags:** `conduct`: a rule addressed to the assistant starts excluded ("Never ask the user for the
  key", "The assistant must get the user's consent before it sends code"), while a rule about the code
  is usually drafted even when it names the user or consent ("The CLI must never ask the user for the
  key"; one that opens with "Without consent," starts excluded whatever its subject, and so does one
  that says "in the conversation" with no subject such as "the server must" before it, even as part
  of its own subject: "Every message in the conversation must be persisted ...", which 1.7.6
  drafted);
  `conditional` ("When X, ...": one such rule gave 22 false flags and nothing real; `validate_rule_map`
  now suggests a trigger the code shows instead); and `descriptive`. `tests-only` is added to a rule
  about test code ("Don't add tests that only check a mock"), and no longer to one whose words show that
  it asks for tests of other code ("Every bug fix adds a regression test") or lets tests off ("except in
  tests"), nor to one with words about production code, CI or build logs, jobs or runs, or test
  output, results, runs, reports or steps, which a rule about test code can have too ("Test runs must
  be hermetic: tests must not touch the network."); other wordings of the first two ("New features
  must include tests") still get it, and the skill says to check it on every entry, both ways.
- **A long definition is cut between statements.** A unit longer than 2,600 characters was cut into
  windows at any line, even inside a call: a `subprocess.run(...)` and a `write_text(...)` whose last
  arguments fell into the next window were flagged for leaving them out, the only two false flags of the
  precise engineering rules in the self-check. A window now ends where a statement does (no bracket open,
  no line continued with a backslash, no method chain going on: `.x`, `?.x`, `->x`); inside a statement
  only when the window holds no such place, or the statement would not fit in the next one.
- **The changed scope finds the changed files.** A changed file whose name holds a space, an accent, a
  quote or a backslash, every changed file when git is set to print other prefixes (`diff.noprefix`,
  `diff.mnemonicPrefix`), and every changed tracked file of a project that is a folder of its git
  repository (a package of a monorepo) were silently left out of the audit of the change, as in 1.7.6;
  each is now audited under its real name. A change outside the project's folder is not audited.
- `draft_rule_map`'s "from N file(s)" and its `sources` count each rule file read once: `AGENTS.md`
  linked to `CLAUDE.md` is one file (1.7.6 counted two), and a file git lists that is gone from disk is
  not counted. `validate_rule_map` no longer lists such a link as a rule file the map does not use.
- **Existing rule maps send what they sent**, except for the windows of definitions longer than 2,600
  characters, units where the new secret redaction for code, listed under *Secret redaction* above,
  applies (a secret declared with a string type or with Go's `:=`, a value with a string prefix such as
  `b"..."` or C#'s `@"..."`, a C array or a table element with a number or an upper-case subscript
  (`TokenName[1] = "..."`), a one-word value holding one quote of the other kind, at its end too
  (`"hunter22'"`), and a default of, or text glued to, a `${...}` placeholder in a quoted secret value,
  a JavaScript template string's too), and `.pyi` units, which now lose their comments and docstrings as
  `.py` units do. That, the draft of jevmcp's own rules and the drafter's recall on three projects were
  measured offline: see *Measured on this release's code* below.

**Documentation.** The self-check found 37 sentences of `PRIVACY.md` and `docs/tools.md` that the code
contradicted or that said more than the code does: limits and field lists (`not_checked`, `flagged`,
`root_error`, the preview's `failures` and `questions`), the labels' agreement path, which runners' paths
are removed, which timestamps are removed, what is read from GitHub, what a map entry may point at, when
the dry run exits 2, how units are split, and more. Each is now true of the code. jevmcp's own spec map
pairs 42 more claims with the code that shows them, excludes 3 sentences that state nothing checkable,
maps every new sentence of this release, and its line ranges point at the code they were reviewed
against. Every 1.7.7 change is documented in `PRIVACY.md`, `docs/tools.md`, `docs/how-to.md`,
`docs/install.md` and the three skills.

**Deliberately not changed.**
- The fixed questions, their options, the thresholds and the model: they are measured. CI triage's
  "environment" option still names "a job that was cancelled or timed out", so a hang can lean
  "environment"; the new facts and next steps address it, and the option changes only after it is measured
  on a set of hangs.
- Spec drift's sentence reading: existing maps and their `--strict` CI depend on it. Rule drafting was fixed
  inside code audit only, so a `~~~` fence or an indented code block in a spec is still read as prose (the
  docs now say so).
- Improvements that are not bug fixes wait for a later release: a per-rule trigger pre-filter, a ledger of
  decided items, a pairing-repair tool, aiming the code excerpt by the claim's words, showing edited code
  before and after, and re-asking only items whose answer could still change.
- `check_spec_drift` still does not report spec sentences that are not in the map; `validate_spec_map` and
  the command line do, and the docs now say so.
- Redaction still removes the text after a quoted label that ends in a secret word and `:` or `=`, up to
  the next quote (`"Token: " + token + " refreshed"`), as 1.7.6 did: refusing a value that starts with a
  space or a `+` would send real secrets (`password = " hunter22"`). And a `.properties` value whose `=`
  is on the line after its key (`db.password\` then `=hunter2`) is sent as written, as in 1.7.6, and
  so are a triple-quoted string (`"""..."""`) and a value that holds the other kind of quote along
  with a space (`"it's a secret"`): `PRIVACY.md` lists what is sent as written.
- In a brace language an object literal spread over lines can still be cut inside when a window ends in
  it: there `{` also opens a block, inside which statements must be cut.

**How it was tested.**
- **Every behaviour change has a test**, and the new tests were also run against the 1.7.6 code, where most
  of them fail, as they should. The encoding tests run the command lines and the server under an ASCII
  locale, and the server under cp1252 too, started so that the UTF-8 restart does not happen: they
  test how text is read and written, and other tests run the restart and the switch that turns it off.
- **Offline comparisons of what is sent**, before and after, for every family (below). Nothing was sent.

**Measured on this release's code.** Offline and with nothing sent, 1.7.6 against 1.7.7:
- **Secret redaction.** The states sent for jevmcp's own map (565 claims) and for the Java project's
  earlier map (115 claims) are byte-identical to 1.7.6's. Over 645,278 text files — 19 public
  repositories (React, Next.js, Vue, Svelte, Angular, Go, Kotlin, Swift, Rust, Ruby and Java code, HTML
  templates included), the test corpora and the maintainers' own projects — the new rules for code change
  1,207 lines, 119 of them distinct, each line compared whole. 94 are secrets, development defaults or
  test fixtures' secrets now redacted (`admin_password: str = "..."`, Go's `password := "testpassword"`,
  Python's `private_key_pem=b"..."`, a default such as `CHANGE-ME-IN-PRODUCTION`). 25 are not secrets but
  the value of a name that holds a secret word: written with a type, with Go's `:=` or with a string
  prefix (`token_type: str = "bearer"`, `password_prompt_absent = b"Enter dashboard password:"`), which
  1.7.6 already redacted when written without one (`token_type = "bearer"`); text glued to a placeholder
  in a JavaScript template string (`${AUTH0_ISSUER}oauth/token`); and, on one line of a compiled bundle,
  the 12 names of a token table set through a numbered subscript (`TokenName[1]="Boolean"`). None is an
  HTML or JSX attribute, a `case` label or a statement. In 6,591 configuration files, 194 lines change,
  nearly all of them secrets written as placeholder defaults (the rule for a value that starts with
  `|` or `>` finds none there). No line is redacted less than in 1.7.6.
- **Spec drift's reply**, for the real results of the 1.7.6 self-check: 74,328 characters instead of
  462,896 (-84%); its `review` claims from P(drifted) 0.3 up are 203 claims in 95 places.
- **CI triage**, on the 73-run corpus: every state changed; the requests went from 107 to 108 (jobs
  merged only because their outputs ended in the same post-job line are now apart, and two jobs whose logs
  share apt's first error are now one); all 108 states now say how long the step ran, and 12 name jobs
  where the same step passed; reading a multi-line `with:` input's lines right gave 11 states the step's
  run time and corrected it by a second in 3. The fact about the change's own words is in 21 of the 108
  states: it is said in 16 of the 49 runs the change caused and in 1 of the 24 it did not (answer keys
  read only to count this, after the rules were written).
- **Code audit.** On jevmcp, 1.7.6 drafted 204 entries (181 to review) from two files; 1.7.7 drafts 18
  (7 to review) from `AGENTS.md`, with no fragment and no stray bold mark, the how-to named too. On
  Django, Vite and rust-analyzer the drafter still finds 95 of the 101 rules their reviewers wrote, with
  831 entries to read instead of 797. The states of the 126 corpus pairs are byte-identical. On jevmcp's
  own code with the six engineering rules, 2,988 of 3,522 states are identical to 1.7.6's (498 of 587
  units keep their lines, and none of them sends anything else); windows that start inside a statement
  went from 48 to 19, all inside 8 statements longer than a window, and calls split across two units
  from 1 of 21 to 0.
- **jevmcp's own spec map** has 919 entries, 734 of them checked claims.

**Measured with TypeSafe on candidates of this release** (about $0.26 in all):
- **CI triage**, on the 73-run corpus graded as for 1.7.0, with the code before the last review round's
  fixes: on the held-out runs (52 graded, from 8 repositories), CHANGE was right 8 times out of 8 (1.7.6:
  6 of 6), with no false alarm and no failure the change caused passed as not the change; the lean
  pointed the right way on 45 of 50 (1.7.6: 43 of 47). On the dev runs, CHANGE was right 5 of 5 (1.7.6:
  4 of 4). Those fixes change what is sent for one of the 108 states, measured offline: a held-out run
  whose change ran `apt` on a Windows runner now offers PowerShell's missing-command line as its error
  line. It was then review, leaning to the change at P(change) 0.87, and was not sent again. The five
  runs of jevmcp below send exactly what they sent then. jevmcp's own failed run, the Windows job
  stopped at its time limit, went from `??` leaning environment at P(change) 0.16 to review at P(change)
  0.44, still leaning environment, now with `KeyboardInterrupt` as its root line and "Looks like a hang"
  as its next step. Of four staged failures of jevmcp's smoke test, the two the environment caused lean
  environment; a renamed tool leans "update the test" at 0.80, below the 0.905 that CHANGE needs
  (P(change) 0.87); and a changed error message is still read as environment (P(change) 0.04), because
  the log never says what the test expected.
- **Spec drift**, a full check of jevmcp's own map as it was then (704 claims), with an earlier
  candidate's code: DRIFT 4, review 494, `??` 101, ok 105, for $0.098 in 122 s of checking. The 4 DRIFT
  claims were read against the code and are accurate: the model is wrong on them. The reply is 77,429
  characters (1.7.6: 462,896).
- **Code audit** of jevmcp's own code, with an earlier candidate's code: with the six engineering rules,
  none of the 27 violations 1.7.6 had was left (an AST check finds none in this release's code either),
  and every item to read was a false alarm, 20 of the 22 from the one conditional rule, the kind
  `validate_rule_map` now warns about. With the rule from `AGENTS.md`, the re-ask bug it found was
  fixed, and none of the ten items it ranked highest broke the rule.
- **Tests:** 1,115 automated tests (one is skipped unless a file owned by another user exists). The change
  was reviewed by independent agents in repeated rounds, each finding re-checked by a second agent told to
  refute it. What the last round still found in this release's changes, and what 1.7.6 already did that
  this release leaves for later, is listed below.

**Known issues** (to be fixed in a later release). Found in this release's own changes by the last review
round:
- **CI triage, an action that failed on its own** keeps its own lines and run time (see above) only when
  the job's time limit is in GitHub's annotation alone. When the log also prints the limit line
  (`##[error]The job has exceeded the maximum execution time of ...`), the failed step gets the limit line
  instead of its own error and the later step's run time and silence, next to "its record says this step
  had already failed".
- **CI triage, cancelled jobs of a matrix.** Triaging a cancelled job by its own URL calls a sibling of
  its matrix that its own time limit stopped "cancelled after the failure (fail-fast)". A matrix whose
  jobs set their own `name:` (no `base (values)` names) is not seen as one matrix: its fail-fast cancels
  get the neutral note that suggests passing a job's own URL, and no fact says whether the same step
  passed in the other jobs of its matrix.
- **Rule-map drafting, stars.** A Python splat that ends a sentence (`must accept **kwargs.`) still loses
  its `**` when the next sentence of the paragraph has a `**` of its own (a power `x**2`, a mask such as
  `sk-***`), and that one is lost too; "at its end too" above holds only without one. A mask written with
  separators (`***-***-1234`, `192.168.***.***`, `***@***.com`, `10.0.**.**`) is taken for bold and loses
  its stars. 1.7.6 kept all of these as written.
- **A run stopped by TypeSafe.** Requests go out several at a time (`jobs`). When the key is rejected or
  the credits run out, the answers already received for items later in order are dropped: they are
  missing from the results, the count and the cost, though TypeSafe answered them. When the stop hits the
  first item in order, every answer is dropped and the reply is an error reply ("checked 0", $0),
  although the paragraph on HTTP 402 above says credits running out part way give no error reply.

Also in 1.7.6:
- **Secrets still sent as written:** a commented-out setting in a config file (`# password: ...`); a YAML
  secret on the lines below its key without `|` or `>` (a list under `api_keys:`, or a plain value on the
  next line); the lines after `password = """` in a TOML multi-line string; a password inside a JDBC URL or
  a connection string (`?password=...`, `Password=...;`); a declaration typed `Final`, `ClassVar` or `Any`
  (`SECRET_KEY: Final = "..."`); C and C++ `L"..."` and `u8"..."` strings and C#'s `$"..."`.
- **CI triage on Windows** reads a log file under `.git\` or a secret file in a subfolder
  (`deploy\id_rsa`, `ci\.npmrc`), which it refuses on Linux and macOS: its guard compares the backslash
  path with `/` patterns.
- **Maps:** a spec or rule map saved as UTF-8 with a byte-order mark is refused as invalid JSON. Save it
  without the mark.
- **File names that are not valid UTF-8:** a code file with such a name, paired with a claim or holding
  a draft's suggested code, makes spec drift fail with an internal error (on the command line, a
  traceback and exit 1, which reads as "at least one DRIFT").
- **Git in another language:** outside a git repository, when git prints its messages in another
  language, `draft_rule_map` and `draft_spec_map` stop with "git could not list this project's files".
- **Rule-map drafting** does not find Claude Code's `.claude/rules/*.md` or Cline's `.clinerules/`: name
  such a file to draft from it. On Windows, a rule from an `AGENTS.md` or `CLAUDE.md` two or more folders
  deep gets a scope with a backslash, which matches no file on Linux or macOS.
- **CI triage** names no project file and offers no traceback frame from a container job's workspace
  (`/__w/<repo>/<repo>/`) or a self-hosted runner's (`.../_work/<repo>/<repo>/`), and it takes Azure
  Pipelines' `_tasks` folder for the workspace, so a task's own script is named as a project file. Jobs
  that failed at different steps with the same first error are merged and told "2 jobs failed at this
  step", with one step's name and run time.
- **Spec drift:** two map entries with the same sentence and the same code share their answers, so one
  can be decided on two independent answers instead of three.
- **Reply size:** during an outage, `check_code_rules`' error reply lists every request that was not
  checked, and `check_spec_drift`'s map problems are listed in full (a map broken by a rename can give a
  reply of over 250,000 characters).
- **`check_spec_drift`'s output schema** describes `complete` as "every selected claim was checked", but it
  is also false when every claim was checked and only a re-ask failed or a map entry was unusable.

## 1.7.6 — 2026-09-28

**Documentation only.** No code changed; every tool behaves exactly as in 1.7.5.

- `docs/install.md`: on Windows, the `--set-key` command needs the full path of the script, and the note
  now gives the folder for both clients (`.codex\plugins\cache\jev\jevmcp\` for Codex,
  `.claude\plugins\cache\jev\jevmcp\` for Claude Code). It named only the Codex folder, under a block
  that also gives the Claude Code command. A comment there still called Claude Code's key field a
  "prompt".

Found by a fourth review round on the whole 1.7.5 change, which found nothing else. 1.7.6 was
released only after a further review round on this change found nothing.

## 1.7.5 — 2026-09-28

**The server works on Windows, the free tools work without a key, and a missing git is explained.**
Found by installing 1.7.4 from GitHub into an empty environment and calling every tool, and then by
starting the server on Linux, macOS and Windows in CI.

- **Windows: the server no longer freezes.** Every `git` and `gh` command the tools run inherited the
  server's standard input, which is the MCP connection itself. On Windows the first tool that ran git
  (drafting a rule map, a routine check, CI triage) never returned. Child processes now get an empty
  input, and a test keeps it that way.
- **Windows: a `git.exe` or `gh.exe` inside a project is never run.** Windows looks for a program in the
  current folder before PATH, and tools run with the project as the current folder. git and gh are now
  looked up in the absolute PATH folders only, never in the current folder, and run by the path found
  (a link such as snap's `gh` keeps its own name).
- **A new CI job starts the server on Linux, macOS and Windows** on every change, exactly as a client
  does and from an empty uv cache, runs the seven free tools, and checks that the three that send
  refuse without a key. The three that send have been run with a real key on Linux only; the docs say
  so.
- **Claude Code: the seven free tools work without a key.** The key option was marked required, and
  Claude Code then does not start the plugin's server at all until a key is set, so the free tools
  were missing too. It is now optional: the `/plugin` screen still shows the field; left empty, the
  free tools work and the three that send say that no key is set. Set the key any time with
  `/plugin configure jevmcp@jev` (the docs and the no-key message said `/plugin manage`).
- **An unfilled placeholder is not a key.** A `TYPESAFE_API_KEY` that still reads
  `${user_config.typesafe_api_key}` is treated as no key: it is never sent, and it no longer hides a
  key stored with `--set-key`.
- **git is a stated requirement, and its absence is explained.** Without git on the server's PATH, a
  routine check, a code audit, and CI triage with `base` or a run URL failed with
  `FileNotFoundError: No such file or directory (git)`. They now say that git is missing and what to
  do instead (name the files for a spec check; triage a saved log without `base`). The spec list no longer calls a
  committed spec "not committed" when git cannot be run: its last commit is reported as unknown, and
  `committed` is null.
- **A code audit of a git project without git reads no code.** Without git, which files git ignores (a
  local `.env`, build output, credentials) cannot be told, and 1.7.4 then read every file on disk.
  Every code-audit tool now stops there and says so; a folder that is not a git repository is read as
  before. PRIVACY.md says both.
- **uv 0.4.19 or newer is stated.** An older uv stops with `error: unexpected argument '--script'
  found`, and neither client shows that message; the troubleshooting table in `docs/install.md` now
  lists what each client shows instead.
- **Smaller fixes.**
  - A CI log whose `##[group]Run` header is never closed (a hand-saved or cut log) no longer reads as
    "the step printed nothing". The 73 real runs of the CI scoring corpus are read exactly as before.
  - `draft_spec_map` no longer ends with a command-line hint that had no program name.
  - The server makes its private folder again if something deletes it while it runs, such as a temp
    cleaner, and never reuses a folder someone else put back at the old path (a link, another user's
    folder, or a folder with other permissions).

**How it was tested.**
- **390 tests** (363 in 1.7.4), including every missing-git path, the placeholder key, the unclosed
  log group, a git planted in the current folder, a private folder put back by someone else, and a
  check that no child process can read the server's input.
- **The new CI job** passed on Linux, macOS and Windows.
- **A clean-room install** of the candidate into an empty environment: Claude Code starts the server
  with no key set, the seven free tools work, the three that send refuse and name
  `/plugin configure jevmcp@jev`, a placeholder key falls through to the stored key, and every
  missing-git path gives its message.
- **Three adversarial review rounds** (code, docs, safety, and the clean-room run), each finding
  re-checked by a skeptic, the later rounds on the earlier rounds' fixes: 31 findings, 25 confirmed and
  fixed (2 of them the same problem found twice), 6 refuted. The last round found no code defect.

## 1.7.4 — 2026-09-26

**Documentation only: three published errors corrected.** No code changed; every tool behaves exactly
as in 1.7.3.

- **1.7.0, CI triage.** Of the 27 change-caused held-out runs that CHANGE did not catch, 26 went to
  review and 1 came back `??`. The entry said all 27 went to review.
- **1.7.3, blind labels.** The Chinese, Japanese and Korean gold labels were written by an AI agent told
  to read as a native-level reader, with no access to the tool. The entry said native-level readers
  wrote them.
- **The Java project's cost figures** (3 s and $0.0013 after editing two files, 11 s and $0.006 for a
  full check) were measured on 2026-09-22, before 1.6.0, when each claim was asked once. The README,
  `docs/tools.md` and both how-to pages now say so: since 1.6.0 a claim the first answer does not
  settle is asked up to twice more, so a first check costs more.

Both CHANGELOG entries and their release notes keep the corrected sentence with a dated note of what
it used to say.

Also: the repository's front page now says what each result label means, what a check costs, how well
each tool did on real repositories, what Jev and the service cannot do, the known gaps, and how
releases are tested.

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
- **Blind labels.** An AI agent, told to read as a native-level reader and given no access to the tool,
  labelled the sentences of 440 real paragraphs in English, Japanese, Chinese and Korean. (Corrected on
  2026-09-26: this said the labels came from native-level readers.) The splitter was tuned on the Kubernetes set
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
  change-caused runs; of the other 27, 26 go to review, where the agent decides, and 1 came back ??.
  (Corrected on 2026-09-26: this said all 27 went to review.)
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
