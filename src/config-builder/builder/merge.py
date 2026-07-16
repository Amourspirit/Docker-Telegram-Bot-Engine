from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DuplicateRecord:
    key: str
    kept_from: str
    skipped_from: str


def merge_sections(sections: list[tuple[Path, dict[str, Any]]]) -> tuple[dict[str, Any], list[DuplicateRecord]]:
    merged: dict[str, Any] = {}
    source_by_key: dict[str, str] = {}
    duplicates: list[DuplicateRecord] = []

    for file_path, section in sections:
        for raw_key, value in section.items():
            key = str(raw_key)
            source = str(file_path)
            if key in merged:
                duplicates.append(
                    DuplicateRecord(
                        key=key,
                        kept_from=source_by_key[key],
                        skipped_from=source,
                    )
                )
                continue

            merged[key] = value
            source_by_key[key] = source

    return merged, duplicates
