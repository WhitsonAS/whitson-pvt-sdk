import argparse
import re
import subprocess
from collections import defaultdict

SECTIONS = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "docs": "Documentation",
    "refactor": "Refactors",
    "test": "Tests",
    "build": "Build",
    "ci": "CI",
    "chore": "Maintenance",
    "release": "Release",
}

SECTION_ORDER = (
    "Features",
    "Fixes",
    "Performance",
    "Documentation",
    "Refactors",
    "Tests",
    "Build",
    "CI",
    "Maintenance",
    "Release",
    "Other",
)

COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$"
)


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def previous_tag() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None


def commit_subjects(rev_range: str) -> list[str]:
    output = run_git(["log", "--pretty=format:%s (%h)", rev_range])
    return [line for line in output.splitlines() if line]


def parse_commit(subject: str) -> tuple[str, str]:
    match = COMMIT_RE.match(subject)
    if not match:
        return "Other", subject

    commit_type = match.group("type")
    section = SECTIONS.get(commit_type, "Other")
    scope = match.group("scope")
    breaking = match.group("breaking")
    message = match.group("subject")
    if scope:
        message = f"{scope}: {message}"
    if breaking:
        message = f"BREAKING: {message}"
    return section, message


def should_include_commit(subject: str) -> bool:
    return not subject.startswith(("Merge ", "Revert ", "fixup! ", "squash! "))


def render_release_notes(subjects: list[str], *, previous: str | None, version: str | None) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for subject in subjects:
        if not should_include_commit(subject):
            continue
        section, message = parse_commit(subject)
        grouped[section].append(message)

    title = f"# v{version}" if version else "# Release Notes"
    lines = [title, ""]
    if previous:
        lines.extend([f"Changes since `{previous}`.", ""])
    else:
        lines.extend(["Initial release.", ""])

    wrote_section = False
    for section in SECTION_ORDER:
        items = grouped.get(section)
        if not items:
            continue
        wrote_section = True
        lines.extend([f"## {section}", ""])
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    if not wrote_section:
        lines.extend(["No user-facing changes.", ""])

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release notes from commit subjects.")
    parser.add_argument("version", nargs="?", help="Version number without a leading v.")
    parser.add_argument("--from", dest="from_ref", help="Start ref. Defaults to previous tag.")
    parser.add_argument("--to", dest="to_ref", default="HEAD", help="End ref. Defaults to HEAD.")
    args = parser.parse_args()

    previous = args.from_ref or previous_tag()
    rev_range = f"{previous}..{args.to_ref}" if previous else args.to_ref
    subjects = commit_subjects(rev_range)
    print(render_release_notes(subjects, previous=previous, version=args.version), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
