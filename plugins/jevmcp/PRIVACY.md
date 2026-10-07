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
  range — are sent as written. A code file's language is known by its suffix in lower case, so
  `UPPER.PY` or `Main.JAVA` is not indexed and keeps its comments and docstrings.
- **Secret-looking values redacted**:
  - everywhere, by shape: Stripe, GitHub, Slack, Google and OpenAI/Anthropic keys, GitLab, npm,
    PyPI and HashiCorp Vault tokens, Slack webhook addresses, AWS access key IDs, JWTs, PEM
    private keys, and credentials inside URLs. A PEM private key written in code as joined string
    literals (Python's `\` continuations, Java's or C#'s `+`, PHP's `.`), under any name, is hidden
    whole when what stands between its BEGIN and END markers is only what a key holds there: base64
    with a run of 20 or more of its characters, `Proc-Type:` and `DEK-Info:` lines, quotes, `\n`
    escapes, XML's line breaks (`&#10;`, `&#13;`, `&#xA;`, `&#xD;`) and the joins. When another
    BEGIN marker with no END marker of its own stands before such a key (a key cut short, a marker
    constant, a comment), everything from that earlier marker on is hidden with the key, as 1.7.8's
    shape hid it; a BEGIN or END marker in a secret-named variable's value or in a connection-string
    password (`Server=x;Password=-----BEGIN ...`) pairs with nothing, as in 1.7.8, where that value
    was redacted first, so the code after it is sent.
    Code between a
    BEGIN marker string and an END marker string is not hidden by this rule, nor by the line range
    rule below (a name between the literals, as in
    `"-----BEGIN ...\n" + privateKeyBase64Encoded + "\n-----END ..."`, makes it code, not a key, when
    the BEGIN marker's literal closes right after the marker and its line breaks; one that goes on
    with key text first, then a name, reads as a key); the PEM shape rule still sends everything from a BEGIN marker to the next END
    marker as one `<redacted>`, as in 1.7.8, so `startswith("-----BEGIN ...") and
    endswith("-----END ...")` on one line is sent as `startswith("<redacted>")`, and marker
    constants on lines of their own are sent as `BEGIN = "<redacted>"`, and nothing up to the END
    marker is sent. Under a secret-named variable, a key whose lines are joined with code
    (`+ System.lineSeparator() +`, or `key += "..."` a line at a time) is sent but for its BEGIN
    line, as in 1.7.8. An armored PGP private key block (`-----BEGIN PGP PRIVATE KEY BLOCK-----` to
    `-----END PGP PRIVATE KEY BLOCK-----`) is read as a PEM private key, by this rule and by the
    rules below for configuration files, a line range, the 2,600-character cap and a claim's share.
    It is written as a key with its checksum line (`=AbCd`) and with `Version:` and `Comment:`
    headers, each on a line of its own (indented or not, behind a joining `+`, `.` or `,` and one
    quote or not) or after a `\n` escape in a one-line string, where its text runs to the next
    backslash or quote; another header (`Hash:`, `Charset:`) or other text on its lines makes it
    code between markers. A PGP public key block is sent as written;
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
    kind of quote along with a space, or starts with a quote (except in a C# verbatim string on one
    line, `@"..."`, and `$@"..."` or `@$"..."` when it holds no `{`, where any value of four
    characters or more is redacted whole, quotes of the other kind, backticks, spaces and a leading
    `""` included, as in `@"it's a secret"` and `@"""quoted"""`; one that spans lines, or a
    `$@"..."` that holds `{`, follows the general rule), a value set through a quoted or lower-case subscript
    (`settings['token'] = "..."`, `token[i] = "..."`), and the next value on a line after a `case`
    label, an `if` or `for` line, or a secret word inside a quoted value that no `:` or `=` follows
    (`type="password" autoComplete="new-password"`, `if token: msg = "..."`). A quoted text that
    ends in a secret word and a `:` or `=` (`label="Password:" placeholder="..."`,
    `"Token: " + token + " refreshed"`) has what follows it on the line redacted, up to the next
    quote, as in 1.7.6. A code file that starts with a UTF-8 byte-order mark is read as one without
    it, so a declaration on its first line is redacted too;
  - in code and configuration files alike, a password in a JDBC URL or a connection string: a
    `password=`, `passwd=` or `pwd=` value, in any case (`?user=x&password=...`, `;password=...`,
    `Server=db;Password=...;` or `Server=db; Password=...`, `UID=x;PWD=...`, libpq's
    `host=db user=x password=...`), when it comes right after `?`, `&`, `;`, a quote or a
    backtick, or after another `name=value` (ending in `;` or not) and a space, with no space
    around the `=`. That earlier value is a word with no space, `=`, `;`, `&` or quote that does not
    end in `,`, `(` or `)` (`Data Source=db,1433; Password=...`,
    `Server=(localdb)\MSSQLLocalDB; Password=...`, `port=5432,5433 password=...`), one word in
    parentheses (`Server=(local); Password=...`) or a single-quoted value (libpq's
    `dbname='app' password=...`). A `pwd=` value written in plain quotes (`Pwd='...'`, `PWD="..."`)
    is sent as written; `Password='...'` and `passwd='...'` are redacted as the quoted values above
    are, and the escaped form (`Pwd=\'...\'`) as below. The key is kept, and the value is redacted
    unless the whole of it has the shape
    of a placeholder or a variable (`{pw}`, `{{pw}}`, `<password>`, `%s`, `%(pw)s`, `%v`, `%DB_PASS%`,
    `$1`, `$DB_PASS`, `$cfg.pw`, `$env:DB_PASS`, `$(DB_PASS)`, `$(cat file)`, Ruby's and Elixir's
    `#{pw}`, Swift's `\(pw)`, Ruby's `%{pw}` and `%<pw>s`, a mask `*****`, a
    regular expression's group such as `(.*)` or `(\S+)`, or a regular expression with no group that
    is made only of `.`, escapes (`\w`, `\\d`) and character classes, each with a quantifier or not,
    and whose last part is an escape or a class with a quantifier, that class holding a range, an
    escape or a leading `^`, as `\w{8,}`, `[A-Za-z0-9]+` and `.+\d+` are; one that holds a literal
    character, an anchor, an escaped sign or `|`, or whose last part has no quantifier or is `.`,
    is redacted, as `abc[0-9]+`, `[a-z]+$`, `\w+\.\w+`, `.+\d`, `.{8,}` and `[Hunt3r]+` are),
    with `\n` or punctuation after it or not
    (`password=***,`), or is a `{...}`, `#{...}`, `<...>` or `$(...)` that a quote or a space cuts
    and that closes later on the line (`{ pw }`, `#{ENV['PW']}`, `<your password>`); `${...}` is
    kept and its default redacted, as below. A `pwd=` value that is an absolute path (it starts
    with `/`, `~/`, `X:\`, `X:/` or a UNC `\\`, and holds only letters, digits and
    `_.-~/\@+%,`) is the shell's working folder and is sent as written
    (`ENV HOME=/home/you PWD=/home/you`, `"PWD=/srv/app"`), except right after a `;`, where it is
    read as ODBC's password, or after `?` or `&`, a URL query's password, and redacted
    (`UID=x;PWD=/Str0ng;`, `?pwd=/srv/app&ssl=1`, and so also `export HOME=/root; PWD=/srv/app`). A password that only starts like one of those, or with `@` or `:`,
    is redacted (`%40dm1n%21x`, `$uperS3cret!`, `*Hunter22*`, `(Hunter22)`, `#Hunter22`,
    `@dmin2024`, `****1234`), and so is a `{`, `#{` or `<` value that a `;` or `&` cuts
    (`{Hunter22;`, `#{Hunter22;`), even when a `}` or `>` follows later on the line, and ODBC's
    brace-quoted value with a `;` in it, spaces, `&`, `'`, backticks and an escaped `\"` included
    (`PWD={Str0ng;Pass}`, `PWD={My Str0ng;Pass}`, `PWD={Hu&nter;22}`, `PWD={It's;Str0ng}`,
    redacted whole). A brace-quoted value may be sent whole or in part when it holds a bare,
    unescaped `"`, or a raw `{` (`PWD={a{b;c}` reads `PWD=<redacted>;c}`; `PWD={a;b{c}` is sent
    whole), or an `&` and no `;` (`PWD={Hu&nter22}` is sent whole; `PWD={Hunt&er22}` reads
    `PWD=<redacted>&er22}`). An unquoted value ends at `&`, a space or a quote, as a URL query's
    value does, after a `;` too, and what follows that end is sent (`Password=Hunter22 x;` reads
    `Password=<redacted> x;`, `Password=Hunt3r"x;` reads `Password=<redacted>"x;`); when fewer than
    four characters stand before that end, the value is sent as written (`Password=P&ssw0rd!;`,
    `Password=ab" cdefgh;`). When a `;` and a space stand between two passwords in one string,
    the second may be sent as written (`Server=db;Password=abcd; Pwd=Hunter22;`). A value in
    escaped quotes, as written inside a source string or a JSON file (`Password=\"...\"`,
    `password=\'...\'`), is one value: it may hold `;`, spaces, the other kind of quote, backticks
    and ADO.NET's doubled quote (`\"Hunt\"\"er\"`); the escaped quotes are kept and what is inside
    them is redacted (`Password=\"<redacted>\"`). A whole placeholder inside them is kept
    (`\"{pw}\"`, `\"<password>\"`, and `${...}` keeps its name with any default redacted), but a
    `<...>`, `{{...}}` or `#{...}` there that holds `;` or `&` is redacted, and so is a command
    substitution with arguments (`\"$(cat file)\"`, kept unquoted), and a value under four
    characters (an empty `\"\"` too) is sent as written, as unquoted values are. Code that builds
    the quotes with the string's own quote (`"password=\"" + pw + "\""`) is sent as written; built
    with the other kind of quote, it may be redacted. A password whose whole value has the shape of
    a placeholder or a variable is sent as written (`{Hunter22}`, as ODBC quotes a password with no
    `;`, `#{Hunter22}`, `%{Hunter22}`, `\(Hunter22)`, `<Hunter22>`, `$uperS3cret`, `$ecret.Pass`,
    `%NAME%`), and so is one in braces that a space cuts, with no `;` (`PWD={Str0ng Pass}`, read
    as `{ pw }` is). A keyword argument
    (`connect(host=h, password=pw)`), a statement (`foo(a=1); password=x`, `x=f(a); password=x`)
    and a password after a value that holds a space inside braces (`Driver={SQL Server}; PWD=...`)
    or ends in `)` without being one word in parentheses (`Server=f(a); Password=...`) are sent as
    written;
  - in configuration files (`.properties`, YAML, TOML, INI, `.env` templates) — however they are
    paired, quoted or not — values whose key has one of those names, or whose last part is `key`
    (`jwt.key`, `encryption-key`, `encryptionKey`) or `dsn`, and signing keys and client secrets.
    A file is a configuration file by its suffix (`.properties`, `.yml`, `.yaml`, `.toml`, `.ini`,
    `.cfg`, `.conf`, `.env`), in any letter case (`application.YML`, `settings.TOML`), or by a
    template's name, `env.example` in any letter case too (`ENV.EXAMPLE`); a name that starts or
    ends with `.env` in upper or mixed case (`.ENV.EXAMPLE`, `prod.ENV`) is refused as a secret
    file.
    That includes a quoted key (`"password": ...`), a value that starts with `|` or `>`
    (`password=>Xk9q`, `token: |abc`), every line of a YAML block value (`password: |`, a value that
    is only `|` or `>`, with `-`, `+` or a digit and a `# comment` after it or not), and in a
    `.properties` file a key and value separated by spaces (`db.password hunter2`) and every line of
    a value continued with a backslash. A line that continues a value is read as a setting of its
    own only in the `key=value` or `key: value` form, so `password=...` on the next line of a JDBC
    URL is redacted, as in 1.7.6 (a placeholder there, `password=${DB_PASSWORD:hunter2}`, loses its
    default as below), while words there (`password to continue`) are sent as written; a line that
    continues a key (after `db.\` or a lone `\`) is read as a setting in every form. When a key is
    whole but its `=` or `:` is on the line after it (`db.password\` then `=hunter2`), that value is
    sent as written, as in 1.7.6. A value that opens a multi-line string with three double or three
    single quotes (TOML's `password = """`) is redacted with every line up to and including the
    closing quotes. In YAML, after a secret key with no value on its line (`password:`,
    `api_keys:`), the sequence items below it (`- ...`, the `-` kept) and plain values on the lines
    below it are redacted; a quoted item is an item even when it holds a colon and a space, also
    after a tag or an anchor (`- "admin: x"`, `- 'a: b'`, `- !!str "admin: x"`, `- &a "admin: x"`).
    When the first line below is itself a key (a mapping, such as an OpenAPI property's `type:`): an
    unquoted `key:`, or a quoted key followed by `:`, after a tag or an anchor too
    (`- !!str key: v`), the lines are read one by one as before. A `#` comment line among the lines
    below such a key, at any column, does not end its value: the items and values after it are still
    redacted, and the comment line is read as a line of its own (a commented-out setting there,
    `# password: x`, has its value redacted, as below; any other comment, a commented-out item or
    value such as `# - sk-old...` or `#   hunter22` included, is sent as written, as in 1.7.7). A
    `;` line is not a comment in YAML: one indented deeper than the key is read as part of the value
    and redacted; one at the key's column or to its left ends the value, and what follows is read
    line by line. A placeholder there is read as on the key's line, so `- ${API_KEY}`,
    `${GOOGLE_SECRET}` and `- ${{ secrets.TOKEN }}` are kept, a default written in one or text glued
    to one is redacted (`${DB_PASS:hunter2}` is sent as `${DB_PASS:<redacted>}`), a quoted
    placeholder, or one after a tag or an anchor, is redacted whole, as `password: "${KEY}"` is, and
    a lone `-` is sent as written. In a YAML or TOML file read whole or by a line range, a value that opens a list or a table on
    its key's line and goes on below it (TOML's `api_keys = [` or YAML's `api_keys: [`, then one
    value a line) has every line below it with text on it redacted, its indentation kept, up to and
    including the line that closes it (brackets counted line by line, leaving out quoted strings
    and comments); in an INI, `.cfg`, `.conf`, `.properties` or `.env` file such a value is a
    string, and only its own line is redacted. A comment there is read as the file's format reads
    it: in TOML, `#` to the line's end wherever it starts outside a string; in YAML, `#` at the
    start of a line or after a space, a quoted string, `,` or a bracket, while a `#` right after
    an unquoted character is part of the value (`P#ssw0rd`, `k#1`). In YAML a quote opens a string
    only where a value may start (the line's start, after a space, `,`, `:`, `[` or `{`), so the
    apostrophe of an unquoted `o'neil` opens none, and `''` inside a single-quoted item is an
    apostrophe in it (`'it''s ] one'` closes no list). So a value that closes on its key's line
    (`credentials: {user: app, password: p#ssw0rd}`) redacts only that line. A quoted YAML string, or
    a TOML multi-line string (`"""`, `'''`), that goes on to the next line is not read as one string: a
    `]` or `}` on one of its lines can end the redaction early. In a YAML file, after `key:`, a tag
    or an anchor before the value, each followed by a space, is passed over (`api_keys: &keys [`,
    `api_keys: !!seq [`, `private_key: !!binary |`): the list, map or block after it is redacted
    as without it, and the key's line reads `key: <redacted>`. So a value there that starts with
    `!` or `&`, holds a space and ends in `|` or `>` (`password: !Zq9w >`) is read as a block's
    header, and the deeper-indented lines below it are redacted with it. After `=`
    (`- MYSQL_PASSWORD=!Zq9w >`), with no space before the bracket (`&a[b`), and in a TOML file,
    a tag or an anchor is not read: only that line is redacted. In a YAML file a bracket after `=`
    opens nothing either (`- MYSQL_PASSWORD={Hunt3r22`): only that line is redacted. A list or map that is never
    closed is redacted to the end of what is read. A secret setting left in a
    comment (`#spring.datasource.password=...`, `# password: ...`, `; password = ...`,
    `# export API_KEY=...`, behind `#` or `;`, and `!` in a `.properties` file) has its value
    redacted when that value is one word or one quoted string, with a ` # comment` of its own after
    it or not; the marker, the key and that comment are kept (in a `.properties` file the text after
    the value is part of the value, and is redacted with it). A comment whose value is several
    words, a note, is sent as written. A PEM private key over several lines, from its `-----BEGIN`
    marker to the first `-----END` marker of a private key after it, has its inner lines redacted
    before these rules read the file: each inner line with text on it becomes `<redacted>`, keeping
    its indentation and its line-continuation backslashes, so every line stays where it was, a line
    range names the same lines, and a value that goes on after the END line (a `.properties`
    continuation, more text under a YAML key) is still read, and redacted, as part of that secret.
    When these rules redact the key line by line (a YAML `|` or `>` block under a secret key, a
    `.properties` continuation, and also a TOML multi-line string under a secret key or a plain
    value on the lines below a bare YAML secret key), it is sent as one `<redacted>` a line; when
    they leave it as written (under a key that is not secret-named, such as `content: |`, or in a
    TOML or INI value), it is sent whole as one `<redacted>`, as in 1.7.7. When they take only part
    of it (its BEGIN line as a quoted value, `private-key: "-----BEGIN ...`, of which 1.7.7 sent all
    but the first line), or a line range cuts it, it is sent as one `<redacted>` a line, its BEGIN
    and END lines and any text after END on that line included. In a code file too, a line range
    that starts or ends inside a PEM private key over several lines sends that key's lines in the
    range as `<redacted>` lines; there a key is one written as a key, as above, so this rule leaves
    code between a BEGIN and an END marker string as it is (a range that holds both markers is sent
    as the shape rule sends it). In any file, when the
    2,600-character cap on a file, a line range or a symbol, or the share of it a claim's code gets,
    would cut inside a PEM private key, every such key in that code is first hidden, so no part of
    it is sent: one over several lines as `<redacted>` lines, one written as a key on one line
    (BEGIN and END
    on the same line, its line breaks written as `\n` escapes or XML's `&#10;` or `&#xD;`, also in a
    file whose lines end in a lone `\r`) as one `<redacted>`, where 1.7.8 sent the part before the
    cut; other text between two markers on one line (a check that only names them,
    `startswith("-----BEGIN ...") and endswith("-----END ...")`) is not a key and is not hidden
    first. The
    hidden key is shorter, so more of the code after it can be sent. Redacted lines stay on their
    own lines, so line numbers never move, except that a PEM private key hidden whole is sent as one
    `<redacted>` line, as in 1.7.7. A line with nothing to redact is sent exactly as written.
    Placeholders such as `${DB_PASSWORD}` are kept: they reveal nothing. A default written into one
    (`${DB_PASSWORD:hunter2}`, `${DB_PASSWORD:-hunter2}`, and without a colon, as shells and Docker
    Compose write it, `${DB_PASSWORD-hunter2}` or `${DB_PASSWORD=hunter2}`) and text glued to one
    (`${PREFIX}hunter2`) are redacted when they are four characters or longer, as a quoted value is.
    A default without a colon is read only after an upper-case environment variable's name, so
    `${jwt-secret}` stays a name, and never in a JavaScript template string in code, where `${A-B}`
    is code. Kept: a GitHub Actions expression (`${{ secrets.TOKEN }}`) whole; an editor variable's
    name (`${env:TOKEN}`, `${input:token}`), while a default after the name is redacted as above
    (Log4j2's `${env:TOKEN:-...}`, the Serverless Framework's `${env:TOKEN, '...'}`); the message of
    `${1:?message}`; and a path in or after a placeholder that names a folder or a file
    (`${WORK_DIR}/token.json`, `${KEY_FILE:-/etc/app/key.pem}`). A path after any other placeholder
    is redacted, as a webhook address carries its token in the path.

  A value that matches none of these (for example `DATABASE_DSN = "..."` written in code, or a
  quoted password of three characters) is sent as written. A code or configuration file is read
  as UTF-8: one saved as UTF-16 (as Windows PowerShell 5.1 saves a `.ps1`) is sent with a NUL
  between its characters, and no secret in it is redacted. `preview_spec_check` shows you exactly
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
  default workspaces of GitHub Actions (a container job's `/__w/<a>/<b>/` and a hosted Windows
  workspace written with `/`, `D:/a/<r>/<r>/`, included; Git Bash's `/d/a/...` is left as written),
  self-hosted GitHub runners and Azure Pipelines agents (`<install folder>/_work/<a>/<b>/`, on
  Windows `X:\...\_work\<a>\<b>\` too; a runner installed two or more folders below `~/work` or
  `X:\a\` is taken for a GitHub-hosted one, so `_work/<a>/<b>/` stays in front of its paths), Azure
  Pipelines' hosted agents, GitLab (Docker and shell executors), Jenkins, CircleCI, Travis CI,
  Buildkite and TeamCity, each at the exact paths `docs/tools.md` lists (the runner's own
  `_actions`, `_temp` and `_tool` folders, and Azure Pipelines' `_tasks`, beside the workspace are
  not the workspace, so their paths are kept whole). No workspace path is removed inside a URL (a
  word with `://` in it before the path; a quote, a backtick, `,`, `;`, `(`, `)`, `{`, `}`, `<`,
  `>` and `|` also end a word, so a path after a URL in a JSON or `key=value` line is removed):
  `file:///home/you/work/r/r/x` is sent as `file:///home/<user>/work/r/r/x`. A container job's, a self-hosted runner's or a hosted Windows
  workspace written with `/` is removed only where a path starts (not right after a letter, a
  digit, `_`, `.`, `~`, `-`, `/`, or a one-letter word and `:`, a drive), and where its `<a>` and
  `<b>` hold no `:`, `;` or `,`: a workspace path that such a list separator ends
  (`-v /__w/r/r:/app`, `PATH=C:\actions-runner\_work\w\w;C:\...`, `PATH=D:/a/r/r;...`) is sent as written,
  as in 1.7.7, except that of a runner installed in `~/work` or `X:\a\`, or one folder below either:
  1.7.7 cut that one as a GitHub-hosted workspace (`-v /home/<user>/work/_work/r/r:/app` read
  `-v r:/app`), and it is now sent whole, a home folder shown as `<user>`, as it is when it ends at
  a space or at the end of the line, or is inside a URL. A path under another workspace that holds a
  `_work/<a>/<b>/` loses everything up to the first one, as a self-hosted runner's would, and so
  does a line that starts with `/workspace/` (with no such `_work/<a>/<b>/`, only `/workspace/`
  comes off, as in 1.7.7). In a log or JUnit report read from a file, the project folder is removed
  from the start of a path. The name of any other home folder is shown as `<user>`: after
  `/home/` or `/Users/`, and on Windows after a drive's `Users` folder in any letter case, written
  with `\`, `\\` or `/` (`C:\Users\x`, `c:\users\x`, `C:\\Users\\x` as a JSON string writes
  it, `c:/users/x`). Written with `/` after the drive, it is read only where the drive letter is
  not right after a letter, a digit or `_` (`-Ic:/users/x` is sent as written; `/Users/` in
  exactly that case is read anywhere). The name ends at its first space, in every form
  (`C:\Users\John Doe\x` is sent as `C:\Users\<user> Doe\x`). Git Bash's and
  WSL's lower-case `/c/users/x` and `/mnt/c/users/x` are sent as written;
- email addresses are replaced by `<email>`;
- secret-looking values are redacted: the shapes listed under spec drift (except that in a log
  line or a line of the change excerpt a `PWD=` path inside a home folder, a CI workspace or the
  project folder that follows another `key=value` or a quote,
  `ENV HOME=/home/you PWD=/home/you`, is redacted, as the folder's name is replaced by `<user>`
  or the folder is removed first; on its own, `PWD=/home/you` is sent as `PWD=/home/<user>`), and in logs also
  bearer, basic and token authorization values, `_authToken=` lines, the password given to
  `docker`, `podman` or `helm login`, `.netrc` passwords, and any value written after `:` or `=`
  behind a name that contains password, passwd, secret, token, API key, access key, private key,
  client secret or credential. The text after a line's leading marks (a diff's `+` or `-`,
  pytest's `>` or `E`, a line number, `|`, `:`, `.`, `#`) is read as the start of a line of code,
  so a declaration with a string type there is redacted (`+API_TOKEN: str = "..."`); behind a
  word, such as docker compose's `web-1  |`, it is not. A PEM private key, or an armored PGP
  private key block (`-----BEGIN PGP PRIVATE KEY BLOCK-----`), in a failed step's log,
  or in a JUnit failure's message or text, is redacted from its BEGIN marker to the next END
  marker of a private key, of any kind. When both are on one line, that span is sent as one
  `<redacted>`. Over several lines, a key starts where nothing but key text follows the BEGIN
  marker on its line (base64, spaces, quotes, backslash escapes, `-`, `:`, `+`, `,`) and that
  text, or one of the next two lines, ends with 20 or more base64 characters (quotes, a `\n`
  escape and punctuation after them aside) or is an encrypted key's `Proc-Type` line; then every
  line up to the END marker is sent as `<redacted>`, whatever it holds and whatever prefix it has
  (pytest's `E`, another job's line in between), and the text before the BEGIN marker and after
  the END marker is kept. Under a PGP block's BEGIN line, empty lines are not counted among
  those two lines, nor are its header lines `Version:`, `Comment:`, `MessageID:`, `Hash:` and
  `Charset:`, the name at the start of the line or after a space or a tab (so behind pytest's
  `E   ` too), with text after the colon or not; a header of another name, or one glued to a
  prefix (`|Version: x`), is counted, and so are such lines under a PEM key's BEGIN line. A PGP
  public key block or message is not touched. A marker is found also where control or invisible
  characters stand inside it, those removed from every line (a NUL, a backspace, a zero-width
  space; so in a UTF-16 log without a byte-order mark, read as UTF-8), or a colour code as it
  is removed from a line (`^[[0m`; in a JUnit report pytest's `#x1B[0m` too). A BEGIN marker that
  code or a message names, with no
  key body after it, starts no key. Not redacted: a key with no whole END marker after it (cut
  or truncated output, such as the lines pytest shows of a long diff without `-vv`; an END marker
  that Python's `pprint` splits in two inside a `bytes` value; key lines with no BEGIN line above
  them), a key each of whose lines carries other text after it (one JSON log line per key line),
  a key whose body does not start within two lines of its BEGIN line, and a key whose marker
  is broken across two lines (a form feed or another line-ending character inside it) or holds
  a tab, a no-break space or another visible character, in a log `#x1B[0m`, or an escape
  character right before one of its capital letters (removed with that letter). Lines that are no
  key
  are redacted too when a line ends with a BEGIN marker, one of the next two lines ends with 20
  or more base64 characters (a commit id) and an END marker follows further down.

The excerpt of the change is cleaned as well:

- a secret file is left out: `.env` and `.env.*` (other than `.example`, `.sample` and `.template`
  files) and any other `*.env` file (`prod.env`, `config/staging.env`), key and certificate files
  (`.pem`, `.key`, `.p12`, `.pfx`, `.jks`), `.kdbx`, SSH private keys (`id_rsa`, `id_ed25519`,
  `id_ecdsa`, `id_dsa`), `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `kubeconfig`, Terraform
  state and variable files, `credentials*.json` and service-account JSON files. Only its path is
  mentioned, with a note that its content is withheld;
- lines that only add or remove a comment are left out, in Python, shell, Ruby, YAML, TOML, Go,
  Rust, Java, Kotlin, Scala, JavaScript, TypeScript, C, C++, C#, Swift and PHP files;
- secret-looking values are redacted as in log lines, also in the code after a diff line's `+`,
  `-` or space, home folders are shown as `<user>` and email addresses as `<email>`;
- a workspace path is removed only where 1.7.7 removed it, and never inside a URL, for
  GitHub-hosted (on Windows only as written with `\`; a hosted path under `_actions`, `_temp`,
  `_tool` or `_tasks`, or of a runner installed in `~/work` or `X:\a\`, or one folder below
  either, is kept whole), Azure Pipelines' hosted agents, GitLab, Jenkins, CircleCI,
  Travis CI, Buildkite and TeamCity, and a line that starts with `/workspace/` (only that comes
  off). So a hosted path under `_tasks`, or of a runner installed in `~/work` or `X:\a\` or one
  folder below either (`/home/<user>/work/_work/<r>/<r>/...`, `X:\a\<x>\_work\<r>\<r>\...`), which
  1.7.7 cut, is now sent whole, its home folder shown as `<user>`. Any other container job's
  `/__w/<a>/<b>/` or self-hosted runner's `_work/<a>/<b>/` in a diff line is code, and is sent as
  written, as in 1.7.7.

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
  ignores cannot be told, so no code is read at all, and neither is any in a repository git cannot
  read (dubious ownership, a broken index, a worktree whose repository folder is gone): the audit
  stops with git's message. So it does at a `.git` folder in the folder or above it, up to any
  ceiling or mount point where git stops looking, that is not empty but that git does not take for a
  repository (its `HEAD` or `refs` gone, as a copy or sync tool that drops empty folders can leave
  it), as its ignored files cannot be told apart either. In a folder that is not a git repository
  there is nothing to ignore (an empty `.git` folder in it or above it does not make it one, nor
  does a repository above a `GIT_CEILING_DIRECTORIES` entry or, unless
  `GIT_DISCOVERY_ACROSS_FILESYSTEM` is set, past a mount point, as git does not look there): every
  code file outside the skipped folders (`node_modules`, `.venv`, `build` and the like) can be read,
  and secret files are still skipped;
- only code files that a reviewed rule's `scope` matches, and by default only the units that the
  change under test touches;
- symbolic links, files over 1.5 MB and secret files (the files listed under "What is never
  sent") are skipped.

The code is cleaned before it is sent:

- comments and docstrings are removed, in the languages listed under spec drift, and each unit is
  sent with its path and the lines of the file it came from; other files, such as shell, Ruby, PHP
  or SQL, are sent as written;
- secret-looking values are redacted, as for spec drift, and a PEM private key written as a key
  (as defined for spec drift) that the cut between two units splits has its lines sent as
  `<redacted>` in both units. A key with other text on its lines (a Kotlin or Scala `|` margin,
  one appended a statement per line as `sb.append("...")` or `key += "..."`, one in comment lines
  under a `keep_comments` rule) that the cut splits is sent, as in 1.7.8. A file saved as UTF-16
  is sent with no secret redacted, as for spec drift;
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
