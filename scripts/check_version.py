import argparse
import re
from pathlib import Path

VERSION_RE = re.compile(r'^version = "(?P<version>[^"]+)"$', re.MULTILINE)


def read_project_version(pyproject_path: Path) -> str:
    match = VERSION_RE.search(pyproject_path.read_text())
    if not match:
        raise ValueError(f"Could not find project version in {pyproject_path}")
    return match.group("version")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert pyproject.toml has the expected version.")
    parser.add_argument("version", help="Expected package version without a leading v.")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml",
    )
    args = parser.parse_args()

    actual = read_project_version(args.pyproject)
    if actual != args.version:
        print(
            f"Version mismatch: pyproject.toml has {actual!r}, expected {args.version!r}",
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
