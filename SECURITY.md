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

- The TypeSafe API key is read only from the client's settings (Claude Code's credential store),
  from the `TYPESAFE_API_KEY` environment variable, or from `typesafe.env` in the plugin's data
  folder — never from this repository or from the project being checked.
- The key is never placed in the model's context, in tool arguments or in tool results.
- Code is sent to `api.typesafe.ai` only when a check runs, after the user's consent, with
  comments removed and secret-looking values redacted. Files such as `.env`, key and certificate
  files, and anything outside the project are refused. See each plugin's `PRIVACY.md`.
