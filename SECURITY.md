# Security

## Reporting a problem

Please do not describe a security problem in a public issue. Instead, open an issue titled
**"Security contact request"** with no details, and a maintainer will reply with a private way
to send them.

Never include an API key — yours or anyone's — in an issue, pull request, log or screenshot. If a
key has been exposed, revoke it at <https://console.typesafe.ai> first.

## Supported versions

The latest release of each plugin.

## How the plugins handle secrets

- The MCP server reads the TypeSafe API key only from a `--key-file` it was registered with
  (an absolute path), the client's settings (Claude Code's credential store) or the
  `TYPESAFE_API_KEY` environment variable, or `typesafe.env` in the plugin's data folder — never
  from this repository or from the project being checked. The command line, which you run
  yourself, also reads a `TYPESAFE_API_KEY=` line from the `.env` of the folder you run it in.
- The key is never placed in the model's context, in tool arguments or in tool results.
- Code is sent to `api.typesafe.ai` only when a check runs, after the user's consent, with
  comments removed and secret-looking values redacted. Files such as `.env`, key and certificate
  files, and anything outside the project are refused. See each plugin's `PRIVACY.md`.
