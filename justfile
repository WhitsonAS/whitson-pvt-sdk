# ── code generation ───────────────────────────────────────────────
BASE_URL := "http://localhost:4000/external"
OUTPUT_DIR := "whitson_pvt_sdk/models"

generate version:
    uv run datamodel-codegen --url {{BASE_URL}}/{{version}}/docs/openapi.json --output {{OUTPUT_DIR}}/{{version}}/_generated.py
    @echo "{{version}} models → {{OUTPUT_DIR}}/{{version}}/_generated.py"

generate-all:
    just generate v1
    just generate v2

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

# ── test ───────────────────────────────────────────────────────────
test:
    uv run pytest tests/ -v

test-cov:
    uv run pytest tests/ -v --cov=whitson_pvt_sdk --cov-report=term-missing

# ── build ─────────────────────────────────────────────────────────
build:
    uv build

# ── run all ───────────────────────────────────────────────────────
all: generate-all lint-fix format ty build
