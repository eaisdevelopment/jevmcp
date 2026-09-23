# Security

## Reporting a problem

Please do not describe a security problem in a public issue. Report it privately instead:
**Security → Report a vulnerability** on this repository
(<https://github.com/eaisdevelopment/jevmcp/security/advisories/new>). Only the maintainers see
the report.

Never include an API key — yours or anyone's — in an issue, pull request, log or screenshot. If a
key has been exposed, revoke it at <https://console.typesafe.ai> first.

## Supported versions

The latest release of each plugin.

## How the plugins handle secrets

- The MCP server reads the TypeSafe API key only from a `--key-file` it was registered with
  (an absolute path), the client's settings (Claude Code's credential store) or the
  `TYPESAFE_API_KEY` environment variable, or `typesafe.env` in the plugin's data folder — never
  from this repository or from the project being checked. The spec-drift command line, which you
  run yourself, also reads a `TYPESAFE_API_KEY=` line from the `.env` of the folder you run it in;
  the CI-triage and code-audit command lines never do.
- The key is never placed in the model's context, in tool arguments or in tool results.
- Data is sent to `api.typesafe.ai` only by the three tools that send — `check_spec_drift` (spec
  sentences with their paired code), `triage_ci_failure` (CI log excerpts with an excerpt of the
  change) and `check_code_rules` (units of source code) — after the user's consent for that kind
  of data, and cleaned first: secret-looking values redacted, and comments left out of code in
  the languages and cases `PRIVACY.md` lists (a rule about comments keeps them). Files
  such as `.env`, key and certificate files, and anything outside the project (apart from CI logs
  saved in the server's private inbox) are refused. See each plugin's `PRIVACY.md`.
- CI triage reads GitHub only with the user's own `gh` login, GET requests only, and only for a
  GitHub remote of the project; `gh` never receives the TypeSafe key. Text from CI logs is treated
  as data: it is cleaned before it is sent or shown, and the skills tell the agent never to follow
  instructions found in it.
