from scripts.release_notes import parse_commit, render_release_notes, should_include_commit


def test_parse_commit_groups_conventional_types():
    assert parse_commit("feat: add publishing workflow (abc123)") == (
        "Features",
        "add publishing workflow (abc123)",
    )
    assert parse_commit("fix(http): normalize base urls (def456)") == (
        "Fixes",
        "http: normalize base urls (def456)",
    )


def test_parse_commit_marks_breaking_changes():
    assert parse_commit("feat!: remove legacy auth resource (abc123)") == (
        "Features",
        "BREAKING: remove legacy auth resource (abc123)",
    )


def test_parse_commit_keeps_unknown_subjects_in_other():
    assert parse_commit("manual release note (abc123)") == ("Other", "manual release note (abc123)")


def test_should_include_commit_skips_generated_commit_subjects():
    assert not should_include_commit("Merge pull request #1 (abc123)")
    assert not should_include_commit("Revert \"feat: add publishing workflow\" (abc123)")
    assert not should_include_commit("fixup! feat: add publishing workflow (abc123)")
    assert not should_include_commit("squash! feat: add publishing workflow (abc123)")
    assert should_include_commit("feat: add publishing workflow (abc123)")


def test_render_release_notes_groups_sections_in_order():
    notes = render_release_notes(
        [
            "docs: add env setup (111111)",
            "feat: add publishing workflow (222222)",
            "fix(http): normalize base urls (333333)",
        ],
        previous="v0.1.0",
        version="0.1.1",
    )

    assert notes == """Changes since `v0.1.0`.

## Features

- add publishing workflow (222222)

## Fixes

- http: normalize base urls (333333)

## Documentation

- add env setup (111111)
"""


def test_render_release_notes_handles_empty_release():
    notes = render_release_notes([], previous="v0.1.0", version="0.1.1")

    assert notes == """Changes since `v0.1.0`.

No user-facing changes.
"""
