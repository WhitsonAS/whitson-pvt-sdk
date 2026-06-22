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
install-hooks:
    uv run prek install --hook-type commit-msg

lint +files='whitson_pvt_sdk/':
    uv run ruff check {{files}}

lint-fix +files='whitson_pvt_sdk/':
    uv run ruff check {{files}} --fix

format:
    uv run ruff format whitson_pvt_sdk/

fmt format:


ty +files='':
    uv run ty check --extra-search-path scripts --force-exclude {{files}}

check: lint format ty
    @echo "All checks passed"

# ── test ───────────────────────────────────────────────────────────
test:
    uv run pytest tests/ -v

test-cov:
    uv run pytest tests/ -v --cov=whitson_pvt_sdk --cov-report=term-missing

# ── build ─────────────────────────────────────────────────────────
build:
    rm -rf dist
    uv build

publish-check: build
    uvx twine check dist/*

bump-version version:
    uv version {{version}}

prepare-release version: (bump-version version) test lint ty publish-check

release-notes version='':
    uv run python scripts/release_notes.py {{version}}

# Create a GitHub Release from the committed package version; publishing to PyPI is handled by GitHub Actions.
release version:
    git diff --quiet
    git diff --cached --quiet
    uv run python scripts/check_version.py {{version}}
    uv run python scripts/release_notes.py {{version}} > /tmp/whitson-pvt-sdk-release-notes.md
    gh release create v{{version}} --title "v{{version}}" --notes-file /tmp/whitson-pvt-sdk-release-notes.md

# ── run all ───────────────────────────────────────────────────────
all: generate-all lint-fix format ty build
