# ── code generation ───────────────────────────────────────────────
BASE_URL := "http://localhost:4000/external"

generate version:
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}}

generate-models version:
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --models-only

generate-endpoints version:
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --endpoints-only

generate-check version:
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --check

generate-all:
    uv run python scripts/generate_sdk.py all --base-url {{BASE_URL}}

# ── lint & typecheck ──────────────────────────────────────────────
lint +files='whitson_pvt_sdk/':
    uv run ruff check {{files}}

lint-fix +files='whitson_pvt_sdk/':
    uv run ruff check {{files}} --fix

format:
    uv run ruff format whitson_pvt_sdk/

fmt format:


ty +files='':
    uv run ty check --force-exclude {{files}}

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
