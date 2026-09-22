# jevmcp, for the agent reading this

You are probably here for one of three reasons. Each has a page that answers it in full; this
file is the map and the rules.

| You were asked to… | Read |
|---|---|
| install jevmcp, or a check failed with "no API key" | [plugins/jevmcp/docs/install.md](plugins/jevmcp/docs/install.md) |
| find out what it can do, or which tool to call | [plugins/jevmcp/docs/tools.md](plugins/jevmcp/docs/tools.md) |
| use it: set a project up, check after a change, run it in CI | [plugins/jevmcp/docs/how-to.md](plugins/jevmcp/docs/how-to.md) |
| work out why your client behaves differently (approvals, unattended runs, sandbox) | [plugins/jevmcp/docs/clients.md](plugins/jevmcp/docs/clients.md) |
| know exactly what leaves the machine | [plugins/jevmcp/PRIVACY.md](plugins/jevmcp/PRIVACY.md) |

## What this is

One plugin, `jevmcp`, installed once: `/plugin install jevmcp@jev` in Claude Code,
`codex plugin add jevmcp@jev` in Codex, after adding the marketplace
`eaisdevelopment/jevmcp`. It gives you one MCP server (`jevmcp`) and one skill (`spec-drift`).

Today the server offers four tools. Only the first sends anything anywhere:

- `check_spec_drift` — does the code still match the spec? Costs fractions of a cent, seconds.
- `validate_spec_map` — is the spec-to-code map complete and current? Free.
- `preview_spec_check` — exactly what a check would send. Free.
- `draft_spec_map` — write the map for a project that has none. Free.

They all work off the **spec map**: `spec_map.json` in the project, which pairs each sentence of
the spec with the code that implements it. `draft_spec_map` writes it; the user reviews it with
you; nobody writes it by hand. That pairing is why a check is cheap — each requirement is sent
with only the few lines that enforce it.

## Rules you do not break

1. **Never ask the user for their API key**, never accept it in chat, never put it in a command
   you run, never pass it as a tool argument. If a tool says no key is set, pass on the exact
   command from its error message and stop — the user runs it in their own terminal. `--set-key`
   refuses to run anywhere else, so trying will fail anyway.
2. **Get consent before the first check in a project.** `check_spec_drift` sends the spec
   sentences and their paired code to `api.typesafe.ai`. Say so, and say what it costs. The free
   tools need no consent. The user's own CLAUDE.md or AGENTS.md may already record that consent.
3. **`??` is not a pass.** It means the code shown cannot settle the claim: fix that entry of the
   spec map and check again.
4. **Never report "no drift" from a run that could not reach TypeSafe** (exit code 3, or a tool
   result that says the service was unavailable). Say the check did not run.
5. **Do not fall back to the command line inside a Codex session.** Codex's sandbox has no
   network, so the check silently finds nothing. The MCP server runs outside the sandbox; use the
   tools. See [clients.md](plugins/jevmcp/docs/clients.md).
6. **Do not change the questions or thresholds**, and do not call the TypeSafe API by hand: they
   are measured and pinned. Do not edit a reviewed map to make a check pass.

## If you are changing this repository

`plugins/jevmcp/scripts/*.py` are copies of the maintainers' working tree, kept byte-identical by
a test. Open an issue or a pull request describing the change rather than only editing the copy,
so it can be applied at the source. Everything user-visible — tool names, exit codes, key
sources — is asserted by tests, and the docs above are checked against the code.
