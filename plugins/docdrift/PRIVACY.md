# Privacy and data flow

docdrift runs on your machine. It has no server of its own, sends no telemetry, and keeps no
logs of your conversations.

## What leaves your machine

Only when a check runs — the MCP tool `check_drift`, or the command line without `--dry-run` —
and, per requirement being checked:

| Sent | Details |
|---|---|
| The spec sentence | as written in your spec map |
| The code paired with it | see below; file paths relative to your project |
| Computed values | arithmetic the tool worked out from the code, e.g. `15*60*1000 = 15 minutes` |
| Three fixed questions | identical for every requirement |

The code paired with a requirement is cleaned before it is sent:

- **Comments and docstrings removed** in Python, Java, JavaScript/TypeScript and the other
  C-family languages (Kotlin, Scala, Groovy, Go, C#, C/C++, Rust, Swift). Other files — for
  example PHP, Ruby, YAML or shell, which can only be paired by line range — are sent as written.
- **Secret-looking values redacted**:
  - everywhere, by shape: Stripe, GitHub, Slack, Google and OpenAI/Anthropic keys, AWS access key
    IDs, JWTs, PEM private keys, and credentials inside URLs;
  - in code, quoted values whose name contains `password`, `passwd`, `passphrase`, `secret`,
    `token`, `api key`, `private key`, `credential` or `access key`;
  - in configuration files, also values whose key ends in `key` or `dsn`, and signing keys and
    client secrets.

  A value that matches none of these (for example `DATABASE_DSN = "..."` written in code) is sent
  as written. `show_payload` shows you exactly what would go.

It goes to TypeSafe's API (`https://api.typesafe.ai/v1/systemone`) over HTTPS, authenticated with
your API key. TypeSafe's own terms and privacy policy govern what it does with requests:
<https://typesafe.ai>.

## What is never sent

- Files named `.env` or `.env.*` (templates such as `.env.example` are read as configuration),
  key and certificate files (`.pem`, `.key`, `.p12`, `.jks`, `.pfx`, `id_rsa`...), and anything
  outside your project folder — a map entry pointing at one is refused.
- Code that no requirement in the map points at.
- Your API key to anyone but TypeSafe. It is never placed in the model's context, a tool's
  arguments or a tool's results. In Claude Code it is kept out of settings files (macOS Keychain,
  or `~/.claude/.credentials.json` elsewhere) and passed only to the docdrift server process. In
  Codex it comes from your environment (`TYPESAFE_API_KEY`), which Codex's own shell tool can also
  see. The MCP server never reads a key from the project it checks.

## See it before it is sent

`show_payload` (MCP) or `--dry-run --show-payload` (command line) prints exactly what a check
would send, and sends nothing. The skill asks for your consent before the first check in a
project.

## What is stored locally

- MCP server: the results of the last check per project, including the code that was sent, in a
  private temporary folder of the server process (readable only by you).
- Command line: the results, including the exact code sent, in `drift.json` in the folder you run
  it from (or `--out FILE`); `--dry-run --out FILE` writes the plan of what would be sent.
- The spec map you create, in your project — you decide whether to commit it.
- The Python dependencies, in uv's cache.
