# ── code generation ───────────────────────────────────────────────
OPENAPI_URL := "https://internal.pvt.whitson.com/external/v1/docs/openapi.json"
OUTPUT := "whitson_pvt_sdk/models/_generated.py"

generate:
    curl -s {{OPENAPI_URL}} | \
        uv run datamodel-codegen \
            --input-file-type openapi \
            --target-python-version 3.10 \
            --snake-case-field \
            --use-field-description \
            --use-standard-collections \
            --output {{OUTPUT}} \
            --base-class pydantic.BaseModel \
            --enum-field-as-literal all \
            --field-constraints \
            --formatters ruff-check ruff-format
    @echo "Models regenerated → {{OUTPUT}}"

# ── lint ──────────────────────────────────────────────────────────
lint:
    uv run ruff check whitson_pvt_sdk/

lint-fix:
    uv run ruff check whitson_pvt_sdk/ --fix

format:
    uv run ruff format whitson_pvt_sdk/

fmt format:

check: lint format
    @echo "All checks passed"

# ── build ─────────────────────────────────────────────────────────
build:
    uv build

# ── run all ───────────────────────────────────────────────────────
all: generate lint-fix format build
