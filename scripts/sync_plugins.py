import argparse
import json
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "whitson_pvt_sdk" / ".agents" / "skills"
TARGET = ROOT / "plugins" / "wpvt" / "skills"
MANIFESTS = (
    ROOT / "plugins" / "wpvt" / "plugin.json",
    ROOT / "plugins" / "wpvt" / ".claude-plugin" / "plugin.json",
)


def stale_versions() -> list[str]:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    return [
        f"{manifest.relative_to(ROOT)} has version {found!r}, pyproject.toml has {version!r}"
        for manifest in MANIFESTS
        if (found := json.loads(manifest.read_text()).get("version")) != version
    ]


def tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the packaged agent skills into the wpvt plugin, or check the copy."
    )
    parser.add_argument("--check", action="store_true", help="Fail if the copy differs.")
    args = parser.parse_args()

    source = tree(SOURCE)
    if not source:
        print(f"No skills found in {SOURCE.relative_to(ROOT)}", file=sys.stderr)
        return 1
    if versions := stale_versions():
        print("; ".join(versions) + ". Set the plugin version to match.", file=sys.stderr)
        return 1
    if args.check:
        target = tree(TARGET)
        stale = sorted(
            name for name in source.keys() | target.keys() if source.get(name) != target.get(name)
        )
        if stale:
            print(
                f"{TARGET.relative_to(ROOT)} differs from {SOURCE.relative_to(ROOT)}: "
                f"{', '.join(stale)}. Run `just plugins-sync` and commit the result.",
                file=sys.stderr,
            )
            return 1
        return 0
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("__pycache__"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
