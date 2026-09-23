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

- **Comments and docstrings removed** in Python, Java, JavaScript/TypeScript and the other
  C-family languages (Kotlin, Scala, Groovy, Go, C#, C/C++, Rust, Swift). Other files — for
  example PHP, Ruby or shell, which can only be paired by line range — are sent as written.
- **Secret-looking values redacted**:
  - everywhere, by shape: Stripe, GitHub, Slack, Google and OpenAI/Anthropic keys, GitLab, npm,
    PyPI and HashiCorp Vault tokens, Slack webhook addresses, AWS access key IDs, JWTs, PEM
    private keys, and credentials inside URLs;
  - in code, quoted values whose name contains `password`, `passwd`, `passphrase`, `pass` (as a
    word: `DB_PASS`, `userPass`), `secret`, `token`, `api key`, `private key`, `credential` or
    `access key`;
  - in configuration files (`.properties`, YAML, TOML, INI, `.env` templates) — however they are
    paired, quoted or not — values whose key has one of those names, or whose last part is `key`
    (`jwt.key`, `encryption-key`, `encryptionKey`) or `dsn`, and signing keys and client secrets.
    Placeholders such as `${DB_PASSWORD}` are kept: they reveal nothing.

  A value that matches none of these (for example `DATABASE_DSN = "..."` written in code) is sent
  as written. `preview_spec_check` shows you exactly what would go.

### CI triage

A CI triage sends one request per distinct failure of the run — a failed step, counted once
however many jobs of a matrix failed the same way. Each request holds:

| Sent | Details |
|---|---|
| Facts about the run | sentences computed on your machine: the failed step, its kind and exit code, the job names, the failing tests and the files the errors name, the paths of the files the change edits, whether a later attempt passed, and how the same job fared on the default branch |
| Candidate error lines | up to 30 lines of the failed step's output that look like errors, each at most 240 characters |
| The end of the failed step's output | at most 5,000 characters |
| An excerpt of the change under test | at most 5,000 characters of its diff, starting with the files the errors name |
| Fixed questions | identical for every failure; the question about which line states the error is asked when two or more lines are offered, and its options are those lines |

From a GitHub Actions log, only the output of the steps that failed is used; a log from another
CI that has no step markers is read as one step. From a JUnit report, the failed test cases'
names, messages and the last 25 lines of each failure's text are used.

Log lines are cleaned before they are sent, and before they are shown to the agent. The
cleaning:

- colour codes, timestamps, control characters and invisible characters are removed;
- the CI runner's workspace path is removed, so paths are relative to the repository, and any
  other home folder is shown as `<user>`;
- email addresses are replaced by `<email>`;
- secret-looking values are redacted: the shapes listed under spec drift, and in logs also
  bearer, basic and token authorization values, `_authToken=` lines, the password given to
  `docker`, `podman` or `helm login`, `.netrc` passwords, and any value written after `:` or `=`
  behind a name that contains password, passwd, secret, token, API key, access key, private key,
  client secret or credential.

The excerpt of the change is cleaned as well:

- a secret file is left out: `.env` and `.env.*` (other than `.example`, `.sample` and `.template`
  files), key and certificate files (`.pem`, `.key`, `.p12`, `.pfx`, `.jks`), `.kdbx`, SSH private
  keys (`id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`), `.npmrc`, `.pypirc`, `.netrc`,
  `.git-credentials`, `kubeconfig`, Terraform state and variable files, `credentials*.json` and
  service-account JSON files. Only its path is mentioned, with a note that its content is
  withheld;
- lines that only add or remove a comment are left out, in Python, shell, Ruby, YAML, TOML, Go,
  Rust, Java, Kotlin, Scala, JavaScript, TypeScript, C, C++, C#, Swift and PHP files;
- secret-looking values are redacted as in log lines.

jevmcp never adds the commit message, the pull request's title or its description to what it sends:
text an author wrote about their own change steers a verdict about it. A CI step that prints one of
them (a commit-message lint, `git log`) puts it in its log, and that log line is sent like any other.

**Reading GitHub.** To triage a GitHub Actions run, jevmcp reads it with your own `gh` login. It
uses GET requests to GitHub's REST API only, and only for a repository that is a GitHub remote of
the project. It reads the run, its jobs, the failed jobs' logs, the change under test, and the
latest run of the same workflow on the default branch. `gh` runs without the TypeSafe key in its
environment. Reading GitHub is free: only the cleaned excerpts above go to TypeSafe, and only when
`triage_ci_failure` runs.

**Log files from another CI** are read only when they are inside your project or in the server's
private inbox. Symbolic links, `.git`, secret files, other users' files, the server's own results
folder and other sessions' temporary folders are refused.

### Code audit

A code audit sends one request per reviewed rule and unit of code. Each request holds:

| Sent | Details |
|---|---|
| The rule | the `rule` of a reviewed entry in your rule map, at most 1,200 characters |
| One unit of code | a function, class or block of one file, at most 2,600 characters, with its path relative to your project and its line numbers |
| Two fixed questions | identical for every request |

Which code can be sent:

- only files git tracks or would commit, so files git ignores — build output, a local `.env`,
  credentials — are left out;
- only code files that a reviewed rule's `scope` matches, and by default only the units that the
  change under test touches;
- symbolic links, files over 1.5 MB and secret files (`.env` and `.env.*`, key and certificate
  files, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`) are skipped.

The code is cleaned before it is sent:

- comments and docstrings are removed, in the languages listed under spec drift, and line
  numbers are kept; other files, such as shell, Ruby, PHP or SQL, are sent as written;
- secret-looking values are redacted, as for spec drift;
- a rule about comments or docstrings (`keep_comments` in the rule map) is the one exception: its
  units are sent with their comments, in requests of their own, with links replaced by `<url>`
  and email addresses by `<email>`. Every other rule's request gets the unit without comments.

`preview_code_audit` reports, before anything is sent, how many units and files would go, the
bytes of code, and their share of every file git tracks. The MCP server refuses an audit of more
than 400 requests (its default cap), or of every unit (`all: true`), until the count is confirmed;
the command line refuses more than `--max-requests` (500 by default).

## What is never sent

- Files named `.env` or `.env.*` (templates such as `.env.example` are read as configuration),
  key and certificate files (`.pem`, `.key`, `.p12`, `.jks`, `.pfx`, `id_rsa`...), and anything
  outside your project folder — a map entry pointing at one is refused. The one exception to
  "outside the project" is a CI log you save in the server's private inbox for a triage.
- For spec drift, code that no requirement in the map points at.
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
