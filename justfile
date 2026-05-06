# ── code generation ───────────────────────────────────────────────
OPENAPI_URL := "https://internal.pvt.whitson.com/external/v1/docs/openapi.json"
OUTPUT := "whitson_pvt_sdk/models/_generated.py"

generate:
    uv run datamodel-codegen --url {{OPENAPI_URL}} --output {{OUTPUT}}
    @echo "Models regenerated → {{OUTPUT}}"

# ── lint & typecheck ──────────────────────────────────────────────
lint:
    uv run ruff check whitson_pvt_sdk/

lint-fix:
    uv run ruff check whitson_pvt_sdk/ --fix

format:
    uv run ruff format whitson_pvt_sdk/

fmt format:


ty:
    uv run ty check

check: lint format ty
    @echo "All checks passed"

# ── build ─────────────────────────────────────────────────────────
build:
    uv build

# ── run all ───────────────────────────────────────────────────────
all: generate lint-fix format ty build
