from pathlib import Path

import pytest

from builder.project_root import find_project_root


def test_find_project_root_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (root / ".project_root").write_text("\n", encoding="utf-8")

    assert find_project_root(nested) == root


def test_find_project_root_raises_when_missing(tmp_path: Path) -> None:
    start = tmp_path / "no-root"
    start.mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        find_project_root(start)
