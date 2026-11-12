# Agent Notes

Start by reading the relevant existing module before changing behavior. Keep edits narrow and aligned with nearby patterns.

## Commands

- Setup: `uv sync`; install the task runner with `uv tool install rust-just` if `just` is missing.
- Dependency cooldown: `[tool.uv] exclude-newer = "3 days"` in `pyproject.toml`, as in the API repository, so `uv lock` never picks a release younger than three days; add a per-package exception only when a fix is required, and say why.
- Focused checks: `just lint`, `just ty`, `just build`.
- `just check` runs `lint -> format -> ty`; it is not read-only because `format` runs `ruff format whitson_pvt_sdk/`.
- `just all` regenerates models, applies lint fixes/formatting, typechecks, then builds.

## Tests

- Run the test suite with `just test`; it executes `uv run pytest tests/ -v`.
- Run coverage with `just test-cov`; it executes `uv run pytest tests/ -v --cov=whitson_pvt_sdk --cov-report=term-missing`.
- Prefer `just test` over invoking pytest directly unless you are intentionally running a focused subset.

## Codegen

- Treat `whitson_pvt_sdk/_generated/**` and `whitson_pvt_sdk/v2/models/__init__.py` as generated output.
- Regenerate from the external API's OpenAPI document, either from a file or from a live API:
  - From a file, with no API running: `just generate-file v2 FILE`, or `just generate-file-check v2 FILE` to only show the diff. In a whitsonPVT workspace, `mise sdk:generate` and `mise sdk:generate:check` (run from `app/`) build the file from the workspace's API source and do this.
  - From a live local API at `http://localhost:4000`: `just generate v2` or `just generate-all`, which fetch `http://localhost:4000/external/{version}/docs/openapi.json`.
- The repo-specific generator lives in `scripts/sdk_generator/`. It runs `ruff check --fix --select I,F401` and `ruff format` on rendered endpoint/resource files, so generated files should not require a second formatting pass.
- Put hand-maintained shared models in `whitson_pvt_sdk/shared/models.py`; avoid hand-editing generated files unless intentionally patching generated output when the API spec is unavailable.
- Authentication is excluded from generated resources via `EXCLUDED_RESOURCES`; keep auth as transport infrastructure, not as `client.authentication`.

## Working in a whitsonPVT workspace

- A whitsonPVT development workspace can hold this repository as an optional `sdk/` worktree next to `app/` and `utils/` (`mise create NAME --sdk` in the app repository). Its branch starts from `origin/main` and tracks nothing until pushed.
- Commit, push and release from `sdk/` as usual; this file and its commit-message rules apply there.
- From the workspace's `app/`: `mise sdk:install`, `mise sdk:check` (lint and ty, no formatting), `mise sdk:test`, `mise sdk:generate`, `mise sdk:generate:check`, and `mise sdk:integration`, which runs the integration tests against the workspace API with its local bypass token and writes test data to the workspace database.
- Never work in the persistent clone the workspaces share (`PVT_SDK_SOURCE`, default `~/Developer/whitson-pvt-sdk`); it stays on `main`.

## Architecture

- Public entrypoint is the `WhitsonPVTClient` class (`whitson_pvt_sdk/_client.py`, re-exported from `whitson_pvt_sdk`); it resolves the credential and wires the v2 resources. Only external API v2 is supported; v1 was removed in 2.0.
- Credentials, each in one module with a small interface (`a -> b` means a imports b):
  - `whitson_pvt_sdk/credentials.py`: the credential kinds, `ApiToken` and `StoredLogin` (frozen, `SecretStr`), `Credential = ApiToken | StoredLogin`, URL normalisation and the origin comparison used for host binding.
  - `whitson_pvt_sdk/auth.py -> _refresh, _store`: `resolve_base_url` (`base_url` -> `WHITSON_PVT_URL` -> default login) and `resolve_credential` (`token=` -> `WHITSON_PVT_TOKEN` -> stored login for that URL), returning `FromArgument | FromEnvironment | FromStore`; `BearerSource`, with one `match` arm per credential kind; and `CredentialAuth`, the `httpx.Auth` over it. The `StoredLogin` arm refuses any request whose scheme, host and port differ from the login's URL, renews within five minutes of expiry and once on a 401. A new credential kind is a new model in `credentials.py` plus one arm in each `BearerSource` method and in `resolve_credential`.
  - `whitson_pvt_sdk/_store.py`: the only code that knows the backend (`credentials.json` at 0600, the optional OS keyring, the `credentials.lock` file lock). Reads are lock-free snapshots (`get`, `default_url`); every write goes through `transaction()`, which holds the lock and persists on exit. Entries are `ActiveLogin | InvalidLogin`.
  - `whitson_pvt_sdk/_refresh.py -> _oauth, _store`: `usable_login` and `replace_access_token` return `StillValid | Refreshed | NoLongerValid`; renewal re-reads the store under the lock, so a login renewed by another process is used without a token request, and `invalid_grant` marks the entry invalid. Plain functions, so `wpvt mcp` can get a current access token without going through an `httpx.Auth`.
  - `whitson_pvt_sdk/_oauth.py`: the OAuth/OIDC wire protocol (`/external/v2/auth/config`, discovery, token, revocation requests) as Pydantic models; no state.
  - `whitson_pvt_sdk/_trust.py -> _store`: which deployments a login may start for and where it may sign in. `host_trust` returns `TrustedDeployment | TrustedLoopback | TrustedByOverride | Refused` from the one `ALLOWLIST` (HTTPS under `pvt.whitson.com`, loopback hosts) and the explicit `trust_host` override; `login_decision(trusted_host, issuer, audience)` returns `Proceed | FirstUse | IssuerChanged | UnexpectedIssuer | UnexpectedAudience` from the host kind, `KNOWN_ISSUERS` (exact issuer hosts, today `whitson.eu.auth0.com`), whether the audience is the deployment's own `/mcp` URL (same origin, exact path) and the stored profile's issuer: a deployment with a known issuer and its own audience proceeds, one with another issuer or another audience is refused with no override, and loopback (unless known issuer and own audience) and override hosts ask on first use or a changed issuer, naming a foreign audience in the question. `SecureUrl` is the https-or-loopback type for the issuer and its endpoints. No environment variable or setting widens either list.
  - `whitson_pvt_sdk/login.py -> _oauth, _store, _trust`: `login(base_url, BrowserLogin(...) | DeviceLogin(), output=..., confirm=..., trust_host=...)`, `logout(base_url)` and `logout_all()`. The only code that starts a login; library code never calls it. Order: host trust (no request on refusal), `/auth/config`, a login-decision refusal, the device-login gate, the login-decision confirmation, then discovery and the flow; the device flow refuses a verification URL off the issuer's origin before printing anything.
  - `whitson_pvt_sdk/cli/`: the `wpvt` Typer app. The `cli` extra is Typer and keyring; the `mcp` extra is `cli` plus FastMCP, for `wpvt mcp` only. `__init__.main` prints the install command when Typer is missing, and `wpvt mcp` does the same for FastMCP; `_app.py` is the root app that adds every group; `_output.py` maps SDK errors to exit codes (2 configuration, 3 authentication, 4 network or server; an unexpected response shape is 4) and prints Pydantic models as JSON. Data commands build `WhitsonPVTClient()` with no arguments and hold no business logic:
    - `_auth.py`: `wpvt auth`.
    - `_resources.py`: `list` and `get` for regions, wells, samples, projects, fluid models and black-oil tables (`bot`) from one table, `RESOURCES`; a row's `listing` is `TopLevel | Nested | Unpaged` (which parent option, whether it pages), `--all` uses `Paginator.iterate`, and `aliases` are extra command names for the same group, hidden from `wpvt --help` (`black-oil-tables` for `bot`). A new resource is one row.
    - `_export.py`: `samples export` (one directory per sample id: `index.json`, `sample.json`, `compositions/`, `experiments/`; no server string reaches a path) and `bot export`.
    - `_reports.py`: `reports export` and `reports import`.
    - `_calc.py`: `calc flash|saturation-pressure|phase-envelope`, one generic `Calculation` row each; the request comes from `RequestFile | SampleFeed`, chosen by `_request_origin`.
    - `_api.py`: `wpvt api`, the raw route call (`Call | ListRoutes | Describe`), `--paginate`, and route discovery from `/external/v2/docs/openapi.json`. Path confinement is not here: it is `http.external_path`, used by `HTTPTransport.request` and `WhitsonPVTClient.request`.
    - `_mcp.py`: `wpvt mcp`, imported lazily so other commands do not load FastMCP. A FastMCP stdio proxy (`create_proxy` over a `StreamableHttpTransport` to `<base_url>/mcp`) with `LoginBearer`, the `httpx2.Auth` adapter over `auth.BearerSource`, and the `X-PVT-Client: wpvt/<version>` header. It checks the backend with one `list_tools` before serving and never starts a login. Session pinning and local tools would attach in `_serve` (transport headers and a provider on the proxy).
- Never log, print or put a token, refresh token, authorization code or PKCE verifier in an error. Tests run against a temporary `XDG_CONFIG_HOME` with the keyring disabled (`tests/conftest.py`); keep it that way so no test touches a real store.
- `GET /me` is parsed by the hand-written `Identity` union (`api_token | user_token | legacy_client`, discriminated by `kind`) in `shared/models.py` until it is in the OpenAPI document; then replace it with the generated model.
- `HTTPTransport` owns the `base_url.rstrip('/') + /external/v2` prefix, timeouts, retries (decided by `_retry.retry_delay`), error mapping, JSON parsing, bytes downloads, multipart uploads, and `request()`, the raw call for any route, whose path `external_path` confines to the prefix (unreserved characters per segment, no `.`/`..`, no host, percent-encoding or query).
- Python 3.11 is the minimum; development and CI use 3.15 (`.python-version`). Do not use syntax newer than 3.11.
- Public resource classes in `whitson_pvt_sdk/v2/resources.py` usually re-export generated facades from `whitson_pvt_sdk/_generated/v2/resources.py`; put manual SDK conveniences there by subclassing/wrapping generated classes.
- Generated resource methods use SDK-shaped names (`list`, `get`, `create`, `update`, `create_bulk`, `update_bulk`) while lower-level generated module functions keep OpenAPI operation IDs.
- v2 list endpoints use paginated models for regions/projects/fluid models/black oil tables/wells.
- Report import/export is special: export returns raw zip bytes plus a synthetic filename, and import/preflight upload `archive.zip` with optional `meta_data` serialized from `ImportArchiveOptions`.
- The agent skill ships in the wheel at `whitson_pvt_sdk/.agents/skills/whitson-pvt/SKILL.md` (Library Skills layout); keep it in step with the public API. It is the single source: `plugins/wpvt/skills/` is a copy made by `just plugins-sync`, and `just lint` fails (`just plugins-check`) until the copy matches.
- `plugins/wpvt/` is the Claude Code and Codex plugin (this repository is its marketplace: `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`). Each tool has its own manifest and MCP file there (`.claude-plugin/plugin.json` and `.mcp.json`; `plugin.json` and `mcp.json` in the Agent Plugins format Codex reads); the plugin holds no deployment URL, token or version, and is not part of the wheel.
- Configure retries and timeouts on `WhitsonPVTClient(...)` with `RetryConfig`, `timeout`, and `file_timeout`; default retries apply only to `GET`/downloads and retry `408`, `429`, `500`, `502`, `503`, and `504`.

## Endpoint Wrappers

For new endpoint wrappers or generator behavior:

1. Prefer changing `scripts/sdk_generator/` and regenerating over hand-editing generated endpoint/resource files.
2. Call `HTTPTransport.get`, `post`, `put`, `patch`, `delete`, `get_bytes`, or `post_multipart`.
3. Serialize Pydantic inputs with `model_dump(exclude_unset=True)`.
4. Validate structured responses with the generated model's `model_validate`.
5. Add or update the matching generated resource facade method through generator inference or `OVERRIDES` when the endpoint exists in OpenAPI.

For SDK-only conveniences or compatibility shims that are not OpenAPI-derived, add them to `whitson_pvt_sdk/v2/resources.py`, not `_generated/**`.

## Final Checks

Before finishing a change, run the narrowest applicable checks: `just test`, `just lint`, `just ty`, and/or `just build`.

Mention if a check was skipped because it would format, regenerate code, require the local API, or depend on missing tooling.
