# Agent Notes

Start by reading the relevant existing module before changing behavior. Keep edits narrow and aligned with nearby patterns.

## Commands

- Setup: `uv sync`; install the task runner with `uv tool install rust-just` if `just` is missing.
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
- `whitson_pvt_sdk/auth.py` owns credentials: the `ApiToken` model (`SecretStr`), resolution from `token=` then `WHITSON_PVT_TOKEN`, and the `httpx.Auth` that writes the bearer. A new credential kind is a new model there plus one `match` arm in `CredentialAuth.auth_flow` and in `resolve_credential`. Never log, print or put a token in an error.
- `HTTPTransport` owns the `base_url.rstrip('/') + /external/v2` prefix, timeouts, retries (decided by `_retry.retry_delay`), error mapping, JSON parsing, bytes downloads, and multipart uploads.
- Public resource classes in `whitson_pvt_sdk/v2/resources.py` usually re-export generated facades from `whitson_pvt_sdk/_generated/v2/resources.py`; put manual SDK conveniences there by subclassing/wrapping generated classes.
- Generated resource methods use SDK-shaped names (`list`, `get`, `create`, `update`, `create_bulk`, `update_bulk`) while lower-level generated module functions keep OpenAPI operation IDs.
- v2 list endpoints use paginated models for regions/projects/fluid models/black oil tables/wells.
- Report import/export is special: export returns raw zip bytes plus a synthetic filename, and import/preflight upload `archive.zip` with optional `meta_data` serialized from `ImportArchiveOptions`.
- The agent skill ships in the wheel at `whitson_pvt_sdk/.agents/skills/whitson-pvt/SKILL.md` (Library Skills layout); keep it in step with the public API.
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
