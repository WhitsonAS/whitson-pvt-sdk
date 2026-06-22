from pathlib import Path

import pytest

from scripts.check_version import read_project_version


def test_read_project_version(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "pkg"\nversion = "1.2.3"\n')

    assert read_project_version(pyproject) == "1.2.3"


def test_read_project_version_raises_when_missing(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "pkg"\n')

    with pytest.raises(ValueError, match="Could not find project version"):
        read_project_version(pyproject)
