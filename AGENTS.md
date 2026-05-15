# Agent Notes

Start by reading the relevant existing module before changing behavior. Keep edits narrow and aligned with nearby v1/v2 patterns.

## Commands

- Setup: `uv sync`; install the task runner with `uv tool install rust-just` if `just` is missing.
- Focused checks: `just lint`, `just ty`, `just build`.
- `just check` runs `lint -> format -> ty`; it is not read-only because `format` runs `ruff format whitson_pvt_sdk/`.
- `just all` regenerates models, applies lint fixes/formatting, typechecks, then builds.
- No test suite is configured in this repo; do not invent a pytest command unless tests are added.

## Codegen

- Treat `whitson_pvt_sdk/models/v1/_generated.py` and `whitson_pvt_sdk/models/v2/_generated.py` as generated Pydantic model output.
- Regenerate only when a live local API is available at `http://localhost:4000`; use `just generate v1`, `just generate v2`, or `just generate-all`, which fetch `http://localhost:4000/external/{version}/docs/openapi.json`.
- Put hand-maintained models in `whitson_pvt_sdk/models/manual.py`; avoid hand-editing generated files unless intentionally patching generated output when the API spec is unavailable.

## Architecture

- Public entrypoint is `WhitsonPVTClient` in `whitson_pvt_sdk/__init__.py`; it only wires `v1` or `v2` resources.
- `HTTPTransport` owns the `base_url.rstrip('/') + /external/{version}` prefix, Auth0 bearer auth, timeouts, error mapping, JSON parsing, bytes downloads, and multipart uploads.
- Resource classes in `whitson_pvt_sdk/v1/resources.py` and `v2/resources.py` are thin facades over same-named module functions.
- Keep v1/v2 behavior aligned unless generated models intentionally differ; v2 list endpoints use paginated models for regions/projects/fluid models/black oil tables.
- Report import/export is special: export returns raw zip bytes plus a synthetic filename, and import/preflight upload `archive.zip` with optional `meta_data` serialized from `ExternalImportArchiveOptions`.

## Endpoint Wrappers

For new endpoint wrappers:

1. Add the thin module function near related functions.
2. Call `HTTPTransport.get`, `post`, `put`, `get_bytes`, or `post_multipart`.
3. Serialize Pydantic inputs with `model_dump(exclude_unset=True)`.
4. Validate structured responses with the generated model's `model_validate`.
5. Add or update the matching resource facade method.
6. Keep v1 and v2 behavior aligned unless generated models intentionally differ.

## Final Checks

Before finishing a change, run the narrowest applicable checks: `just lint`, `just ty`, and/or `just build`.

Mention if a check was skipped because it would format, regenerate code, require the local API, or depend on missing tooling.
