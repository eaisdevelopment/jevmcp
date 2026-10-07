# Changelog

## 1.7.9 — 2026-10-08

**The known issues and older gaps of 1.7.8, fixed.** The 1.7.8 entry below ends with three known
issues and a list of older gaps; each is fixed here, except where *Not fixed* says otherwise. The
fixed questions, their options, the thresholds, the model and spec drift's sentence reading are
unchanged.

**Secret redaction** (spec drift; the rules for code also apply to code audit's units and CI
triage's lines):
- The shell's `PWD=` with an absolute path (`ENV HOME=/home/you PWD=/home/you`, `"PWD=/srv/app"`;
  a path that starts with `/`, `~/`, `X:\`, `X:/` or a UNC `\\` and holds only letters, digits and
  `_.-~/\@+%,`) is sent as written again, as in 1.7.7, except right after a `;`, where it
  is read as ODBC's password, or after `?` or `&`, a URL query's password. A regular expression
  with no group after `password=` that is made only of `.`, escapes and character classes and
  ends in an escape or a class with a quantifier (`\w{8,}`, `[A-Za-z0-9]+`; the class with a
  range, an escape or `^`) is kept, as a group is; one with a literal character in it
  (`abc[0-9]+`) is redacted.
- A PEM private key written in code as joined string literals (Python's `\`, Java's `+`, PHP's
  `.`) is hidden whole, under any name, also when another BEGIN marker (a marker constant, a
  comment) with no END marker of its own stands before it, then from that marker on, as 1.7.8's
  shape hid it (a marker in a secret-named variable's value or in a connection-string password,
  `PRIVATE_KEY_HEADER = "-----BEGIN ..."`, pairs with nothing, as in 1.7.8, so the code after it
  is sent); 1.7.8 sent all but its first line under a secret name.
  Code between a BEGIN and an END marker string, a name between its literals included
  (`+ privateKeyBase64Encoded +`), is sent as in 1.7.8 when the BEGIN marker's literal closes right
  after the marker and its line breaks; one that goes on with key text first reads as a key.
- An armored PGP private key block (`-----BEGIN PGP PRIVATE KEY BLOCK-----`) is redacted as a PEM
  private key is, in code and configuration files; with its checksum line and `Version:` or
  `Comment:` headers it is written as a key for the line-range and cap rules below. 1.7.8 sent
  it. A PGP public key block is sent as written.
- In a code file that starts with a UTF-8 byte-order mark, a typed secret declaration on line 1
  (`SECRET_KEY: Final = "..."`) is redacted.
- In a YAML or TOML file, a list or table under a secret key that goes on below its line
  (`api_keys = [`) is redacted to its closing line; in an INI, `.cfg`, `.conf`, `.properties` or
  `.env` file only that line is, as before. A comment inside the list that holds `]` or `}`
  does not end it; in YAML a `#` or an apostrophe inside an unquoted item (`k#1`, `o'neil`) is
  part of the item, so a list that closes on its key's line redacts only that line, and `''`
  inside a single-quoted item is an apostrophe. In YAML, after `key:`, a tag or an anchor
  before the list, map or block (`api_keys: &keys [`, `private_key: !!binary |`) is passed over.
- A configuration file is known by its suffix in any letter case (`application.YML`), and the
  template name `env.example` in any letter case too, so their secret settings are redacted.
- In a code file too, a line range that starts or ends inside a PEM private key written as a key
  sends that key's lines as `<redacted>`.
- A PEM private key written as a key on one line that the 2,600-character cap, or a claim's share,
  would cut is hidden whole first, also in a file whose lines end in a lone `\r`; 1.7.8 sent the
  part before the cut. A key whose line breaks are written as XML's `&#10;` or `&#xD;` counts as
  written as a key, so a cut or a line range sends none of it either.
- Code audit: a PEM private key written as a key that the cut between two units splits is sent
  as `<redacted>` lines; 1.7.8 sent its lines.
- CI triage: a PEM private key, or an armored PGP private key block, in a failed step's log, or
  in a JUnit failure's message or text,
  is redacted from its BEGIN marker to the next END marker when key text follows the BEGIN
  marker: every line between is sent as `<redacted>`, whatever it holds (behind pytest's `E` or
  another per-line prefix, in a `-vv` diff of a list or a dict, in `pprint`'s or Node's quoted
  form, with another job's line in between); 1.7.8 sent its lines. A marker is found also with
  control or invisible characters inside it (a UTF-16 log without a byte-order mark). `PRIVACY.md`
  has the rule.
- CI triage: a secret declared with a string type is also redacted behind a line's leading marks
  (`+API_TOKEN: str = "..."`; a diff's `+` or `-`, pytest's `>` or `E`, a line number, `|`, `#`),
  in log lines and in the change excerpt.
- CI triage: the name of a Windows home folder is shown as `<user>` with `Users` in any letter
  case, written with `\`, `\\` or `/` (`c:\users\x`, `C:\\Users\\x`, `c:/users/x`); written with
  `/`, only where the drive letter is not right after a letter, a digit or `_`.

**Spec drift.**
- A Python file that starts with a byte-order mark is indexed, and its docstrings read, so a map
  entry that names one of its functions, classes or constants, or a route it defines, is checked
  and its code sent (1.7.8 reported it not found and left it unchecked), a `config:` entry
  also shows that file's reads of the setting, and a route it mounts from another file
  (`include_router(..., prefix=...)`, `register_blueprint`, Django's `include()`) now has its
  prefix, so a `route:` entry written without it, which 1.7.8 checked, is reported not found; a line
  range into it, and code audit's units of it, have their comments and docstrings removed, as in
  any Python file; 1.7.8 sent its docstrings.
- One claim's failed first request no longer stops the others being asked again (code audit too).
- `--dry-run --out` in a folder whose path is not valid UTF-8 writes its plan (such a byte as `?`)
  when the map has a problem, instead of a traceback.
- `validate_spec_map` lists the first 20 problem lines and names a file that lists them all;
  `problems_total` counts them.
- `check_spec_drift`, `validate_spec_map`, `preview_spec_check` and `draft_spec_map` (with `docs`)
  show the notes the command line prints about indexing the code, such as code files whose names
  are not valid UTF-8 or a YAML config that could not be parsed (`index_notes`): the first 10, then
  `... and N more`, which the command line now prints too.
- The spec finder runs git with `LC_ALL=C` and decides "outside a repository" as the code audit
  does when git finds no repository on its way up, so with git in another language an empty `.git`, a `GIT_CEILING_DIRECTORIES` entry or a
  mount point above the project no longer stops it; a repository git cannot read stops it with
  git's message, and so does a `.git` folder in the project or above it that is not empty but that
  git does not take for a repository (its HEAD gone), also with git in English, where 1.7.8 listed
  the files there; naming the spec in `docs` still works.

**CI triage.**
- A matrix whose step names differ only by a pre-release version (`3.14-dev`, `3.13.0-beta.4`,
  `1.23rc1`, `22-ea`, `23-nightly`) is one failure again, as in 1.7.7. A pre-release word written
  as a word of its own (`3.13 beta`) still keeps two names apart.
- A GitHub-hosted Windows workspace written with `/` (`D:/a/<r>/<r>/`) is removed from log paths.
  Git Bash's `/d/a/...` is still left as written.
- No workspace is cut out of a URL: `file:///home/you/work/r/r/x` is sent as
  `file:///home/<user>/work/r/r/x`, where 1.7.8 sent `file://x`. A workspace path after a URL in
  the same JSON or `key=value` text is cut: a GitHub-hosted or another CI's as in 1.7.8, and now
  a container job's (`/__w/<a>/<b>/`) or a self-hosted runner's (`_work/<a>/<b>/`) too, which
  1.7.8 left as written there.
- A CI log or JUnit report whose file name is not valid UTF-8 can be previewed and triaged; 1.7.8
  failed with an internal error.
- `triage_ci_failure`'s output schema says what `complete` means: every failed job's log read and
  every failure answered.

**Code audit.**
- A rule file that `draft_rule_map` finds but cannot reach (a folder under `.claude/rules` that
  can be listed but not entered, a link loop, a link to nothing) is left out with a note naming
  it, and the other rule files are drafted, on every Python version, in git and outside it; on
  such a folder 1.7.8 failed with a permission error. With `docs` naming the folder that holds
  it, it is left out with a warning; a link there that can be followed is left out without one,
  as before.
- A code file whose name is not valid UTF-8, in git or outside it, is left out of an audit with a
  note naming it when git lists it or its folder can be listed, on the command line (stderr) and as a `note:` line in `validate_rule_map`,
  `preview_code_audit` and `check_code_rules`. Outside git, 1.7.8 crashed on it.
- A code file in scope that cannot be read (no read permission, or in a folder that cannot be
  entered) is left out with a note naming it, and the rest of the audit runs (except as *Not fixed*
  says): in every scope when
  git lists the file or, outside git, its folder can be listed. 1.7.8
  stopped with a permission error, or, auditing the change, left it and the changed files git
  listed after it out without a word. When git cannot compare the change for another reason, the
  audit now stops with git's message instead of auditing part of it.
- Command line: `--draft-map --docs` leaves out a named rule file that does not exist or cannot
  be read (a link to nothing, a link loop, no read permission) with a line on stderr, and drafts
  the others. 1.7.8 gave a traceback for one it had no permission to read and said nothing of
  one that did not exist.
- Auditing the uncommitted change on a branch with no commit yet (a new repository,
  `git checkout --orphan`), the files already added with `git add` are audited too; they were
  left out without a note.
- A rule in a `CLAUDE.md` or `AGENTS.md` right in `.claude/`, `.cursor/` or `.clinerules/`, or
  anywhere under `.claude/rules/` or `.cursor/rules/`, gets
  the scope of the folder that holds that agent folder (the whole project for `.claude/CLAUDE.md`),
  not one that matches no code; outside git, `.claude/CLAUDE.md` is found.

**MCP server.**
- A tool argument that holds a NUL or a lone surrogate (such as `\ud800`) gives a tool error
  naming the argument and the character, not an internal error (-32603). A `\udc80` to `\udcff`
  escape, a byte of a file name that is not valid UTF-8, is still accepted, and on Windows a lone
  surrogate is too.
- On Python 3.12 and older, a path in a tool argument that is, or passes through, a link loop
  gives a tool error naming the path, not an internal error (-32603).

**Documentation.** `docs/clients.md` points to the generated how-to page for the size of the
skills and the tool list, instead of figures that had gone stale.

**What is sent changes only where it should.** Measured offline against 1.7.8: the states of
jevmcp's own spec map as 1.7.8 shipped it (823), a Java project's two maps (115 and 131) and code
audit's scoring corpus (126) are byte-identical; of the CI corpus's 121 states, 116 are, and the
other 5 hold a `D:/a/...` or `file://` path, or a Windows home folder written with doubled
backslashes, read as above.

**jevmcp's own spec map** pairs every new or changed sentence of `PRIVACY.md` and `docs/tools.md`
with the code that shows it: 1,080 entries, 895 of them checked claims. Its line ranges were
moved to the 1.7.9 code.

**How it was tested.** Every behaviour change has a regression test that fails on the 1.7.8 code
and passes on this release's; each family's fixes were then attacked by a second agent told to
break them, and what it found was fixed. 2,732 automated tests (one is skipped unless a file owned
by another user exists).

**Not fixed:**
- Spec drift and code audit: a `PWD=` path right after a `;` is still redacted
  (`export HOME=/root; PWD=/srv/app`), as ODBC's `UID=x;PWD=...` password is. In a CI log line or
  a line of CI triage's change excerpt, a `PWD=` path that follows another `key=value` or a quote
  is still redacted when it is inside a home folder (`ENV HOME=/home/you PWD=/home/you`), as the
  folder's name is replaced by `<user>` first, or inside a CI workspace or the project folder
  (`ENV LANG=C PWD=/__w/r/r/src/app`), as that prefix is removed first.
- CI triage: a PEM private key is redacted only up to a whole END marker. Sent as written: the
  key lines pytest shows of a long diff it cuts short without `-vv` (`...Full output truncated`),
  a key whose END marker `pprint` splits inside a `bytes` value, a key each of whose lines
  carries other text after it (one JSON log line per key line), and a key whose body does not
  start within two lines of its BEGIN line.
- CI triage: a typed secret declaration behind a word prefix (docker compose's `web-1  |`) is
  sent as written, and so is the name in Git Bash's or WSL's lower-case `/c/users/x`. A home
  folder's name is replaced only up to its first space (`C:\Users\John Doe\x` is sent as
  `C:\Users\<user> Doe\x`), as in 1.7.8.
- CI triage: a private key whose marker is broken across two lines, or holds a tab, a no-break
  space or another visible character, is sent. Under a PGP block's BEGIN line only empty lines
  and the headers `Version:`, `Comment:`, `MessageID:`, `Hash:` and `Charset:` (at the start of
  the line or after a space or a tab) are passed over when looking for its body.
- CI triage: a file that an error line names only by a `file://` URL (a Node ESM stack frame,
  Kotlin's `e: file:///...`) is not among the files the errors name.
- Connection strings: a password after a `;` is read as in 1.7.8, to `&`, a space or a quote; what
  follows that is sent (`Password=Hunter22 x;` reads `Password=<redacted> x;`), and a value with
  fewer than four characters before it is sent whole (`Password=P&ssw0rd!;`). A wider rule was
  tried in this release and taken back, as each change to it was found to send something else.
  A `pwd=` value in plain quotes (`Pwd='...'`) is sent as written, and when a `;` and a space
  stand between two passwords in one string, the second may be sent as written
  (`Server=db;Password=abcd; Pwd=Hunter22;`).
- A PEM private key with other text on its lines (a Kotlin or Scala `|` margin, one appended a
  statement per line as `key += "..."`, one in comment lines) is not written as a key: code
  audit sends it when a unit cut splits it, and spec drift when a line range into a code file
  starts or ends inside it. Appended to a secret-named variable, it is sent but for its first
  line. A PGP block with a header other than `Version:` or `Comment:` is not written as a key
  either.
- A code or configuration file saved as UTF-16 is sent with a NUL between its characters and no
  secret in it redacted. A code file with an upper-case suffix (`UPPER.PY`) is not indexed by
  spec drift and keeps its comments.
- Code audit: auditing the change stops with `N changed files cannot be read, too many for git to
  leave out of the comparison` when more changed files that cannot be read (of any kind, each in a
  folder that can be entered) are in the change than fit on git's command line, tens of thousands
  on Linux; 1.7.8
  audited the changed files git listed before the first of them.
- Code audit: a file that the file list does not hold (outside git, one in a folder that cannot be
  listed) is left out without a note, in every scope, also when `files` names it, as in 1.7.8.
- On Python 3.13 a link loop named in a tool argument is answered as in 1.7.8, not with the new
  error.

## 1.7.8 — 2026-10-07

**The known issues of 1.7.7, fixed.** The 1.7.7 entry below ends with a list of known issues: four
that the last review round found in 1.7.7's own changes, and gaps 1.7.6 already had. Each one is
fixed here, or narrowed where a full fix would need a guess with known false hits, except two: rule
drafting reads bold marks, masks, splats and powers as 1.7.7 did, so the two known issues about
stars stay (see *Not fixed*). What is still open is listed under *Not fixed* below. The fixed
questions, their options, the thresholds, the model and spec drift's sentence reading are unchanged.

**A run that TypeSafe stops keeps every answer it got** (all three tools that send). When TypeSafe
rejects the key (HTTP 401/403) or the credits run out (HTTP 402), nothing new is sent and requests
already in flight finish, as in 1.7.7. Now every answer that came back counts, whatever its item's
place in the order: it is labelled, counted in `checked` and the counts, paid for in `cost_usd`
and kept in the results file. 1.7.7 dropped the answers to items later in the order than the
stopped one, and when the stop hit the first item, every answer: the reply was then an error
("checked 0", $0) although TypeSafe had answered. Items with no answer are not checked: spec drift
adds one line, `the run stopped early: <reason>`, and `checked` is less than `claims_selected`;
CI triage and code audit mark each such item `not checked: the run stopped early`. A rejected key
is always an error reply (exit 2 on the command line), and its results file still holds every
answer received. Credits running out give an error reply only when no item got an answer;
otherwise the reply is normal, with `complete: false` (exit 3). An item whose re-asks the stop cut
keeps its first answer's label, with a `note`, as in 1.7.7. When more than one answer is asked
for (spec drift's and code audit's default of 3) and the stop comes before asking again, nothing is
asked again: each answered item that one answer did not settle (spec drift's `review` and `??`,
code audit's `review`) keeps its first answer's label, with one answer (`samples` 1) and the
`note` `not decided by agreement: asking again failed (not asked: the run stopped early), so the
label is the first answer's`, and the stop line gives their number:
`the run stopped early - N item(s) keep their first answer's label: <reason>`. With one answer
asked for, or when every answered item was settled, the line stays
`the run stopped early: <reason>`, with no note.
- **Why the run stopped is never cut from the reply.** The `INCOMPLETE` block, in all three tools,
  now starts with that line (`the run stopped early`, `re-asking stopped early`,
  `re-asking was cancelled`), so "credits are used up (HTTP 402) ... Top up" is always in the text;
  then it lists the first 20 lines and `... and N more (...)`. `structuredContent.not_checked` has
  the same order and is cut to fit (about 10,000 characters), and the new `not_checked_total` counts
  every line. Past 20 lines, when the reply is an error or `not_checked` was cut, the text names a
  file in the results folder that lists every line (`last-check-not-checked-...`,
  `last-ci-triage-not-checked-...`, `last-code-audit-not-checked-...`). 1.7.7 listed every line of
  `check_code_rules`' error reply (64,797 characters in an outage of 603 requests, measured offline;
  now 6,342), and kept the whole list in `not_checked`: with 1 of 3,486 requests answered, a reply
  of 627,770 characters for code audit (now 46,051) and 298,753 for spec drift (now 14,029). In CI
  triage the logs not read are still all listed, and the jobs not checked as in 1.7.7 (the text
  names the first 20, then `(+N more)`; `jobs_not_checked` and the results file name them all). The
  output schemas now say what `not_checked` holds: a stop gives its one line, never one per item it
  cut, and only a request that failed, or asking again that failed other than by a stop, gets a line
  of its own; `not_checked_total` counts lines, not items. An item a stop left unsent is counted by
  `claims_selected` minus `checked` (spec drift) or is a result labelled `not checked` (CI triage,
  code audit); an item whose asking again it cut, while asking again or before it, keeps its first
  answer's label with a `note`, and the stop line gives their number
  (`re-asking stopped early - N item(s) ...` or `the run stopped early - N item(s) ...`). A
  cancelled call gets no reply at all, as MCP has it; its results file holds every answer received.
  `check_code_rules`' `complete` now says that it is false also when only asking again was cut (as
  it already was); a file the audit never reads, such as one over 1.5 MB, is not a request.
- **A name that is not valid UTF-8 does not fail the reply.** The files the three tools that send
  write beside their reply (the results file, the list of places, and the lists of map problems
  and of what was not checked) write `?` for a byte of such a name, as the reply does, so writing
  them never turns the reply into an internal error: in 1.7.7 a CI log whose name is not valid
  UTF-8 made `triage_ci_failure` fail that way. `preview_ci_triage` still does (see *Not fixed*).
- **Items asked exactly alike share their answers.** Two spec-map entries with the same sentence and
  the same code (in CI triage and code audit, two items whose requests are exactly the same) are
  asked once, in the first pass and when asked again, and each keeps its own row. 1.7.7 asked both,
  and their answers went into one cached list, so one of them could be decided "by agreement" on two
  independent answers instead of three. The shared answers cost nothing more. jevmcp's own map has
  two such groups.

**Secret redaction: more forms are redacted.** Sent as written in 1.7.7, now redacted (the rules
for code also apply to the units a code audit sends and to the change and the log lines a CI triage
sends):
- C and C++ `L"..."` and `u8"..."` strings (in single quotes too), and C#'s `$"..."`, `$@"..."` and
  `@$"..."` when the value holds no `{`; in a C# verbatim string (`@`, `$@`, `@$`) a doubled `""` is
  part of the value, which is now redacted whole (1.7.7 sent what followed the first `""`, for
  `@"..."` too). In a C# verbatim string on one line (`@"..."`, and `$@"..."` or `@$"..."` when it
  holds no `{`), any value of four characters or more is redacted whole, quotes of the other kind,
  backticks, spaces and a leading `""` included (`@"it's a secret"`, `@"""quoted"""`), while
  elsewhere a value that holds the other kind of quote along with a space is still sent as
  written; a verbatim string that spans lines, or a `$@"..."` that holds `{`, follows that general
  rule. A lower-case `l` is not a prefix.
- A declaration typed with a bare `Final`, `typing.Final`, `ClassVar` or `Any` (Python), or
  TypeScript's `any`, case as written (`SECRET_KEY: Final = "django-insecure-..."`).
  `Final[int]` and other types that are not strings are still sent as written.
- A password in a JDBC URL or a connection string, in code and configuration: a `password=`,
  `passwd=` or `pwd=` value, in any case, right after `?`, `&`, `;`, a quote or a backtick, or after
  another `name=value` (ending in `;` or not) and a space, with no space around the `=`
  (`?user=x&password=...`, `Server=db;Password=...;`, `Server=db; Password=...`, `UID=x;PWD=...`,
  libpq's `host=db user=x password=...`). That earlier value is a word with no space, `=`, `;`, `&`
  or quote that does not end in `,`, `(` or `)` (`Data Source=db,1433; Password=...`,
  `Server=(localdb)\MSSQLLocalDB; Password=...`, `port=5432,5433 password=...`), one word in
  parentheses (`Server=(local); Password=...`) or a single-quoted value (libpq's
  `dbname='app' password=...`). The key is kept; the value is kept only when the whole of it has the
  shape of a placeholder or a variable (`{pw}`, `<password>`, `%s`, `%v`, `%DB_PASS%`, `$1`,
  `$DB_PASS`, `$env:DB_PASS`, `$(cat file)`, Ruby's and Elixir's `#{pw}`, Swift's `\(pw)`, Ruby's
  `%{pw}` and `%<pw>s`, `*****`, a regular expression's group such as `(\S+)`, with `\n` or
  punctuation after it or not), or is a `{...}`, `#{...}`, `<...>` or `$(...)` that a quote or a
  space cuts and that closes later on the line (`#{ENV['PW']}`); `${...}` is kept and its default
  redacted. A password that only starts like one, or with `@` or `:`, is redacted (`%40dm1n%21x`,
  `$uperS3cret!`, `*Hunter22*`, `(Hunter22)`, `#Hunter22`, `@dmin2024`), and so are a `{`, `#{` or
  `<` value that a `;` or `&` cuts (`#{Hunter22;`) and ODBC's brace-quoted value with a `;` in it,
  spaces, `&`, `'`, backticks and an escaped `\"` included (`PWD={Str0ng;Pass}`,
  `PWD={My Str0ng;Pass}`, `PWD={Hu&nter;22}`, `PWD={It's;Str0ng}`), redacted whole. A value in
  escaped quotes, as written inside a source string or a JSON file (`Password=\"...\"`,
  `password=\'...\'`), is one value: it may hold `;`, spaces, the other kind of quote, backticks and
  ADO.NET's doubled quote (`\"Hunt\"\"er\"`); the escaped quotes are kept and what is inside them is
  redacted (`Password=\"<redacted>\"`). A whole placeholder inside them is kept (`\"{pw}\"`,
  `\"<password>\"`; `${...}` keeps its name, with any default redacted), but a `<...>`, `{{...}}` or
  `#{...}` there that holds `;` or `&` is redacted, and so is a command substitution with arguments
  (`\"$(cat file)\"`, sent as written unquoted); a value under four characters (an empty `\"\"`
  too) is sent as written, as unquoted values are; code that builds the quotes with the string's own
  quote (`"password=\"" + pw + "\""`) is sent as written, and with the other kind of quote it may be
  redacted. A password with a placeholder's or a variable's whole shape is sent as written
  (`{Hunter22}`, ODBC's quoting of a password with no `;`, `#{Hunter22}`, `%{Hunter22}`,
  `\(Hunter22)`, `<Hunter22>`, `$uperS3cret`, `%NAME%`). A keyword argument
  (`connect(host=h, password=pw)`) or a statement (`foo(a=1); password=x`, `x=f(a); password=x`) is
  sent as written.
- In configuration files: a secret value that opens a multi-line string with three double or three
  single quotes (TOML's `password = """`), with every line up to and including the closing quotes;
  in YAML, the sequence items and plain values on the lines below a secret key that has no value on
  its line (`api_keys:` then `  - sk-...`; `password:` then `  hunter2`), a quoted item that holds
  `: ` included, also after a tag or an anchor (`- "admin: x"`, `- !!str "admin: x"`,
  `- &a "admin: x"`), while a mapping below it (an OpenAPI property's `type:`; an unquoted `key:` or
  a quoted key followed by `:`, after a tag or an anchor too) is read line by line as before; a `#`
  comment line among those lines, at any column, does not end the value (it is read as a line of its
  own: a commented-out setting there, `# password: x`, has its value redacted, and any other
  comment, a commented-out item or value included, is sent as written), while a `;` line at the
  key's column or to its left does (an indented one is read as part of the value and redacted); a
  placeholder there is read as on the key's line (`- ${API_KEY}`, `${GOOGLE_SECRET}` and
  `- ${{ secrets.TOKEN }}` kept, `${DB_PASS:hunter2}` sent as `${DB_PASS:<redacted>}`, a quoted
  placeholder, or one after a tag or an anchor, redacted whole, as `password: "${KEY}"` is), and a
  lone `-` is sent as written; and a secret setting left in a comment
  (`#spring.datasource.password=...`, `# password: ...`, `; password = ...`, `# export API_KEY=...`,
  and `!` in a `.properties` file) when its value is one word or one quoted string, with a
  ` # comment` of its own after it or not. A comment whose value is several words, a note, is sent
  as written. Redacted lines keep their place, so line numbers never move.
- In a configuration file, a PEM private key over several lines (from its `-----BEGIN` marker to the
  first `-----END` marker of a private key after it) has its inner lines redacted before the
  configuration rules run: each inner line with text on it becomes `<redacted>`, keeping its
  indentation and line-continuation backslashes, so every line stays where it was, line ranges name
  the same lines, and a value that goes on after the END line (a `.properties` continuation, more
  text under a YAML key) is still redacted as part of that secret. A key the rules take only part
  of, such as one written as a quoted YAML or `.env` value over several lines
  (`private-key: "-----BEGIN ...`), which 1.7.7 sent but for its first line, or that a line range
  cuts, is sent as one `<redacted>` a line, its BEGIN and END lines and any text after END on that
  line included. A key the rules redact line by line (a YAML `|` or `>` block under a secret key, a
  `.properties` continuation) or leave as written (under a key that is not secret-named, such as
  `content: |`, or in a TOML or INI value, which the PEM shape then hides whole as one `<redacted>`)
  is sent as 1.7.7 sent it, in a long file and in a claim that shares the 2,600-character cap with
  other code too. Under the new rules above, a key that is the value of a secret TOML multi-line
  string (`private_key = """`) or of a bare YAML secret key with the key on the lines below
  (`private_key:`) is sent as one `<redacted>` a line, where 1.7.7 sent one.
- **A cut never sends part of a PEM private key** (spec drift). When the 2,600-character cap on a
  file, a line range or a symbol, or the share of it a claim's code gets, would cut inside a PEM
  private key over several lines, in any file, every such key in that code is first sent as
  `<redacted>` lines; 1.7.7 sent the part before the cut, sometimes only a few characters
  (`-----BEGIN PRIVA`). A key written on one line is cut as in 1.7.7, and so is a key in a Java,
  JavaScript or TypeScript file whose lines end in a lone `\r` (other files are read with such a
  `\r` as a line end). The hidden key is shorter, so more of the code after it can be sent.
- **A config file that starts with a byte-order mark is redacted as one without it** (spec drift; a
  code audit sends no config file): 1.7.7 did not read a secret setting on its first line, nor, in
  1.7.8's new rules, the values below it, and sent them as written.

**Spec drift.**
- **A map saved as UTF-8 with a byte-order mark loads**, a spec map and a rule map alike (Windows
  PowerShell 5.1's `Set-Content -Encoding UTF8`, Visual Studio's "UTF-8 with signature"); 1.7.7
  refused it as invalid JSON. `--update-lines` keeps the mark and changes only the digits; maps are
  still written without one. The "not valid JSON" message mentions a trailing comma or a missing
  quote only where that can be the cause, never for an empty file.
- **A code file whose name is not valid UTF-8** no longer makes a check, a dry run or
  `draft_spec_map` fail with an internal `UnicodeEncodeError` (on the command line a traceback and
  exit 1, which reads as "at least one DRIFT"). A code, config or OpenAPI file whose own name, its
  path inside the checked folder, is not valid UTF-8 is left out of the index with a note that
  names it (the command line prints the note; the MCP tools do not), and a dry-run plan that cannot
  be written leaves no empty file. On the command line, a `--src` path that is itself not valid
  UTF-8 stops a check, a dry run or a draft at once with exit 2 and says to cd into the project;
  1.7.7's dry run worked there, but its real check crashed writing `drift.json` after sending.
- **Outside a git repository, the spec finder** (`draft_spec_map` without `docs`, `--find-specs`)
  works whatever language git prints its messages in when no folder from the project up holds a
  `.git`. With a `.git` there that git does not use (an empty or stray one, or a repository above a
  `GIT_CEILING_DIRECTORIES` entry or past a mount point) and git in another language, it still stops
  with "git could not list this project's files", as in 1.7.7 (see *Not fixed*).
- **`check_spec_drift`'s map problems are capped.** The `MAP PROBLEMS` block lists the first 20
  lines, a line about the map as a whole (a `specs` folder that is gone) first, then
  `... and N more lines (all M lines are listed in <file>)`; the file,
  `last-check-map-problems-<project>-<tag>.json`, is written whether or not the reply is an error.
  `structuredContent.map_problems` is cut to fit, and the new `map_problems_total` counts lines, not
  entries: a broken entry usually gives two. A map with 597 of 600 entries broken by a rename gave
  a reply of 351,192 characters; now 14,948 (measured offline). `validate_spec_map` still lists
  every problem.
- **The output schema's `complete`** now says what the docs say: true only when nothing was
  skipped (no map problems, nothing stopped, nothing failed, asking a claim again included).

**CI triage.**
- **An action that failed with only an `##[error]` line** keeps its own error line and run time
  when the job then stops at its time limit and the log prints the limit line, in either wording,
  as it already did for the cancel line.
- **Fail-fast is measured from a failed job only.** A cancelled job is called "cancelled after the
  failure (fail-fast)" only when it ended between 5 seconds before and 5 minutes after a job of its
  matrix that GitHub reports as failed or timed out (or when an end time is not known), whether or
  not that job is being triaged. Triaging a cancelled or time-limit job by its own URL no longer
  makes it the failure its siblings are measured from, so a sibling stopped at its own time limit
  gets the neutral note with its run time.
- **Jobs that failed at different steps are not merged.** Failures merge on the failed step and the
  first error together. The step's name is compared with case, numbers, hex ids and OS names
  ignored (`ubuntu`, `macos` and `windows`, with `-latest` or a version or not, and in the step name
  also `linux`, so `${{ runner.os }}`'s `Linux`, `macOS` and `Windows` count as one), a version
  counting as one number however many parts it has (`Go 1.22` and `Go 1.22.3`), so a matrix whose
  step name carries its value (`Set up Python 3.12`, `Run tox -e py312`, `Test on Linux`) is still
  one failure, while steps whose names differ in words (an abbreviation such as `win`, `osx` or
  `darwin` included) are separate failures, each its own request. On the 73-run corpus this splits 4
  merged failures, and the requests go from 108 to 121; one of them is the pair the 1.7.7 entry
  described as merged by apt's first error (`Install Valgrind` and `Install system dependencies`). A
  merged failure shows the first job's step name, run time and cancel facts, as before.
- **More CI workspaces are removed**: a GitHub container job's `/__w/<a>/<b>/`, and a self-hosted
  runner's or Azure Pipelines agent's `<install folder>/_work/<a>/<b>/` (on Windows
  `X:\...\_work\<a>\<b>\`, or the same with forward slashes). Such logs now have relative paths,
  name the project's files and offer the traceback frame. The two cuts apply only where a path
  starts: never right after a letter, a digit, `_`, `.`, `~`, `-` or `/`, nor right after a
  one-letter word and `:`, a drive (`D:/__w/...` and `-v /x:/__w/...` stay as written); a
  self-hosted path that starts with a drive (`C:/opt/r/_work/<a>/<b>/`) is cut, drive included.
  Their `<a>` and `<b>` hold no `:`, `;` or `,`, so a workspace path that such a list separator ends
  is sent as written, as in 1.7.7 (`-v /__w/r/r:/app`,
  `--mount type=bind,source=/__w/r/r,target=/app`, `PYTHONPATH=/opt/r/_work/w/w:/...`,
  `C:\actions-runner\_work\w\w;C:\...`, `["/__w/r/r","/usr/lib/x"]`), where the cut ran on into the
  next entry before this fix. The exception is a runner installed in `~/work` or `X:\a\`, or one
  folder below either: 1.7.7 cut its workspace path as a GitHub-hosted one
  (`-v /home/<user>/work/_work/r/r:/app` read `-v r:/app`, `set PATH=D:\a\_work\r\r;C:\Windows` read
  `set PATH=r;C:\Windows`), and 1.7.8 sends that path whole, a home folder shown as `<user>`; so it
  does when such a runner's workspace path ends at a space or at the end of the line, or is inside a
  URL, where 1.7.7 cut it too. A workspace path with a file or folder after it is still cut, in a
  list too (`PYTHONPATH=/opt/r/_work/w/w/src:/opt/r/_work/w/w/lib` reads `PYTHONPATH=src:lib`,
  `source=/__w/r/r/out,target=/app` reads `source=out,target=/app`). They never apply inside a URL:
  when the path's own word (the characters before it, back to a space) holds `://` (`https://...`,
  `file:///__w/...`, `file:///C:/.../_work/...`, `https://[::1]/_work/...`); a URL earlier on the
  line, before a space, does not stop them. A self-hosted path is cut below its first
  `_work/<a>/<b>/` whose `<a>` is not a runner folder, so a project's own `_work` folder keeps its
  path; the install folder must be written in plain path characters and never passes through a
  runner folder, so a path inside `_actions`, `_temp`, `_tool` or `_tasks` is kept whole, also with
  a `_work/` deeper in it. That holds for a runner installed in `~/work` or one folder below it, or
  in `X:\a\` or one folder below it written with `\`, and for a path printed right after a log
  marker such as `##[error]` or `[command]`. A GitHub-hosted Windows workspace written with `/`
  (`D:/a/...`, Git Bash's `/d/a/...`) is left as written, as in 1.7.7, a runner installed in `X:\a\`
  written that way included. The other CIs' workspaces keep 1.7.7's cut, and a project's own
  `_work/<a>/<b>/` below them keeps its path: GitLab's `/builds/<g>/<p>/` at the start of a path and
  its shell executor's `builds/...` in the `gitlab-runner` user's home folder, Jenkins'
  `/var/lib/jenkins/workspace/<job>/`, CircleCI's `project/` and Travis CI's `build/<o>/<r>/` in the
  `circleci` and `travis` users' home folders (and `X:\Users\travis\build\<o>\<r>\`), a Docker
  action's `/github/workspace/`, Buildkite's `/var/lib/buildkite-agent/builds/<a>/<o>/<p>/` and
  TeamCity's `/opt/buildAgent/work/<id>/` and `X:\BuildAgent\work\<id>\`; only these exact paths. A
  path under any other workspace (a Jenkins agent's `agent/workspace/<job>/` in the `jenkins` user's
  home, Bitbucket Pipelines' `/opt/atlassian/pipelines/agent/build/`) gets the self-hosted cut at
  its first `_work/<a>/<b>/`, like any absolute path. A line that starts with `/workspace/`, where a
  runner may be installed, is cut in 1.7.7's place, before Travis CI's, GitLab's shell executor's,
  Buildkite's and TeamCity's paths are read, so a path of theirs after it is never spliced: at its
  first `_work/<a>/<b>/` that the self-hosted cut would cut, below another CI's path too
  (`/workspace/_work/a/b/x` reads `x`, `/workspace/x/_work/a/b/c.go` and
  `/workspace/opt/buildAgent/work/1/_work/a/b/c.go` read `c.go`; 1.7.7 read
  `opt/buildAgent/work/1/_work/a/b/c.go` there), and otherwise only `/workspace/` comes off, as in
  1.7.7 (`/workspace/opt/buildAgent/work/1/x` reads `opt/buildAgent/work/1/x`, and
  `/workspace/opt/buildAgent/work/1/_work/_temp/x` reads `opt/buildAgent/work/1/_work/_temp/x`). A
  relative path is not touched. **The change excerpt is not cut this way:** its lines are code, and
  only the workspace cuts 1.7.7 made apply to them, the GitHub-hosted one as 1.7.8 reads it. So two
  kinds of path that 1.7.7 cut in a diff line are now sent whole, the home folder shown as `<user>`:
  one under Azure Pipelines' `_tasks` (`/home/<user>/work/_tasks/...`, `X:\a\_tasks\...`), and one
  of a runner installed in `~/work` or `X:\a\`, or one folder below either
  (`/home/<user>/work/_work/<r>/<r>/...`, `/home/<user>/work/<x>/_work/<r>/<r>/...`,
  `X:\a\_work\<r>\<r>\...`, `X:\a\<x>\_work\<r>\<r>\...`); a path under `_actions`, `_temp` or
  `_tool` was kept whole in 1.7.7 too. Any other container or self-hosted path in a diff line is
  sent as written, as in 1.7.7, and a diff line that starts with `/workspace/` loses only that, as
  in 1.7.7.
- **Azure Pipelines' `_tasks` folder** joins `_actions`, `_temp` and `_tool` as a runner folder
  that is kept whole and never named as a project file, under each of those workspaces.
- **The log-file guard holds on Windows and for every `.git` folder.** A log under any `.git`
  folder (`vendor/lib/.git/config` too, which 1.7.7 read on every system), or a secret file in a
  subfolder (`deploy\id_rsa`, `ci\.npmrc`), is refused with `<path> is not a log a check may read.`,
  the path written with `/`.
- **Narrowed, not changed: a matrix is known only by its job names.** GitHub's record of a job names
  no matrix (checked live: the job record has no matrix key, its check run's external id differs for
  each job, and the check suite covers the whole run), so jobs count as one matrix when their names
  are the same up to the first ` (`, as GitHub's default names, `name (values)`, are. The jobs of a
  matrix whose own `name:` puts its values elsewhere (`ubuntu-latest @ Go 1.25`) are not seen as
  one: their cancelled jobs get the neutral note with their run time, and the "same step passed in
  other jobs of its matrix" fact is not given for them. Two different jobs whose names agree up to
  ` (` (`Lint (python)` and `Lint (docs)`) are seen as one. The 1.7.7 sentence about the corpus now
  reads: the 100 cancelled jobs named as the failed job's matrix ended 0 to 105 seconds after it (of
  the corpus's 134 cancelled jobs, 34 belong to matrices that name their own jobs, 32 of one
  project's and 2 of another's).

**Code audit.**
- **The rule-file finder takes the files coding agents load as rules**: every `.md` file under
  Claude Code's `.claude/rules/` (subfolders too, at the root or in any folder), every document
  directly in Cline's `.clinerules/` folder (not its subfolders, such as `workflows/`), and a
  `.clinerules` file, on Windows outside git too: there the file list now names files with `/`, as
  git does, so the files a code audit reads there are named with `/` too. Outside git, the walk for
  `.claude/rules` and `.cursor/rules` follows no link: a linked `.claude` or `.cursor` folder
  (wherever it leads, inside the project too), a linked `rules` folder, a linked file and a file
  that resolves outside the project are not listed, so `validate_rule_map` never names them as rule
  files in the project and `preview_code_audit`'s file list does not count them; in a git
  repository, git's list is used as before. A found rule file that cannot be read is left out with a
  note (one named in `docs` still fails). A rule file's YAML front matter (a leading `---` block
  in a `.md`, `.mdc` or `.mdx` file whose first line that is not blank or a `#` comment, at the
  margin or indented, is a `key:` line at the left margin, every other line a key, a list item, a
  line that goes on with one, a `#` line or blank, and a list item at the left margin under a key
  with nothing after its colon, such as `paths:`, under a key whose list begins on its line, or
  under another item) is no longer read for rules, so a `description:` is never drafted as one; its
  `paths:` (or Cursor's `globs:`) is not used as the scope either: the scope is guessed from the
  rule's words, and the review sets it. A document that opens with a `---` rule above its Markdown
  is read for rules when the block has no `key:` line, when a list item or an indented line that is
  not a comment comes before any key (`---`, `- Never push to main.`, `Note: ...`, `---`, as in
  1.7.7), or when a list item follows a `Label: text` line (`Note: you must sign the CLA.` then
  `- Never push to main.`); one whose every line reads as YAML (`Rules:` then
  `- Never push to main.`) is still taken for front matter.
- **A scope drafted from a nested `AGENTS.md` or `CLAUDE.md`** uses `/` on every system (1.7.7 wrote
  `services\api/**/*.py` on Windows).
- **A rule map saved with a byte-order mark loads** (see *Spec drift*).
- **Outside a git repository, the code-audit tools** work whatever language git prints its messages
  in (1.7.7 stopped with "git could not list this project's files"). A folder is outside a
  repository when git finds none from it up: an empty `.git` folder in it or above it does not make
  it one, nor does a repository above a `GIT_CEILING_DIRECTORIES` entry or, unless
  `GIT_DISCOVERY_ACROSS_FILESYSTEM` is set, past a mount point, as in 1.7.7. A repository git cannot
  read stops the audit with git's message, a worktree whose repository folder is gone included:
  1.7.7 read every file there, the git-ignored ones too. So does a `.git` folder in the folder or
  above it, up to such a ceiling or mount point, that is not empty but that git does not take for a
  repository, such as one whose `HEAD` or `refs` is gone, as a copy or sync tool that drops empty
  folders can leave it: the message names that `.git`, and 1.7.7 read every file there too.

**What is sent changes only where it should.** Offline and with nothing sent, 1.7.7 against 1.7.8:
- **Spec drift:** the states of jevmcp's own map (734 claims as 1.7.7 shipped it) and of a Java
  project's two maps (115 and 131 claims) are byte-identical to 1.7.7's. Over 121,213 files (4,954
  of them configuration), the new redaction changes 162 lines, all redacted more and none less: 19
  in this release's own tests, the other 143 connection strings in examples and fixtures,
  commented-out `.env` passwords and `# project_key:` templates, block lists under secret-named
  keys, and `*_TOKEN*: Final` constants in a library.
- **Code audit:** the 126 states of the scoring corpus, the 4,109 states of jevmcp's own maps and
  jevmcp's own draft (its 18 entries and its list of sources) is byte-identical. The sentences
  drafted from other documents change only where YAML front matter was read as rules before (which
  files are drafted from, and the scopes, change as described above): over 94,999 documents on the
  maintainers' machine that hold a bold, mask, splat or power shape, every document whose drafted
  sentences differ from 1.7.7's differs by its front matter alone (measured after the sixth review
  round).
- **CI triage:** on the 73-run corpus, 104 of the 108 states are byte-identical; the 4 merged
  failures split as above give 17 states instead of 4 (121 requests). No corpus log has a container,
  self-hosted or `_tasks` path.
- **The second review round's fixes**, measured against the code that round reviewed:
  spec drift's 775, 115 and 131 states, code audit's 126 corpus states, the
  4,228 states of jevmcp's own maps and the drafts of 40,381 documents on the maintainers' machine,
  and CI triage's 121 states are byte-identical. The connection-string rule redacts 43 more lines
  over 123,781 files, none less: 35 in this release's own tests, 6 copies of one library's
  docstring `PWD=(whatever);` and 2 in jevmcp's own comments. On Windows outside git, the code a
  code audit sends now names its file with `/`.
- **The third review round's fixes**, measured against the code that round reviewed: spec drift's
  788, 115, 131 and 131 states, code audit's 126 corpus states, the 4,263 states of jevmcp's own
  maps, its draft (18 entries and its sources) and the drafts of 40,382 documents on the
  maintainers' machine, and CI triage's 121 states are byte-identical, and so are the 48,447 lines
  of change excerpts in the CI corpus (to 1.7.7's too). The redaction scan of 605 files changes one
  line, redacted less: a comment in jevmcp's own `spec_drift.py` whose example
  `password=#{ENV['PW']}` is sent as written again (Ruby's interpolation, as in 1.7.7). No corpus
  log has a path the new CI workspace rules read differently.
- **The fourth review round's fixes**, measured against the code that round reviewed: spec drift's
  809, 115, 131 and 131 states, code audit's 126 corpus states, the 4,284 states of jevmcp's own
  maps, its draft (18 entries and its sources) and the sentences drafted from the 237 rule documents
  in jevmcp's repository and the maintainers' notes, and CI triage's 121 states are byte-identical,
  and so are the 48,447 lines of change excerpts in the CI corpus (to 1.7.7's too). The redaction
  scan of 605 files changes no line; against 1.7.7 it redacts 4 more lines and none less. No corpus
  log or rule document has a shape these fixes read differently.
- **The fifth review round's fixes**, measured against the code that round reviewed: spec drift's
  819, 115, 131 and 131 states (and against 1.7.7's code too), code audit's 126 corpus states, the
  4,298 states of jevmcp's own maps, its draft (18 entries and its sources), and the sentences
  drafted from the 238 rule documents in jevmcp's repository and the maintainers' notes are
  byte-identical, and none of the 474,647 Markdown documents there opens with a `---` block whose
  first line is indented. CI triage's code is unchanged. The redaction scan of 605 files changes no
  line; against 1.7.7 it redacts 4 more lines and none less. A PEM private key in 1,200 generated
  configuration files, read whole and by every line range, sends no part of the key, or of a value
  continued after it, that the code before or 1.7.7 hid.
- **The sixth review round's fixes**, measured against the code that round reviewed and against
  1.7.7's: spec drift's 837, 115, 131 and 131 states, code audit's 126 corpus states, the 4,326
  states of jevmcp's own maps and its draft (18 entries and its sources) are byte-identical; CI
  triage's code is unchanged. Rule drafting is 1.7.7's again: of the 239 rule documents in jevmcp's
  repository and the maintainers' notes, 235 draft as in 1.7.7 and 4 differ only as their front
  matter is no longer read, and against the code that round reviewed, 6 of those documents change,
  each a bold or mask line now read as 1.7.7 reads it. The redaction scan of 605 files changes no
  line; against 1.7.7 it redacts 4 more lines and none less. A PEM private key placed before, across
  and after the 2,600-character cap, read through a file, a line range and a claim that shares the
  cap (4,956 states), and in 1,200 generated configuration files read whole and by every line range,
  sends no part of the key; a state differs from 1.7.7's only where 1.7.7 sent part of a key, or
  where a key is the value of a TOML string or a YAML value below a bare secret key, now redacted
  line by line (384 states of that fuzz, each a YAML value below a bare secret key).

**jevmcp's own spec map** pairs every new or changed sentence of `PRIVACY.md` and `docs/tools.md`
with the code that shows it: 1,008 entries, 823 of them checked claims. Its 232 line ranges were
moved to the 1.7.8 code: 191 by content, 40 by hand, 1 unchanged; after the second review round's
fixes, its 269 ranges were moved again: 239 by content, 17 by hand, 13 unchanged; after the third
round's, its 273 ranges: 173 by content, 1 by hand, 99 unchanged; after the fourth round's, its 270
ranges: 121 by content, 9 by hand, 140 unchanged; after the fifth round's, its 271 ranges: 99 by
content, 3 by hand, 169 unchanged; and after the sixth round's, its 274 ranges: 90 by content, 6 by
hand, 178 unchanged.

**How it was tested.** Every behaviour change has a regression test that fails on the code before it
(the 1.7.7 code, or for a fix from a review round, the code that round reviewed) and passes on this
release's; the guards next to them pass on both. Each family's fixes were then attacked by a second
agent told to break them, and what it found was fixed, or is listed below; the same was done again
for the fixes of the second, the third, the fourth, the fifth and the sixth review round. The
earlier rounds' tests of bold and mask handling in rule drafts went with that handling, and new
tests pin 1.7.7's reading of those shapes. 1,930 automated tests (one is skipped unless a file owned
by another user exists).

**Not fixed** (the two known issues about stars in rule drafts, as 1.7.7 listed them; each other
item is narrower than the 1.7.7 known issue, or older than it):
- CI triage: a matrix is known only by its job names up to the first ` (` (see above). An install
  folder that itself holds a `_work` folder (`/srv/_work/actions-runner/_work/w/w/`) is cut at the
  first one, and a path written right after `:` with no `://` (`file:/opt/r/_work/...`) loses the
  path but keeps `file:`. A self-hosted runner installed two or more folders below `~/work` or
  `X:\a\` (`~/work/<x>/<y>/_work/`, `X:\a\<x>\<y>\_work\`) is taken for a GitHub-hosted workspace,
  so its paths keep `_work/<a>/<b>/` in front and are not matched to the project's files; on a
  runner installed in `~/work` or `X:\a\` itself, a repository named `_work` is taken for the hosted
  workspace of a repository named `_work`. A GitHub-hosted Windows workspace written with `/`
  (`D:/a/<r>/<r>/`, as Go stack frames print it on `windows-latest`, or Git Bash's `/d/a/<r>/<r>/`)
  is left as written, as in 1.7.7, so those paths are not matched to the project's files. A path
  under a workspace 1.7.7 had no pattern for (a Jenkins agent's, Bitbucket Pipelines') loses a
  project's own `_work/<a>/<b>/` folder there, read as a self-hosted runner's. The GitHub-hosted cut
  keeps 1.7.7's reading of a workspace path that a list separator ends
  (`set PATH=D:\a\r\r;C:\Windows` reads `set PATH=Windows`), and a line that starts with
  `/workspace/` followed by a GitHub-hosted, Docker action's, Jenkins or CircleCI path still has
  that path cut out of its middle, as in 1.7.7 (`/workspace/var/lib/jenkins/workspace/j/x` reads
  `/workspacex`). In a step name, only `linux` is added to the OS names: `win`, `osx`, `darwin` or
  `win-x64` keep two failures apart. `preview_ci_triage` still fails with an internal error on a CI
  log whose own name is not valid UTF-8, as in 1.7.7.
- Code audit: rule drafting reads bold and bold-italic marks, masks, splats and powers as 1.7.7 did,
  so 1.7.7's two known issues about stars are not fixed. A Python splat or a power that ends a
  sentence (`must accept **kwargs.`) can lose its `**` when the next sentence of the paragraph has a
  power or a mask (`x**2`, `sk-***`), and a power there loses its stars too; a mask written with
  separators (`***-***-1234`, `192.168.***.***`, `***@***.com`, `10.0.**.**`) is taken for bold and
  loses its stars; and a bold span that a sentence cut splits can keep its closing mark
  (`**CRITICAL: Disk at >95%** must page.` gives `Disk at >95%** must page.`). Every fix of these
  shapes in the review rounds of this release opened the shapes next to it (about fifteen findings
  in five rounds), so they are left as 1.7.7 had them; review a drafted rule's text. A leading `---`
  block whose every line reads as YAML is taken for front matter, rules in it included (any `Word:`
  line counts as a key, and a Markdown heading as a comment). In a git repository, a code file whose
  name is not valid UTF-8 is left out of a code audit with no note, as in 1.7.7.
- Spec drift: an unexpected internal error still exits 1, the code for "at least one DRIFT". A map
  that names a file whose name is not valid UTF-8 by a hand-typed `\udcXX` escape is not handled,
  and `--find-specs` and `--update-lines` do not refuse a `--src` path that is not valid UTF-8.
  Outside a git repository, with git in another language, the spec finder stops with "git could not
  list this project's files" when a folder from the project up holds a `.git` that git does not use
  (an empty or stray one, or a repository above a `GIT_CEILING_DIRECTORIES` entry or past a mount
  point), as in 1.7.7; with git in English it lists the files there.
- Redaction: the triple-quote rule runs in every configuration format, so a YAML `password: '''`
  that never closes is redacted to the end of the file; a value that opens a list or a table on its
  key's line and goes on below it (TOML's `api_keys = [`, YAML's `api_keys: [`) has only that line
  redacted, and the values below it are sent, as in 1.7.7; a commented setting followed by a `;`
  comment (INI) is sent as written, and `# token: see #123` has `see` redacted. A connection-string
  password after a value that holds a space inside braces (`Driver={SQL Server}; PWD=...`, which
  reads as code such as `let x={a: 1}; pwd=...`) or that ends in `)` without being one word in
  parentheses (`Server=f(a); Password=...`, the shape of a statement) is sent as written. A
  connection-string password whose whole value has the shape of a placeholder or a variable
  (`PWD={Hunter22}`, `#{Hunter22}`, `%{Hunter22}`, `\(Hunter22)`, `<Hunter22>`, `$uperS3cret`,
  `$ecret.Pass`, `%NAME%`, a value that reads as a regular expression's group) is sent as written,
  and so is a `{...}`, `#{...}` or `<...>` that a quote or a space cuts and that closes later on the
  line (`PWD={Str0ng Pass}`); a placeholder in parentheses (`PWD=(whatever)`) is redacted. With an
  `&` in such a brace-quoted value with no `;`, `PWD={Hu&nter22}` is sent whole and
  `PWD={Hunt&er22}` in part (`PWD=<redacted>&er22}`). A raw `{` inside a brace-quoted value cuts it:
  `PWD={a{b;c}` reads `PWD=<redacted>;c}`, so part is sent, and `PWD={a;b{c}` is sent whole. An
  unquoted value ends at `&`, a space or a quote, as a URL query's value does, so in a `;`-separated
  string a password holding one is sent in part, or whole when fewer than four characters come
  before it (`Password=P&ssw0rd!;` and `Password=My Secret 22;` are sent as written,
  `Password=Tr0ub4dor&3;` reads `Password=<redacted>&3;`), as 1.7.7 sent them. A brace-quoted value
  that holds a bare, unescaped `"` (`PWD={My"Str0ng;Pass}`, kept so as not to read JSX such as
  `password={a ? "x;" : "y"}`) may be sent whole or in part, and so may a value in escaped quotes
  that holds a bare quote of their own kind (`Password=\"ab"cd\"`, possible only in a string written
  with the other quote). In YAML, below a secret key with no value on its line, a commented-out item
  or value (`# - sk-old...`, `#   hunter22`) is sent as written, and a `;` line at the key's column
  or to its left ends the value, so the values after it are sent, as in 1.7.7 (an indented `;` line
  is read as part of the value and redacted). A quoted secret over several lines that is not a PEM
  private key (`password: "hunter` then `  22"`) has only its first line redacted, as in 1.7.7. In a
  code file, or another file that is not a configuration file, a line range that starts or ends
  inside a PEM private key sends the key's lines inside the range, as in 1.7.7; the 2,600-character
  cap, or a claim's share of it, that cuts a key written on one line (BEGIN and END on the same
  line) sends the part before the cut, as in 1.7.7; a CI change excerpt or a code-audit window that
  starts or ends inside a key can send part of it, as in 1.7.7; and a PGP `PRIVATE KEY BLOCK` is not
  one of the shapes redacted.
- `validate_spec_map` lists every map problem, uncapped (about 350,000 characters for a map with 597
  entries broken by a rename).

**Known issues** (to be fixed in a later release). Found in this release's own changes by the last
review round:
- **CI triage, a matrix by pre-release version.** Jobs whose step names differ only by a pre-release
  version (`Set up Python 3.13` and `Set up Python 3.14-dev`, `3.13.0-beta.4`, `Go 1.23rc1`) are
  separate failures, each its own request; 1.7.7 merged them.
- **Spec drift and code audit, the shell's `PWD=`.** A working-directory setting such as
  `ENV HOME=/home/you PWD=/home/you` or `"PWD=/srv/app"` is read as a connection-string password,
  and its path is sent as `<redacted>`; 1.7.7 sent it as written. Nothing secret is sent either way.
- **Code audit, a rules folder that cannot be entered.** A folder under `.claude/rules` (or
  `.clinerules`) that can be listed but not entered (mode 644) still makes `draft_rule_map` fail
  with a permission error; 1.7.7 drafted the project's other rule files.

Older gaps the review found that 1.7.7 already had, left for a later release:
- **Redaction:** a PEM private key written in code as joined string literals under a secret-named
  variable, or printed over several lines in a CI log, is sent but for its first line; in a code
  file that starts with a UTF-8 byte-order mark, a typed secret declaration on its first line is
  sent as written; a multi-line TOML array or YAML flow sequence under a secret key has only its
  first line redacted.
- **Spec drift:** a Python file that starts with a byte-order mark is not indexed;
  `validate_spec_map` lists every map problem, uncapped.
- **Code audit:** a rule in `.claude/CLAUDE.md` gets the scope `.claude/**`, and outside git that
  file is not found; inside git, a committed file whose name is not valid UTF-8 is left out.
- **CI triage:** a CI log whose own file name is not valid UTF-8 makes `preview_ci_triage` fail; a
  GitHub-hosted Windows workspace written with `/` (`D:/a/r/r/`) is not removed.

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
