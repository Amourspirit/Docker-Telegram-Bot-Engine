from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path) -> Path:
    """Walk up from start until a directory containing .project_root is found."""
    candidate = start if start.is_dir() else start.parent
    candidate = candidate.resolve()

    for path in (candidate, *candidate.parents):
        if (path / ".project_root").is_file():
            return path

    raise FileNotFoundError("Could not locate .project_root in parent directories")
