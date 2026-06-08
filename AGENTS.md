# Agent Notes

Start by reading the relevant existing module before changing behavior. Keep edits narrow and aligned with nearby v1/v2 patterns.

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

- Treat `whitson_pvt_sdk/_generated/**` and `whitson_pvt_sdk/{v1,v2}/models/__init__.py` as generated output.
- Regenerate only when a live local API is available at `http://localhost:4000`; use `just generate v1`, `just generate v2`, or `just generate-all`, which fetch `http://localhost:4000/external/{version}/docs/openapi.json`.
- The repo-specific generator lives in `scripts/sdk_generator/`. It runs `ruff check --fix --select I,F401` and `ruff format` on rendered endpoint/resource files, so generated files should not require a second formatting pass.
- Put hand-maintained shared models in `whitson_pvt_sdk/shared/models.py`; avoid hand-editing generated files unless intentionally patching generated output when the API spec is unavailable.
- Authentication is excluded from generated resources via `EXCLUDED_RESOURCES`; keep auth as transport infrastructure, not as `client.authentication`.

## Architecture

- Public entrypoint is `WhitsonPVTClient` in `whitson_pvt_sdk/__init__.py`; it wires `v1` or `v2` resources and exposes `get_access_token()` for explicit token reuse.
- `HTTPTransport` owns the `base_url.rstrip('/') + /external/{version}` prefix, Auth0 bearer auth, token caching, timeouts, error mapping, JSON parsing, bytes downloads, and multipart uploads.
- Public resource classes in `whitson_pvt_sdk/v1/resources.py` and `v2/resources.py` re-export generated facades from `whitson_pvt_sdk/_generated/{version}/resources.py`.
- Generated resource methods use SDK-shaped names (`list`, `get`, `create`, `update`, `create_bulk`, `update_bulk`) while lower-level generated module functions keep OpenAPI operation IDs.
- Keep v1/v2 behavior aligned unless generated models intentionally differ; v2 list endpoints use paginated models for regions/projects/fluid models/black oil tables/wells.
- Report import/export is special: export returns raw zip bytes plus a synthetic filename, and import/preflight upload `archive.zip` with optional `meta_data` serialized from `ExternalImportArchiveOptions`.

## Endpoint Wrappers

For new endpoint wrappers or generator behavior:

1. Prefer changing `scripts/sdk_generator/` and regenerating over hand-editing generated endpoint/resource files.
2. Call `HTTPTransport.get`, `post`, `put`, `get_bytes`, or `post_multipart`.
3. Serialize Pydantic inputs with `model_dump(exclude_unset=True)`.
4. Validate structured responses with the generated model's `model_validate`.
5. Add or update the matching resource facade method through generator inference or `OVERRIDES`.
6. Keep v1 and v2 behavior aligned unless generated models intentionally differ.

## Final Checks

Before finishing a change, run the narrowest applicable checks: `just test`, `just lint`, `just ty`, and/or `just build`.

Mention if a check was skipped because it would format, regenerate code, require the local API, or depend on missing tooling.
