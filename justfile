# ── code generation ───────────────────────────────────────────────
BASE_URL := "http://localhost:4000/external"

# VERSION defaults to the latest API version the generator supports
generate version='':
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}}

generate-models version='':
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --models-only

generate-endpoints version='':
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --endpoints-only

generate-check version='':
    uv run python scripts/generate_sdk.py {{version}} --base-url {{BASE_URL}} --check

# Generate from an OpenAPI file instead of a live API
generate-file file version='':
    uv run python scripts/generate_sdk.py {{version}} --openapi {{file}}

generate-file-check file version='':
    uv run python scripts/generate_sdk.py {{version}} --openapi {{file}} --check

# ── lint & typecheck ──────────────────────────────────────────────
install-hooks:
    uv run prek install --hook-type commit-msg

lint +files='whitson_pvt_sdk/ tests/ scripts/ examples/': plugins-check
    uv run ruff check {{files}}

lint-fix +files='whitson_pvt_sdk/ tests/ scripts/ examples/':
    uv run ruff check {{files}} --fix

format:
    uv run ruff format whitson_pvt_sdk/

fmt format:


ty +files='':
    uv run ty check --extra-search-path scripts --force-exclude {{files}}

check: lint format ty
    @echo "All checks passed"

# ── plugins ───────────────────────────────────────────────────────
# Copy the packaged skills into plugins/wpvt/skills, the plugin's copy
plugins-sync:
    uv run python scripts/sync_plugins.py

plugins-check:
    uv run python scripts/sync_plugins.py --check

# ── test ───────────────────────────────────────────────────────────
test:
    uv run pytest tests/ -v

integration:
    uv run pytest tests/integration/ -v -m integration -o addopts=''

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
    uv run python scripts/check_version.py {{version}}

prepare-release version='': test lint ty publish-check

release-notes version='':
    uv run python scripts/release_notes.py {{version}}

github-release version target='HEAD':
    uv run python scripts/release_notes.py {{version}} > /tmp/whitson-pvt-sdk-release-notes.md
    gh release create v{{version}} --target "{{target}}" --title "v{{version}}" --notes-file /tmp/whitson-pvt-sdk-release-notes.md

# Dispatch the GitHub release workflow; CI bumps, validates, tags, releases, and publishes.
release version:
    gh workflow run publish.yml --ref main -f version={{version}}

# ── run all ───────────────────────────────────────────────────────
all: generate lint-fix format ty build
