# whitson PVT SDK

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://github.com/WhitsonAS/whitson-pvt-sdk/blob/main/LICENSE)

HTTP client for the whitson PVT external API. Python 3.11+.

## Install

```bash
# uv (recommended)
uv add whitson-pvt-sdk

# pip
pip install whitson-pvt-sdk
```

## Quick start

Authenticate with an API token. Set `WHITSON_PVT_TOKEN` in the environment, or pass
`token=` explicitly:

```bash
export WHITSON_PVT_TOKEN=whitson_pvt_...
```

```python
from whitson_pvt_sdk import WhitsonPVTClient

with WhitsonPVTClient(base_url="https://internal.pvt.whitson.com") as client:
    # or: WhitsonPVTClient(token="whitson_pvt_...", base_url="https://internal.pvt.whitson.com")
    regions = client.regions.list()
    well = client.wells.get(well_id=123)
    sample = client.samples.get(sample_id=456)
```

Leaving the `with` block closes the client's connections. A client kept for the life
of a process can call `client.close()` instead; closing twice is harmless, and a
request on a closed client raises `RuntimeError`.

Create an API token in whitson PVT under **Developer → Integrations**. Tokens start
with `whitson_pvt_` and are shown once, when they are created.

The client resolves its deployment and credential in a fixed order:

| | First | Then | Then | Otherwise |
| --- | --- | --- | --- | --- |
| Deployment | `base_url=` | `WHITSON_PVT_URL` | the default login from `wpvt auth login` | `ConfigurationError` |
| Credential | `token=` | `WHITSON_PVT_TOKEN` | the stored login for that deployment | `ConfigurationError` naming all three and `wpvt auth login --url <url>` |

An API token (`token=` or `WHITSON_PVT_TOKEN`) is used only with a deployment from `base_url=` or
`WHITSON_PVT_URL`; with one from the default login it is refused, as below. It is only sent over
HTTPS: a plain `http://` URL is refused with `ConfigurationError` unless it is this machine
(`localhost`, a name under `localhost`, `127.0.0.1` or `::1`).

An API token is sent as the bearer token on every request and wins even when a stored login
exists for the same deployment, but only to a deployment you named: `base_url=` or
`WHITSON_PVT_URL`. When the URL would come from the default login and `token=` or
`WHITSON_PVT_TOKEN` is set, creating the client raises `ConfigurationError` naming both, so a
token kept in the environment is never sent to whichever deployment happens to be the default
login; set `WHITSON_PVT_URL` (or pass the URL) or unset the token. A set-but-empty `token=` or `WHITSON_PVT_TOKEN` is an error, not
a fall-through. A stored login that the authorization server no longer accepts raises
`LoginError`, which says to run `wpvt auth login` again.

`client.me.get()` returns who the credential belongs to (kind, user, role and scopes).

### Upgrading from 1.x

2.0 authenticates with API tokens or a `wpvt auth login`, no longer with client credentials,
and talks only to external API v2.

- Python 3.11 or newer is required; 3.10 is no longer supported. Stay on 1.x for Python 3.10.
- Removed: `ClientCredentials`, the `credentials=` argument, the `/auth/token`
  exchange, `client.get_access_token()`, `whitson_pvt_sdk.auth.TokenManager` and
  `TokenData`. Pass `token=` or set `WHITSON_PVT_TOKEN` instead; the bearer is the token you
  already hold.
- Removed: `version=` and the v1 API (`whitson_pvt_sdk.v1`). API releases that accept
  tokens no longer serve `/external/v1`.
- `WhitsonPVTClient` is now the client class; `whitson_pvt_sdk.v2.WhitsonPVTClientV2`
  is gone. Annotate with `WhitsonPVTClient`.
- The package root exports only `WhitsonPVTClient`. Import `RetryConfig` from
  `whitson_pvt_sdk.shared.models` and `HTTPTransport` from `whitson_pvt_sdk.http`.
- `retry_config=None` is no longer accepted; omit `retry_config` for the defaults.
- `HTTPTransport(credential, base_url, ...)` takes an `ApiToken` or `StoredLogin` from
  `whitson_pvt_sdk.credentials`, has no `version` argument and is no longer a context manager.
- `WhitsonPVTClient(base_url=...)` is optional: it falls back to `WHITSON_PVT_URL` and then to
  the default login stored by `wpvt auth login`.
- `calculations.get_gor_recombination_feed_composition(s)` take the feed composition(s)
  through `source=` instead of `feed_composition(s)=`.
- A missing or empty token raises `ConfigurationError` when the client is created,
  not `AuthError`. `AuthError` now means only that the API answered 401 or 403.
- A request that gets no response (connection error, timeout) raises
  `NoResponseError` instead of `APIError` with `status_code=None`. Every
  `ResponseError` (`AuthError`, `NotFoundError`, `ValidationError`, `RateLimitError`,
  `APIError`) now carries an integer `status_code`.
- `WhitsonPVTClient` has `close()` and works as a context manager; replace any
  `client._transport.close()` with `client.close()` or a `with` block.
- `RetryConfig` is immutable and its `methods` must be upper-case HTTP methods.
- `whitson_pvt_sdk.utils.write_json(data, path=None)` is no longer accepted; omit
  `path` for `output.json`.
- The unused multi-domain copy models (`DomainAuthConfig`, `MultiDomainCopyConfig`
  and related) are removed from `whitson_pvt_sdk.shared.models`.
- `GasDensityUnit` and `LiquidDensityUnit` are replaced by `DensityUnit`, which has no `"SG"`.
  `GetWellModel.samples` and `GetProjectWithFluidModelsModel.fluid_models`/`samples` are
  `None` when the credential may not read them, and `samples.list(well_id)` then raises
  `AuthError`. See `docs/api-v2-update.md`.
- `calculations.get_sample_feed_composition(s)` raise `MissingDataError` instead of
  `ValueError` when the fluid model has no adjusted composition for a requested sample.
- The HTTP library is now [httpx2](https://github.com/pydantic/httpx2), Pydantic's fork of
  httpx, instead of httpx. The SDK's public interface takes and returns no httpx types, but
  code that reached into its internals (`HTTPTransport._http`, `whitson_pvt_sdk.auth.CredentialAuth`),
  caught `httpx` exceptions chained under an SDK error (`__cause__`), or configured the `httpx`
  logger must use `httpx2` instead. Requests identify as `python-httpx2/<version>`.
- TLS certificates are verified against the operating system's trust store instead of the
  `certifi` bundle: on Windows and macOS through `truststore`, on Linux from OpenSSL's
  system CA file or directory. A CA installed in the system store, such as a corporate
  TLS-inspection CA, is now trusted without extra configuration, and an update of `certifi`
  no longer changes what is trusted. A Linux container without a CA bundle (no
  `ca-certificates` package) now fails verification where `certifi` used to cover it. Setting
  `SSL_CERT_FILE` or `SSL_CERT_DIR` still selects a bundle and takes precedence, as before.

1.x keeps working with client credentials until the server retires them. Pin
`whitson-pvt-sdk<2` if you cannot switch to a token yet.

### Retries

The SDK retries transient read failures by default. `GET` requests are attempted up
to 3 times for network timeouts/transport errors and HTTP `408`, `429`, `500`,
`502`, `503`, and `504` responses. Mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`, and
multipart uploads) are not retried by default, except on HTTP `429` (rate
limiting).

Retry delays honor `Retry-After`, `retry-after-ms`, and `X-RateLimit-Reset`
headers when present, waiting at most 60 s per retry; a value that is negative, infinite or not
a number counts as absent. `X-RateLimit-Limit` and `X-RateLimit-Remaining` are left
available on the raw HTTP response internally, but do not affect retry timing.

If retries are exhausted on HTTP `429`, the SDK raises `RateLimitError` with
`retry_after_seconds` when retry timing headers are present. `max_attempts`
includes the first request; use `RetryConfig(max_attempts=1)` to disable
retries. `RetryConfig.methods` controls non-429 retries only; remove `429` from
`RetryConfig.statuses` to disable all-method rate-limit retries.

Configure retries on the client:

```python
from whitson_pvt_sdk import WhitsonPVTClient
from whitson_pvt_sdk.shared.models import RetryConfig

client = WhitsonPVTClient(
    base_url="https://internal.pvt.whitson.com",
    retry_config=RetryConfig(max_attempts=1),  # disables retries
)
```

Configure default request timeouts with `timeout`; downloads and uploads use
`file_timeout`:

```python
client = WhitsonPVTClient(
    base_url="https://internal.pvt.whitson.com",
    timeout=30.0,
    file_timeout=60.0,
)
```

### Errors

Everything the SDK raises derives from `SDKError` in `whitson_pvt_sdk.errors`:

| Error | Raised when | Fields |
| --- | --- | --- |
| `ConfigurationError` | the client is created without a usable URL or credential | `message` |
| `LoginError` | a login did not complete, or the stored login is no longer valid | `message` |
| `NoResponseError` | a request gets no response (connection error, timeout) after retries | `message` |
| `ResponseError` | the API answers with an error status; base of the five below | `status_code`, `response_body`, `request_id`, `server_message` (the `message` of the JSON error body, `None` without one) |
| `AuthError` | HTTP 401 or 403 | as `ResponseError` |
| `NotFoundError` | HTTP 404 | as `ResponseError` |
| `ValidationError` | HTTP 400 or 422 | as `ResponseError` |
| `RateLimitError` | HTTP 429 after retries | also `retry_after_seconds` |
| `APIError` | any other error status | as `ResponseError` |
| `CalculationError` | a calculation returns a failed result | `code`, `sample_id`, `input_index`, `error` |
| `MissingDataError` | the input names data that does not exist, such as a sample without an adjusted composition in the fluid model | `message` |

```python
from whitson_pvt_sdk.errors import AuthError, NoResponseError, ResponseError

try:
    region = client.regions.get(region_id=1)
except AuthError:
    ...  # the token was rejected or lacks access
except ResponseError as exc:
    print(exc.status_code, exc.request_id)
except NoResponseError:
    ...  # no response; a write may still have reached the API
```

### Pagination

List endpoints (regions, projects, fluid models, black oil tables, wells) are
cursor-paginated. Use `iterate()` for lazy traversal or `list_all()` for an eager
list:

```python
for region in client.regions.iterate(limit=50):
    print(region.name)

regions = client.regions.list_all(limit=50)
```

Each response still includes a `pagination` field when you need manual cursor
control:

```python
page = client.regions.list()
print(page.pagination.next_cursor)
```

Pass `cursor` and `limit` to control pagination:

```python
page = client.regions.list(limit=50)
page = client.regions.list(cursor=page.pagination.next_cursor)
```

Limit defaults to the API default (usually 20) when omitted. `iterate()` and
`list_all()` are available on all cursor-paginated resources: `regions`,
`wells`, `projects`, `fluid_models`, and `black_oil_tables`.

All five resources also accept `name=` on `list()`, `iterate()`, and `list_all()`.
This is a case-insensitive exact match; the API trims surrounding whitespace.

### Any route

`client.request(method, path, params=..., body=...)` calls an external v2 route that has no
resource method and returns an `ApiResponse` (`status_code`, `headers`, `content` bytes). `path`
is relative to `/external/v2` (a leading `/external/v2` is accepted); a host, `..`,
percent-encoding or a query string in it raises `ConfigurationError` before any request.

```python
response = client.request("GET", "/samples/345")
sample = json.loads(response.content)
```

### Staged imports and OSDU export

`client.import_sessions` exposes archive upload, inspection, per-record resolution,
selected-record commit, and deletion. `client.import_records` exposes the four
single-record OSDU import endpoints.

```python
from pathlib import Path
from whitson_pvt_sdk.v2.models import ImportSessionCreateOptionsModel

session = client.import_sessions.create(
    Path("archive.zip").read_bytes(),
    ImportSessionCreateOptionsModel(region_id=123),
)
records = client.import_sessions.list_records(session.id)
# Review records before calling update_resolution() and commit().
```

Export OSDU archives with `client.reports.export(report_id=123, format="osdu")`.
The native archive format remains the default.

See [Updating to the current external API v2](docs/api-v2-update.md) for changed model names,
commit-selection semantics, and API deployment requirements.

More runnable examples are available in [examples](https://github.com/WhitsonAS/whitson-pvt-sdk/tree/main/examples).

## Command line

The `wpvt` command comes in two optional extras; the library itself keeps its two runtime
dependencies (httpx2 and pydantic).

| Extra | Adds | For |
| --- | --- | --- |
| `cli` | Typer and keyring | `wpvt auth`, the data commands and `wpvt api` |
| `mcp` | The `cli` extra plus FastMCP | Everything above and `wpvt mcp`, for agent hosts |

```bash
uv tool install "whitson-pvt-sdk[cli]"   # or: pip install "whitson-pvt-sdk[cli]"
uv tool install "whitson-pvt-sdk[mcp]"   # or: pip install "whitson-pvt-sdk[mcp]"
```

Without the `cli` extra, `wpvt` prints its install command and exits with code 2; without the
`mcp` extra, so does `wpvt mcp`.

```console
$ wpvt auth login --url https://example.pvt.whitson.com
Opened a browser to log in. If it did not open, visit:
http://127.0.0.1:52817/start?n=...
Logged in to https://example.pvt.whitson.com as Ada Lovelace <ada@example.com> (role: project_editor). This login is now the default.

$ wpvt auth status
Deployment: https://example.pvt.whitson.com
Credential: stored login (wpvt auth login)
Identity:   Ada Lovelace <ada@example.com> (role: project_editor)
Scopes:     read:data, write:data

$ wpvt auth logout
Logged out of https://example.pvt.whitson.com; the refresh token was revoked.
```

- `wpvt auth login [--url URL] [--device] [--trust-host] [--yes]` logs in with the
  authorization code flow and PKCE through a one-off listener on `127.0.0.1`, on the first free
  port of 52817, 54631, 57493 and 61287 (the redirect URI must match exactly, so these are the
  ports registered on the login server; the login fails with a message naming them when all are
  busy). The browser is given a one-time link to the listener, `/start?n=<random>`, which
  redirects it to the login server, so the login's `state` and PKCE challenge never appear on a
  command line that other users of the machine can read; if that link is opened a second time,
  the login stops, since another program may have used it first. Only a callback carrying this
  login's `state` ends the wait; any other request to the listener is answered 400 or 404 and
  ignored. The listener's pages are fixed text with no external resources, served with
  `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`. It opens a browser
  only when attached to a terminal, with the browser's own output kept off the terminal;
  otherwise it prints the link, which must be opened on the same machine. `--device` logs in
  with a code entered on another device, for SSH sessions, containers and sandboxes, on deployments that enable it. The login is stored, and
  becomes the default, only after `/external/v2/me` accepts it; if that check fails, nothing is
  stored and the previous default stays. A deployment accepts a login only while a sign-in to
  its web app has confirmed your role in the last 30 days; otherwise it refuses the login and
  says so, and signing in to the web app, not logging in again, fixes it.
- `wpvt auth status [--url URL]` shows the deployment, the credential in use and where it
  came from (`WHITSON_PVT_TOKEN` or the stored login), and the identity, role and scopes the
  API reports: the API token's name for an API token, and "legacy client <subject>, full
  access" for a legacy client. It never prints a token. When the deployment refuses the stored
  login, it shows the deployment's reason, and suggests `wpvt auth login` only when there is none.
- `wpvt auth logout [--url URL | --all]` removes stored logins and revokes their refresh
  tokens when the authorization server offers revocation. It removes a login even when its
  tokens cannot be read; when the OS keyring is unavailable, it says the keyring entries were
  not deleted (`"keyring": "not_deleted"` with `--json`) and names them.
- `wpvt --version` prints the version.

The URL comes from `--url`, else `WHITSON_PVT_URL`, else the default login; with
`WHITSON_PVT_TOKEN` set, a URL from the default login is refused (see Quick start). Commands that report
take `--json`: one JSON document on stdout; errors go to stderr, as one JSON document (`error`,
`message`) with `--json`. Progress messages (the login URL, the device code) go to stderr.

### Data commands

For what an MCP tool result cannot carry: full tables, whole samples, many records at once. Each
command calls the external API through `WhitsonPVTClient()` with the same URL and credential as
above (`WHITSON_PVT_URL` and `WHITSON_PVT_TOKEN`, else the default login) and adds no logic of its
own.

| Command | Does |
| --- | --- |
| `wpvt regions list`, `wpvt wells list --region ID`, `wpvt projects list --region ID`, `wpvt fluid-models list --project ID`, `wpvt bot list --fluid-model ID` | One page (`--limit`, `--cursor`), or every page with `--all`; `id` and `name` per line, or `{"items": [...], "next_cursor": ...}` with `--json` |
| `wpvt samples list --well ID` | Every sample of a well |
| `wpvt <resource> get ID` | The resource as JSON |
| `wpvt samples export ID... --out DIR` | One directory per sample, see below |
| `wpvt bot export ID --out FILE [--format csv]` | The whole black-oil table as JSON, or its rows as CSV with units in the header |
| `wpvt reports export REPORT_ID --out FILE` | The report archive (`--format osdu`, `--native-payload`, `--structured-experiments`) |
| `wpvt reports import FILE [--region ID] [--acknowledge-suggestions] [--preflight]` | Import an archive, or only check it; prints the result |
| `wpvt calc flash\|saturation-pressure\|phase-envelope --input FILE [--out FILE]` | Validate the request with the SDK's model and run it; `-` reads stdin |
| `wpvt api [METHOD] PATH` | Any external v2 route, like `gh api` |

```console
$ wpvt wells list --region 12 --all --json > wells.json
$ wpvt samples export 345 346 --out ./samples
Wrote sample 345 to samples/345
Wrote sample 346 to samples/346
$ wpvt calc flash --sample 345 --fluid-model 78 --input conditions.json --out flash.json
```

`wpvt bot` covers black-oil tables (BOT); `wpvt black-oil-tables` is an alias for it.

`samples export` writes `DIR/<sample id>/` with `index.json` (layout, units convention, SDK and API
version), `sample.json` (the sample without its compositions and experiments),
`compositions/<field>.json` (one per composition, such as `gas_composition`) and
`experiments/<n>-<type>.json` (one per experiment, in order, such as `1-CCE.json`). Directory and
file names come only from ids, positions and experiment types, never from names stored on the
server. A sample directory that exists and is not empty is refused unless `--force`, which
replaces it. Values are in the units the API returns: a quantity's unit is in the field of the
same name with `_unit` appended.

`calc` reads the request from `--input`. With `--sample ID --fluid-model ID` the feed composition
comes from the stored sample through `calculations.get_sample_feed_composition`
(`--source slate_to_slate_converted`, the default, or `adjusted_compositions`), and `--input` holds
the rest of the request without `fluid_model_id` or `feed_composition`; it can be left out for a
phase envelope. `--sample` and `--fluid-model` go together, and a request file that sets either
field is refused.

`wpvt api` sends any external v2 route with the same credential. PATH is relative to
`/external/v2`; a leading `/external/v2` is accepted, so the `full_data` route in an MCP tool
result works as given. Absolute URLs, `..`, percent-encoding, backslashes, empty segments and
query strings in PATH are refused before any request, so the credential never leaves the
deployment's external API. METHOD defaults to GET, or POST with `--data`.

```console
$ wpvt api --list                                   # every route, from the deployment's OpenAPI
$ wpvt api --describe GET /samples/{sample_id}      # scopes, parameters and schema names
$ wpvt api /regions/12/wells -q limit=250 --paginate --out wells.json
$ wpvt api GET /external/v2/samples/345 --out sample-345.json
$ wpvt api /calculations/phase-envelope -d @request.json
```

- `-q KEY=VALUE` adds a query parameter; `-d` takes inline JSON, `@FILE` or `-` for stdin, and is
  checked to be a JSON object or list of objects before sending.
- `--paginate` follows `pagination.next_cursor` on a GET and prints one document: the first
  page's envelope with the list concatenated across pages and
  `"pagination": {"next_cursor": null, "prev_cursor": null}`. A response without cursor
  pagination is refused rather than guessed at.
- `--include` prints the status and the rate-limit headers to stderr.
- `--list` and `--describe` read `/external/v2/docs/openapi.json` from the deployment each time;
  add `--json` for one document. There is no query language; pipe to `jq`.

### `wpvt mcp`

`wpvt mcp` serves the deployment's MCP tools over stdio for an agent host, using the same login
as the rest of `wpvt`. It is a proxy to `<deployment>/mcp`: the tools are defined by the server,
not by the SDK. It needs the `mcp` extra.

```bash
claude mcp add wpvt -- wpvt mcp
codex mcp add wpvt -- wpvt mcp
```

- MCP currently needs a login from `wpvt auth login`; the server refuses API tokens
  (`whitson_pvt_...`) on MCP. When it refuses the token in `WHITSON_PVT_TOKEN`, `wpvt mcp` says
  to unset it and log in, and to check the token with `wpvt auth status` if it should work
  elsewhere.
- It never starts a login or opens a browser. With no login, a login that is no longer valid,
  a credential the server refuses, or an unreachable deployment, it exits before serving with
  the message on stderr, so the host shows the server as failed. A login that stops working while
  serving turns into a tool error naming `wpvt auth login --url ...`.
- The MCP endpoint does not say why it refuses a stored login, so `wpvt mcp` then asks
  `/external/v2/me` with the same token and shows its reason, such as the 30-day web sign-in rule
  above. It suggests `wpvt auth login` only when the API gives no reason, and says so when the API
  accepts the login that MCP refuses.
- The stored login renews itself, is persisted under the store's lock and goes only to its own
  deployment. Every request carries `X-PVT-Client: wpvt/<version>`.
- stdout carries only MCP messages; diagnostics go to stderr (`--verbose` for more). Tokens are
  never logged.
- `--url` picks the deployment; otherwise `WHITSON_PVT_URL`, else the default login.

| Exit code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Any other error, such as another process holding the credential store's lock for longer than a login renewal can take (try again) |
| 2 | Usage or configuration: a bad option, no URL or credential configured, an API token without an explicit URL, login not enabled on the deployment, a credentials file with loose permissions or that cannot be replaced, an OS keyring that cannot be read, the `cli` extra (or for `wpvt mcp`, the `mcp` extra) missing |
| 3 | Authentication: the login was refused or is no longer valid, or the API rejected the credential |
| 4 | Network or server: no response, or an unexpected status or response shape from the API, the deployment's login configuration or the authorization server |

### Use with Claude Code and Codex

The `wpvt` plugin in this repository registers `wpvt mcp` as an MCP server and adds the
`whitson-pvt` agent skill. Install the command with the `mcp` extra and log in first; the plugin
holds no URL or token and uses your default login.

```bash
uv tool install "whitson-pvt-sdk[mcp]"
wpvt auth login --url https://<your deployment>

claude plugin marketplace add WhitsonAS/whitson-pvt-sdk && claude plugin install wpvt@whitson-pvt
codex plugin marketplace add WhitsonAS/whitson-pvt-sdk && codex plugin add wpvt@whitson-pvt
```

Without plugins: `claude mcp add wpvt -- wpvt mcp` or `codex mcp add wpvt -- wpvt mcp`. See
[plugins/README.md](https://github.com/WhitsonAS/whitson-pvt-sdk/tree/main/plugins) for details
and troubleshooting.

### Which deployments a login trusts

`wpvt auth login` asks the deployment where to sign in and sends your browser there, so it only
starts for hosts it can expect you to trust:

- HTTPS hosts under `pvt.whitson.com`, such as `example.pvt.whitson.com` or
  `eu.example.pvt.whitson.com` (not `pvt.whitson.com` itself, and not lookalikes such as
  `evilpvt.whitson.com` or `pvt.whitson.com.example.org`);
- this machine, over http or https: `localhost`, names under `localhost` (such as
  `api.pvt.localhost`), `127.0.0.1` and `::1`. A name under `localhost` must resolve only to
  loopback addresses when the login starts, since not every resolver maps such names to this
  machine; otherwise the login is refused before any request.

Host names are compared lower-case without a trailing dot. A URL with a user name or password,
a non-ASCII or punycode (`xn--`) host name, or plain HTTP to another host is refused. For any
other host, the login stops before contacting it and names the host. If you know and trust it,
run the login again with `--trust-host` and the URL in `--url` (in Python,
`login(..., trust_host=True)`). The override applies to that one command and that URL only; no
environment variable or setting widens the list.

The deployment also names the login server (the issuer) your browser is sent to and the service
the login grants access to (the audience). A deployment may only ask for access to itself: its
own MCP resource URL, `https://<deployment host>/mcp`, with the same scheme, host and port and
exactly the path `/mcp`. Together they decide what happens next:

| Deployment | Login server it names | Audience it asks for | Result |
| --- | --- | --- | --- |
| Under `pvt.whitson.com` | whitson's (`whitson.eu.auth0.com`) | itself | Logs in, no question |
| Under `pvt.whitson.com` | whitson's | anything else | Refused, also with `--trust-host` or `--yes` |
| Under `pvt.whitson.com` | any other | any | Refused, also with `--trust-host` or `--yes` |
| This machine | whitson's | itself | Logs in, no question |
| This machine | whitson's | anything else | Asks first (see below) |
| This machine | any other | any | Asks first (see below) |
| Another host, with `--trust-host` | any | any | Asks first (see below) |

The login server's host must match exactly: `whitson.eu.auth0.com` with the default HTTPS port,
not a subdomain, a lookalike or another Auth0 tenant. A deployment under `pvt.whitson.com` that
names another login server may have been taken over or misconfigured, so the refusal names both
hosts and asks you to report it to whitson; there is no option to continue. The same holds for
one that asks for access to another service, such as another deployment: the tokens would be
valid there, and the deployment you logged in to could use them against it.

Asking first means: the first login to such a deployment from this machine, and a login after its
login server or its audience changed, shows the deployment host and the login server host, and
the audience when it is not the deployment itself, and asks to continue (default no). What is
remembered is the pair of login server and audience of the stored login for that deployment, so
later logins to the same deployment with the same login server and the same audience ask
nothing, and a change of either asks again. Without a terminal, the login is refused unless you
pass `--yes`, which only answers this question. `--yes` never accepts access to another service:
when the audience is not the deployment itself, the login is refused with `--yes` and must be
confirmed at a terminal. In Python, pass `confirm=`, a function that receives a `FirstUse`, `IssuerChanged` or
`AudienceChanged` from `whitson_pvt_sdk.login` (each with `deployment_host`, `issuer_host`,
`foreign_audience` and `describe()`; `IssuerChanged` adds `previous_issuer_host` and
`AudienceChanged` adds `previous_audience`) and returns whether to continue; ask a person
whenever `foreign_audience` is set. Without it, such a login raises `ConfigurationError`. A login
that needs no question needs no `confirm=`.

`login()` also takes `verify=`, a function called with the new login before it is stored;
`login()` returns its result. If it raises, nothing is stored and the previous default stays.
`wpvt auth login` passes a check of `/external/v2/me`; a caller that wants no check passes
`verify=lambda new_login: new_login`.

The issuer, and the authorization, token, device and revocation endpoints it publishes, must be
HTTPS (http only on this machine). The browser, and the page where a device code is entered, are
only ever on the issuer's own scheme, host and port.

Device login (`--device`) is available only on deployments that enable it (`device_login` in
`/external/v2/auth/config`), since a device code can be phished. Elsewhere, log in from a
machine with a browser or use an API token in `WHITSON_PVT_TOKEN`.

These checks apply to logging in. An API token (`token=` or `WHITSON_PVT_TOKEN`) is sent to
the URL you give in `base_url=`, `--url` or `WHITSON_PVT_URL`, over HTTPS (plain HTTP only to
this machine), never to one taken from the default login, and a stored login only ever to its
own deployment.

Library code never starts a login. Scripts and agents should use `WHITSON_PVT_TOKEN`; a login
made with `wpvt auth login` is for people at a terminal, and every SDK client on the machine then
uses it for that deployment.

### Where logins are stored

Logins are profiles keyed by deployment URL, one of them the default. The file is
`credentials.json` in `$XDG_CONFIG_HOME/whitson-pvt/` (default `~/.config/whitson-pvt/`) on
Linux and macOS, and in `%APPDATA%\whitson-pvt\` on Windows. When the `keyring` package is
installed and has a usable backend (macOS Keychain, Windows Credential Manager, Secret Service),
the access and refresh tokens are kept in the OS keyring under the service `whitson-pvt`, and the
file keeps only the non-secret facts: URL, issuer, client id, audience, scopes, expiry, whether
the login is still valid, and the default. Without a usable keyring, or when the keyring refuses
a write, the tokens are kept in the file. To keep tokens out of the keyring, set
`PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`.

If a login is in the keyring and the keyring cannot be read, such as a locked keyring or an SSH
session without a desktop session bus, commands stop with exit code 2 and name the keyring
error. Unlock the keyring (on Linux, log in to the desktop session or start
`gnome-keyring-daemon --unlock`) and try again, or run `wpvt auth login` again in that session:
when the keyring refuses the write, the login is stored in the credentials file instead.
`wpvt auth logout` removes such a login without reading it; it cannot revoke the refresh token
or delete the keyring entries then, and says so.

### Security properties

- **Host binding.** A stored login is only ever sent to the deployment it was issued for. The
  transport compares the scheme, host and port of every request with the login's URL and refuses
  to send it anywhere else, and the client only picks the login stored for its own URL.
- **Private file.** `credentials.json` is created with mode `0600` in a `0700` directory and
  replaced atomically, never widened. The SDK refuses to read a credentials file that other users
  can read or that another user owns, and says how to fix it.
- **Rotation-safe renewal.** The access token is renewed five minutes before it expires and once
  after a 401. Renewal takes a lock on `credentials.lock` next to the file, re-reads the store
  (another process may have renewed already), and saves the rotated refresh token before it lets
  go, so a script and another `wpvt` process can share one login. Another process waits for the
  lock up to 120 s, longer than a renewal can take with the 30 s HTTP timeouts. On Windows, where
  the file cannot be replaced while another process is reading it, the replacement is retried
  briefly.
- **No browser from library code.** Only `wpvt auth login`, or an explicit call to
  `whitson_pvt_sdk.login.login`, starts a login, and only to a trusted deployment that names
  whitson's login server, or after you confirm the hosts (see above).
- Tokens, refresh tokens, authorization codes and PKCE verifiers are never logged or printed.
- **Terminal-safe output.** Text the server controls (names, error messages, login server
  errors) is printed with control characters other than newline and tab shown escaped, such as
  `\x1b`, so a response cannot move the cursor or retitle the terminal. `--json` output is
  JSON-escaped already; `wpvt api` writes the response body unchanged, as `curl` does.

## Development

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — Python package & project manager

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### Setup

```bash
uv sync                           # installs Python deps + dev tools, and the cli and mcp extras' packages
uv tool install rust-just         # installs just (command runner) globally
just install-hooks                # installs the commit message hook
```

### Commit Messages

Commit messages use Conventional Commits so release notes can be generated from
Git history. The local `commit-msg` hook validates messages after running
`just install-hooks`.

Use:

```text
type: subject
type(scope): subject
type!: breaking subject
```

Allowed types are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`,
`ci`, `chore`, and `release`.

Examples:

```text
feat: add pypi publishing workflow
fix(http): normalize localhost base urls
docs: add examples env setup
```

### Tasks

```bash
just lint                        # ruff check
just format                      # ruff format
just ty                          # ty check
just test                        # pytest
just integration                 # opt-in tests against a real API
just build                       # uv build
just plugins-sync                # copy the packaged skill into plugins/wpvt (just lint checks it)
just generate                    # regenerate models and endpoint wrappers from a live API
just generate-file FILE          # regenerate from an OpenAPI file, no API needed
just generate-file-check FILE    # only show what would change
just all                         # generate + lint/format + build
```

`just lint` runs Ruff over the package, `tests/`, `scripts/` and `examples/` with the API
repository's rule set (`ANN401`, `B`, `C4`, `DTZ`, `E`, `F`, `I`, `ICN`, `ISC`, `N`,
`PGH003`, `PIE`, `RET`, `RUF`, `S110`, `S608`, `SIM`, `T201`, `TID251`, `UP`, plus `W`), so
`print` is reserved for `scripts/` and `examples/`. Tests follow the API repository's
`TESTING.md`: they prove behaviour through the public interface, mock only HTTP, the clock and
OS calls, and do not restate generated models or the generator's output.

Integration tests are skipped by default. They create an isolated region, well,
sample, and simple experiment for each run so existing staging data is not modified.
The external API does not currently expose delete endpoints for these resources,
so test data is left behind with unique `sdk-it-*` names.
Run them against a real API by setting an API token:

```bash
export WHITSON_INTEGRATION_BASE_URL=https://internal.pvt.whitson.com
export WHITSON_INTEGRATION_TOKEN=whitson_pvt_...

just integration
```

For local testing without a real token, the API supports
`EXTERNAL_API_AUTH_BYPASS=true` with its local/debug safeguards. Restart the API
using the Flask development CLI, bound to `127.0.0.1` with a local database, then
use `local-pvt-sdk-test-token` as the integration token. See "Local SDK Testing" in
`api/pvt_api/external_api/AGENTS.md` in the API repository. The flag belongs to the
API process, not the SDK; do not enable it in deployments.

Optional IDs enable project, fluid-model, calculation, black-oil-table, and report
checks that cannot be backed by created fixtures: `WHITSON_INTEGRATION_PROJECT_ID`,
`WHITSON_INTEGRATION_FLUID_MODEL_ID`, `WHITSON_INTEGRATION_BLACK_OIL_TABLE_ID`,
`WHITSON_INTEGRATION_SAMPLE_ID`, and `WHITSON_INTEGRATION_REPORT_ID`. The sample ID
must have an adjusted composition in the configured fluid model; conversion is
separately tested with a created sample containing a characterized C7+ residue.
Calculation errors fail tests rather than skipping the dependent endpoints.

The report ID enables real native and OSDU archive round trips, legacy preflight/
import, and all four single-record OSDU endpoints. Choose a report with an available
PDF, wells, samples, and RAFS-supported experiments (CCE/CVD/DLE/MSS). The round-trip
tests use only public SDK methods: export → create a unique region → upload → review
→ commit → read back → delete the staging session → re-export. Native and OSDU
high-fidelity tests compare native data and file hashes and check that the source
report is unchanged. Structured OSDU tests compare the data actually represented in
RAFS, not native-only fields.

The round trip leaves its region and imported entities behind (their IDs are logged);
only the staging session can be deleted through the external API. Export failures
are test failures, not skips, and occur before the round-trip region is created.
Integration requests do not retry, so API errors remain visible. To run just this test:

```bash
uv run pytest tests/integration/test_v2_report_roundtrip.py -v -s -m integration -o addopts=''
```

Use `include_whitson_native_payload=True` and `import_mode="whitson_high_fidelity"`
for full native fidelity. RAFS-only archives do not preserve all native metadata,
composition details, primary-experiment flags, or saturation-pressure classifications.
JSON-only File.Generic import intentionally returns an unsupported record without
committing file bytes; use archive import for files. Single-record analysis metadata
needs a reviewed `resolved_payload` with experiment data before committing; set its
`entity_type` discriminator explicitly.

The OpenAPI/wiring test requires only `WHITSON_INTEGRATION_BASE_URL`, not a token.

### Publishing

Publishing uses GitHub Actions and PyPI Trusted Publishing; no PyPI API token is
stored in this repository. Configure the `whitson-pvt-sdk` project on PyPI to
trust this GitHub repository and the `pypi` environment, then publish a GitHub
Release to build and upload the package.

Before creating a release, update `version` in `pyproject.toml` and run:

```bash
just test
just lint
just ty
just publish-check
just release-notes 0.1.1
```

`just release-notes` generates deterministic Markdown from Conventional Commits
since the previous Git tag. Create the GitHub Release with:

```bash
just release 0.1.1
```

The release recipe writes generated notes to a temporary file and passes them to
`gh release create`. Publishing to PyPI starts when the GitHub Release is
published. The GitHub CLI must be authenticated with release permissions; use
`gh auth login` and `gh auth status` to set up and verify access.

### Code generation

Generated code comes from the external API's OpenAPI document. `just generate`
fetches `/external/{version}/docs/openapi.json` from the configured `BASE_URL`;
`just generate-file FILE` reads a saved document instead, so no API has to run.
Every generate recipe takes the API version as an optional last argument (such
as `just generate-file FILE v2`); without it, the generator uses the latest
version it supports (`LATEST_VERSION` in `scripts/sdk_generator/config.py`). Both
run `datamodel-code-generator` for Pydantic models, then the repo-specific
generator in `scripts/sdk_generator/` for endpoint modules and resource facades.
The `-check` recipes only print the diff.

Generated outputs live under:

- `whitson_pvt_sdk/_generated/v2/models.py`
- `whitson_pvt_sdk/_generated/v2/resources.py`
- `whitson_pvt_sdk/v2/models/__init__.py` re-exports generated models

`whitson_pvt_sdk/v2/resources.py` re-exports the public resource classes and adds
hand-written conveniences. Resource classes call `HTTPTransport` directly and expose
SDK-shaped method names such as `list`, `get`, `create`, `update`, `create_bulk`, and
`update_bulk`.

Authentication endpoints are intentionally excluded from generated resources;
auth is infrastructure owned by `whitson_pvt_sdk.auth` and `HTTPTransport`.

### Working in a whitsonPVT workspace

The whitsonPVT app repository can add this repository to a development workspace
as an optional `sdk/` worktree next to `app/` and `utils/`:

```bash
mise create NAME --sdk           # in the app repository; also adds it to an existing workspace
```

The SDK branch defaults to the app branch name and starts from `origin/main`.
Creating it runs `uv sync` and installs the commit message hook. Work in `sdk/`
with this repository's own recipes (`mise exec -- just RECIPE` outside a
mise-activated shell):

```bash
just test                                                    # unit tests
just lint && just ty                                         # lint and type check
just generate-file ../app/api/openapi-external.json          # regenerate from the workspace's API
just generate-file-check ../app/api/openapi-external.json    # only show the drift
just integration                                             # integration tests against the workspace API
```

The app repository commits `api/openapi-external.json` and keeps it current. For
`just integration` the workspace presets `WHITSON_INTEGRATION_BASE_URL` (always)
and `WHITSON_INTEGRATION_TOKEN` (the API's local bypass token, unless you export
your own); start the API with `EXTERNAL_API_AUTH_BYPASS=true mise api:dev` first.
It writes test data to the workspace database. Commit and release from `sdk/` as
usual.

### Package structure

```
whitson_pvt_sdk/
├── __init__.py              # WhitsonPVTClient
├── credentials.py           # ApiToken and StoredLogin, the two credential kinds
├── auth.py                  # URL and credential resolution; the httpx2.Auth that sends them
├── login.py                 # login (browser with PKCE, or device) and logout
├── _login_page.py           # the pages the browser login's listener answers with
├── _store.py                # the credential store: credentials.json, keyring, lock
├── _refresh.py              # renewal of a stored login under the store lock
├── _oauth.py                # OAuth/OIDC wire protocol: /auth/config, discovery, token requests
├── _trust.py                # which deployments a login may start for and where it signs in
├── cli/                     # the wpvt command (Typer; the cli extra): auth, data commands,
│                            #   export, calc, api, mcp
├── http.py                  # HTTPTransport (httpx2, retries, error mapping)
├── errors.py                # SDKError, ConfigurationError, ResponseError, ...
├── shared/models.py         # hand-maintained shared models
├── shared/pagination.py     # Paginator utility
├── _generated/              # generated models and resource facades
└── v2/                      # public resources and model re-exports
```

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](https://github.com/WhitsonAS/whitson-pvt-sdk/blob/main/LICENSE).
