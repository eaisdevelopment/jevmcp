# Privacy and data flow

jevmcp runs on your machine. It has no server of its own, sends no telemetry, and keeps no
logs of your conversations.

## What leaves your machine

Three tools send data, each a different kind, and only when they run:

| Tool | What it sends |
|---|---|
| `check_spec_drift`, or `spec_drift.py` without `--dry-run` | spec sentences, each with the code paired with it |
| `triage_ci_failure`, or `ci_triage.py` without `--dry-run` | excerpts of a failed CI run's log, with an excerpt of the change under test |
| `check_code_rules`, or `code_audit.py` without `--dry-run` | units of your source code, each with one of your project's own rules |

Every other tool, and every `--dry-run`, sends nothing to TypeSafe.

Everything that is sent goes to TypeSafe's API (`https://api.typesafe.ai/v1/systemone`) over
HTTPS, authenticated with your API key. TypeSafe's own terms and privacy policy govern what it
does with requests: <https://typesafe.ai>.

### Spec drift

A spec-drift check sends, per requirement being checked:

| Sent | Details |
|---|---|
| The spec sentence | as written in your spec map |
| The code paired with it | see below; file paths relative to your project |
| Computed values | arithmetic the tool worked out from the code, e.g. `15*60*1000 = 15 minutes` |
| Three fixed questions | identical for every requirement |

The code paired with a requirement is cleaned before it is sent:

- **Comments and docstrings removed** in Python (stub files, `.pyi`, included), Java,
  JavaScript/TypeScript and the other C-family languages (Kotlin, Scala, Groovy, Go, C#, C/C++,
  Rust, Swift). Other files — for example PHP, Ruby or shell, which can only be paired by line
  range — are sent as written.
- **Secret-looking values redacted**:
  - everywhere, by shape: Stripe, GitHub, Slack, Google and OpenAI/Anthropic keys, GitLab, npm,
    PyPI and HashiCorp Vault tokens, Slack webhook addresses, AWS access key IDs, JWTs, PEM
    private keys, and credentials inside URLs;
  - in code, quoted values of at least four characters whose name contains `password`, `passwd`,
    `passphrase`, `pass` (as a word: `DB_PASS`, `userPass`), `secret`, `token`, `api key`,
    `private key`, `credential` or `access key`, given with `=`, `:`, `=>` or Go's `:=`, or
    declared with a string type before the `=` where a declaration or a parameter starts — a type
    whose name ends in `str` or `string` (`password: str = "..."`, `Optional[str]`, `SecretStr`,
    `StrictStr`, `const token: string = "..."`, `string | undefined`, `let token: &str = "..."`,
    and Kotlin's and Swift's `String` declarations), or with a bare `Final`, `typing.Final`,
    `ClassVar` or `Any` (Python) or TypeScript's `any`, written in that case
    (`SECRET_KEY: typing.Final = "..."`, `private password: any = "..."`) — and Go's
    `var password string = "..."` at the start of a line. The name may end in a subscript that is
    empty, a number or an upper-case name, as a C array's does (`char password[] = "..."`, `[64]`,
    `[PW_LEN + 1]`) and as a table element's does (`TokenName[1] = "..."`); the value may have a
    string prefix (`b"..."`, `u"..."`, C#'s `@"..."`; C and C++'s `L"..."` and `u8"..."`, in
    single quotes too; C#'s `$"..."`, `$@"..."` and `@$"..."` when it holds no `{`; `r"..."`,
    `rb"..."` or `br"..."` when it holds no `\`, `(` or `[`; an f-string when it holds no `{`, and
    an `fr` or `rf` string under both), and in a C# verbatim string (`@`, `$@`, `@$`) a doubled
    `""` is part of the value, which is redacted whole. A lower-case `l` is not a prefix. A value
    of one word may hold one quote of the other kind (`"p'ssw0rd"`). A value declared with any
    other type (an enum such as `HashStrategy`, or `Final[int]`) is sent as written, and so are a
    raw string that holds `\`, `(` or `[`, which is a pattern (`token_pattern=r"(?u)\b\w\w+\b"`),
    an f-string that holds `{`, a triple-quoted string (`"""..."""`), a value that holds the other
    kind of quote along with a space, or starts with a quote, a value set through a quoted or lower-case subscript
    (`settings['token'] = "..."`, `token[i] = "..."`), and the next value on a line after a `case`
    label, an `if` or `for` line, or a secret word inside a quoted value that no `:` or `=` follows
    (`type="password" autoComplete="new-password"`, `if token: msg = "..."`). A quoted text that
    ends in a secret word and a `:` or `=` (`label="Password:" placeholder="..."`,
    `"Token: " + token + " refreshed"`) has what follows it on the line redacted, up to the next
    quote, as in 1.7.6;
  - in code and configuration files alike, a password in a JDBC URL or a connection string: a
    `password=`, `passwd=` or `pwd=` value, in any case (`?user=x&password=...`, `;password=...`,
    `Server=db;Password=...;` or `Server=db; Password=...`, `UID=x;PWD=...`, libpq's
    `host=db user=x password=...`), when it comes right after `?`, `&`, `;`, a quote or a
    backtick, or after another `name=value` (ending in `;` or not) and a space, with no space
    around the `=`. The key is kept, and so are placeholders (`{...}`, `%s`, `$1`, `<...>`, `@p`,
    and `${...}`, whose default is redacted as below). A keyword argument
    (`connect(password=pw)`) or a statement (`foo(); password=x`) is sent as written;
  - in configuration files (`.properties`, YAML, TOML, INI, `.env` templates) — however they are
    paired, quoted or not — values whose key has one of those names, or whose last part is `key`
    (`jwt.key`, `encryption-key`, `encryptionKey`) or `dsn`, and signing keys and client secrets.
    That includes a quoted key (`"password": ...`), a value that starts with `|` or `>`
    (`password=>Xk9q`, `token: |abc`), every line of a YAML block value (`password: |`, a value
    that is only `|` or `>`, with `-`, `+` or a digit and a `# comment` after it or not), and in a
    `.properties` file a key and value separated by spaces
    (`db.password hunter2`) and every line of a value continued with a backslash. A line that
    continues a value is read as a setting of its own only in the `key=value` or `key: value`
    form, so `password=...` on the next line of a JDBC URL is redacted, as in 1.7.6 (a
    placeholder there, `password=${DB_PASSWORD:hunter2}`, loses its default as below), while
    words there (`password to continue`) are sent as written; a line that continues a key (after
    `db.\` or a lone `\`) is read as a setting in every form. When a key is whole but its
    `=` or `:` is on the line after it (`db.password\` then `=hunter2`), that value is sent as
    written, as in 1.7.6. A value that opens a multi-line string with three double or three single
    quotes (TOML's `password = """`) is redacted with every line up to and including the closing
    quotes. In YAML, after a secret key with no value on its line (`password:`, `api_keys:`), the
    sequence items below it (`- ...`, the `-` kept) and plain values on the lines below it are
    redacted; when the first line below is itself a key (a mapping, such as an OpenAPI property's
    `type:`), the lines are read one by one as before. A secret setting left in a comment
    (`#spring.datasource.password=...`, `# password: ...`, `; password = ...`,
    `# export API_KEY=...`, behind `#` or `;`, and `!` in a `.properties` file) has its value
    redacted when that value is one word or one quoted string, with a ` # comment` of its own after
    it or not; the marker, the key and that comment are kept (in a `.properties` file the text after
    the value is part of the value, and is redacted with it). A comment whose value is several
    words, a note, is sent as written. Redacted lines stay on their own lines, so line numbers never
    move. A line with nothing to redact is sent exactly as written.
    Placeholders such as `${DB_PASSWORD}` are kept: they reveal nothing. A default written into one
    (`${DB_PASSWORD:hunter2}`, `${DB_PASSWORD:-hunter2}`, and without a colon, as shells and Docker
    Compose write it, `${DB_PASSWORD-hunter2}` or `${DB_PASSWORD=hunter2}`) and text glued to one
    (`${PREFIX}hunter2`) are redacted when they are four characters or longer, as a quoted value
    is. A default without a colon is read only after an upper-case environment variable's name, so
    `${jwt-secret}` stays a name, and never in a JavaScript template string in code, where
    `${A-B}` is code. Kept: a GitHub Actions expression (`${{ secrets.TOKEN }}`) whole; an editor
    variable's name (`${env:TOKEN}`, `${input:token}`), while a default after the name is redacted
    as above (Log4j2's `${env:TOKEN:-...}`, the Serverless Framework's `${env:TOKEN, '...'}`); the
    message of `${1:?message}`; and a path in or after a placeholder that names a folder or a file
    (`${WORK_DIR}/token.json`, `${KEY_FILE:-/etc/app/key.pem}`). A path after any other
    placeholder is redacted, as a webhook address carries its token in the path.

  A value that matches none of these (for example `DATABASE_DSN = "..."` written in code, or a
  quoted password of three characters) is sent as written. `preview_spec_check` shows you exactly
  what would go.

### CI triage

A CI triage sends one request per distinct failure of the run — a failed step, counted once
however many jobs of a matrix failed the same way. A failed job whose log was not read (it could
not be downloaded, or reading stopped after 40 jobs or 50 MB of logs) sends nothing: it is listed
as not checked. Each request holds:

| Sent | Details |
|---|---|
| Facts about the run | sentences computed on your machine: the failed step, its kind and exit code, the job names, how long the step ran and its longest silence, whether GitHub reports the job cancelled or stopped at its time limit, the other jobs of the run where the same step passed, the failing tests and the files the errors name, the paths of the files the change edits, a name, or up to 80 characters of a string's text, that an error line holds and the change adds or removes (read from the change's redacted lines, never from a secret file), whether a later attempt passed, and how the same job fared in the last run on the default branch before this one |
| Candidate error lines | up to 30 lines of the failed step's output that look like errors, each at most 240 characters; for a Python traceback, also where it was in your project's own code, as `path:line in function: source line` |
| The end of the failed step's output | at most 5,000 characters |
| An excerpt of the change under test | at most 5,000 characters of its diff, starting with the files the errors name |
| Fixed questions | identical for every failure; the question about which line states the error is asked when two or more lines are offered, and its options are those lines |

From a GitHub Actions log, only the output of the steps that failed is used; a log from another
CI that has no step markers is read as one step. From a JUnit report, the failed test cases'
names, messages and the last 25 lines of each failure's text are used.

Log lines are cleaned before they are sent, and before they are shown to the agent. The
cleaning:

- colour codes, the timestamp GitHub Actions writes at the start of each line (read first, to
  work out how long the step ran), control characters and invisible characters are removed;
  timestamps in other formats, or inside a line, stay;
- the CI runner's workspace path is removed, so paths are relative to the repository, for the
  default workspaces of GitHub Actions (a container job's `/__w/<a>/<b>/` included), self-hosted
  GitHub runners and Azure Pipelines agents (`<install folder>/_work/<a>/<b>/`, on Windows
  `X:\...\_work\<a>\<b>\` too), Azure Pipelines' hosted agents, GitLab (Docker and shell
  executors), Jenkins, CircleCI, Travis CI, Buildkite and TeamCity (the runner's own `_actions`,
  `_temp` and `_tool` folders, and Azure Pipelines' `_tasks`, beside the workspace are not the
  workspace, so their paths are kept whole); in a log or JUnit report read from a file, the project
  folder is removed from the start of a path; any other home folder is shown as `<user>`;
- email addresses are replaced by `<email>`;
- secret-looking values are redacted: the shapes listed under spec drift, and in logs also
  bearer, basic and token authorization values, `_authToken=` lines, the password given to
  `docker`, `podman` or `helm login`, `.netrc` passwords, and any value written after `:` or `=`
  behind a name that contains password, passwd, secret, token, API key, access key, private key,
  client secret or credential.

The excerpt of the change is cleaned as well:

- a secret file is left out: `.env` and `.env.*` (other than `.example`, `.sample` and `.template`
  files) and any other `*.env` file (`prod.env`, `config/staging.env`), key and certificate files
  (`.pem`, `.key`, `.p12`, `.pfx`, `.jks`), `.kdbx`, SSH private keys (`id_rsa`, `id_ed25519`,
  `id_ecdsa`, `id_dsa`), `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `kubeconfig`, Terraform
  state and variable files, `credentials*.json` and service-account JSON files. Only its path is
  mentioned, with a note that its content is withheld;
- lines that only add or remove a comment are left out, in Python, shell, Ruby, YAML, TOML, Go,
  Rust, Java, Kotlin, Scala, JavaScript, TypeScript, C, C++, C#, Swift and PHP files;
- secret-looking values are redacted as in log lines.

jevmcp never adds the commit message, the pull request's title or its description to what it sends:
text an author wrote about their own change steers a verdict about it. A CI step that prints one of
them (a commit-message lint, `git log`) puts it in its log, and that log line is sent like any other.

**Reading GitHub.** To triage a GitHub Actions run, jevmcp reads it with your own `gh` login. It
uses GET requests to GitHub's REST API only, and only for a repository that is a GitHub remote of
the project. It reads the run, its jobs, the failed jobs' logs, the annotations of a failed job
that was cancelled or timed out (where GitHub says a time limit was reached), the repository's
record (for its default branch), the change under test, and the last completed run of the same
workflow on the default branch from before this run, with its jobs. For a pull-request URL it
first reads the pull request, to find its head commit, and the runs of that commit; the pull
request's title and description are never sent. For a scheduled or manual run, the change under
test is what changed since the last run of the workflow on the same branch that passed before
this run. Both of those earlier runs are the branch's own: a pull request's run, a fork's
included, is never used as either. `gh` runs without the TypeSafe key in its environment. Reading GitHub is free: only the
cleaned excerpts above go to TypeSafe, and only when `triage_ci_failure` runs.

**Log files from another CI** are read only when they are inside your project or in the server's
private inbox. Symbolic links, files under any `.git` folder (a vendored repository's too), secret
files, other users' files, the server's own results folder and other sessions' temporary folders
are refused, on Windows as on Linux and macOS.

### Code audit

A code audit sends one request per reviewed rule and each unit of code it applies to; a pair the
first answer does not settle is sent up to twice more, unchanged. Each request holds:

| Sent | Details |
|---|---|
| The rule | the `rule` of a reviewed entry in your rule map, at most 1,200 characters |
| One unit of code | a function, class or block of one file, at most 2,600 characters, with its path relative to your project and its line numbers |
| Two fixed questions | identical for every request |

Which code can be sent:

- only files git tracks or would commit, so files git ignores — build output, a local `.env`,
  credentials — are left out. In a git repository where git is not installed, which files git
  ignores cannot be told, so no code is read at all, and neither is any in a repository git
  cannot read (dubious ownership, a broken index, a worktree whose repository folder is gone): the
  audit stops with git's message. In a folder that is not a git repository there
  is nothing to ignore: every code file outside the skipped folders (`node_modules`, `.venv`,
  `build` and the like) can be read, and secret files are still skipped;
- only code files that a reviewed rule's `scope` matches, and by default only the units that the
  change under test touches;
- symbolic links, files over 1.5 MB and secret files (the files listed under "What is never
  sent") are skipped.

The code is cleaned before it is sent:

- comments and docstrings are removed, in the languages listed under spec drift, and each unit is
  sent with its path and the lines of the file it came from; other files, such as shell, Ruby, PHP
  or SQL, are sent as written;
- secret-looking values are redacted, as for spec drift;
- a rule about comments or docstrings (`keep_comments` in the rule map) is the one exception: its
  units are sent with their comments, in requests of their own, with links replaced by `<url>`
  and email addresses by `<email>`. Every other rule's request gets the unit without comments.

`preview_code_audit` reports, before anything is sent, how many units and files would go, the
bytes of code, and their share of every file git tracks. The MCP server refuses an audit of more
than 400 requests (its default cap), or of every unit (`all: true`), until the count is confirmed;
the command line refuses more than `--max-requests` (500 by default).

## What is never sent

- Secret files — `.env`, `.env.*` and other `*.env` files such as `prod.env` (templates such as
  `.env.example` are read as configuration),
  key and certificate files (`.pem`, `.key`, `.p12`, `.jks`, `.pfx`), `.kdbx`, SSH private keys
  (`id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`), `.npmrc`, `.pypirc`, `.netrc`,
  `.git-credentials`, `kubeconfig`, Terraform state and variable files (`.tfstate`, `.tfvars`),
  `credentials*.json` and service-account JSON files. A spec-map entry pointing at one is
  refused, and a code audit never reads one, whatever the case of its name (`.ENV`, `ID_RSA`,
  `server.PEM`: a disk that ignores case, as macOS does by default, opens `.env` for `.ENV`); a
  CI triage leaves one out of the change excerpt and refuses one as a log when its name is
  written as above, in lower case.
- Anything outside your project folder: a map entry pointing there is refused. The one exception
  is a CI log you save in the server's private inbox for a triage.
- For spec drift, code that no requirement points at: an entry in the map, or, with
  `spec_drift.py --docs` and no map, a name, an upper-case constant or a route that the sentence
  itself names.
- The commit message, the pull request's title and its description, as anything jevmcp adds itself
  (a log line that prints one is sent like any other log line).
- Your API key to anyone but TypeSafe. It is never placed in the model's context, a tool's
  arguments or a tool's results. In Claude Code it is kept out of settings files (macOS Keychain,
  or `~/.claude/.credentials.json` elsewhere) and passed only to the jevmcp server process. In
  Codex it comes from your environment (`TYPESAFE_API_KEY`), which Codex's own shell tool can also
  see. The MCP server never reads a key from the project it checks.

## See it before it is sent

`preview_spec_check` (MCP) or `--dry-run --show-payload` (command line) prints exactly what a check
would send, and sends nothing. `preview_ci_triage` shows the exact state of each failure and
returns a snapshot id; `triage_ci_failure` with that snapshot sends exactly what was shown.
`preview_code_audit` shows the exact states of the first three requests, and
`code_audit.py --dry-run --show-payload` prints all of them.

The skills ask for your consent before the first send of each kind of data in a project, and ask
again for each kind. For CI logs and for source code, only you can give that consent, in the
conversation: a file in the repository never counts as your consent.

## What is stored locally

- MCP server: the results of the last run per family and project, including exactly what was
  sent, in a private temporary folder of the server process (readable only by you), removed when
  the server stops.
- MCP server, CI triage: each preview's snapshot (the failures and the change as they were read,
  before the change is cut and cleaned) and the states it showed, and `gh`'s cache folder, in the
  same private folder, removed when the server stops.
- MCP server, CI triage: the inbox, a private folder (mode 0700) for log files you save for a
  triage, removed with everything in it when the server stops.
- Command line: the results, including the exact code sent, in `drift.json` in the folder you run
  it from (or `--out FILE`); `--dry-run --out FILE` writes the plan of what would be sent.
- Command line, CI triage: the results, including log excerpts, in `triage.json` in the folder you
  run it from (or `--out FILE`); `--dry-run --out FILE` writes the states that would be sent.
  `gh`'s cache folder is a temporary folder that is removed once the run has been read.
- Command line, code audit: the results in `audit.json` in the folder you run it from (or
  `--out FILE`).
- The spec map and the rule map you create, in your project — you decide whether to commit them.
- Answers from earlier runs of all three families, in `~/.cache/jevmcp/verdicts.json`
  (`$XDG_CACHE_HOME` is respected), so a request that has not changed is not paid for twice. It
  holds a SHA-256 digest of each request and the model's answers - never your code, your logs or
  your spec text, never your API key. Delete the file to clear it, or pass `--no-cache` to ignore
  it.
- The Python dependencies, in uv's cache.
