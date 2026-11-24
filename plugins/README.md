# whitson PVT plugins for Claude Code and Codex

The skill in `wpvt/skills/` is a copy. Its source is
`whitson_pvt_sdk/.agents/skills/whitson-pvt/SKILL.md`, the skill the package ships; edit that file and
run `just plugins-sync`. `just lint` fails while the copy differs.

The `wpvt` plugin gives an agent host two things:

- the `wpvt` MCP server, which runs `wpvt mcp` over stdio: your deployment's MCP tools with your
  `wpvt` login;
- the `whitson-pvt` skill: how to use those tools, and when to fetch full data with `wpvt api`,
  `wpvt samples export` and `wpvt bot export` instead.

The plugin holds no deployment URL and no token. `wpvt mcp` uses the default login stored by
`wpvt auth login`, so the same plugin works for every deployment.

## Before you install

A plugin cannot install a command, so install `wpvt` with the `mcp` extra and log in first:

```bash
uv tool install "whitson-pvt-sdk[mcp]"          # or: pip install "whitson-pvt-sdk[mcp]"
wpvt auth login --url https://<your deployment>
wpvt auth status                                # check the login
```

`wpvt` must be on the `PATH` that Claude Code or Codex starts with. For a read-only connection,
log in with `wpvt auth login --url https://<your deployment> --scope read`, or pick the scopes on
a page with `--choose`; the server then offers only the tools those scopes allow.

## Claude Code

```bash
claude plugin marketplace add WhitsonAS/whitson-pvt-sdk
claude plugin install wpvt@whitson-pvt
```

In a session, `/plugin marketplace add WhitsonAS/whitson-pvt-sdk` and then
`/plugin install wpvt@whitson-pvt` do the same; Claude Code 2.1.275 or later also takes the one-step
`/plugin install wpvt --marketplace WhitsonAS/whitson-pvt-sdk`. Start a new session, or run `/reload-plugins`.

## Codex

```bash
codex plugin marketplace add WhitsonAS/whitson-pvt-sdk
codex plugin add wpvt@whitson-pvt
```

Or open `/plugins` in Codex and install `wpvt` from the whitson PVT marketplace. Start a new
session afterwards. An installed plugin is switched on or off in `~/.codex/config.toml`:

```toml
[plugins."wpvt@whitson-pvt"]
enabled = true
```

## Without plugins

Register the MCP server by hand; the skill can be added with `uvx library-skills` from a project
that depends on the SDK.

```bash
claude mcp add wpvt -- wpvt mcp
codex mcp add wpvt -- wpvt mcp
```

## Troubleshooting

- **The server fails to start, or no whitson PVT tools appear.** Run `wpvt mcp` in a terminal.
  It exits with the reason on stderr; when it waits for input instead, it works (stop it with
  Ctrl-C) and the problem is in the host's configuration.
- **`command not found: wpvt`, or the host cannot start it.** The command is not installed, or
  not on the host's `PATH`. Install it as above; with `uv tool install`, run
  `uv tool update-shell` and restart the host.
- **`wpvt mcp needs the mcp extra`.** It was installed with only the `cli` extra:
  `uv tool install --reinstall "whitson-pvt-sdk[mcp]"`.
- **No deployment URL configured, or the login is no longer valid.** Run
  `wpvt auth login --url https://<your deployment>` in your own terminal, then restart the server
  (`/mcp` in Claude Code, a new session in Codex). An agent never runs the login for you.
- **A tool is refused with "sign in again and approve the scope".** The login was made with
  `--scope` or `--choose`; run `wpvt auth login` again without them, or with that scope added,
  then restart the server.
- **The server refuses an API token.** MCP needs a `wpvt auth login`; unset `WHITSON_PVT_TOKEN`
  in the host's environment.
