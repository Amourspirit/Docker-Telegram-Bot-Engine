from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_EXTENSIONS = {".json", ".yaml", ".yml"}


def _expand_braces(pattern: str) -> list[str]:
    """Expand simple brace expressions like **/*.{json,yml}."""
    start = pattern.find("{")
    if start == -1:
        return [pattern]

    end = pattern.find("}", start + 1)
    if end == -1:
        return [pattern]

    prefix = pattern[:start]
    suffix = pattern[end + 1 :]
    options = [item.strip() for item in pattern[start + 1 : end].split(",") if item.strip()]
    if not options:
        return [pattern]

    expanded: list[str] = []
    for option in options:
        expanded.extend(_expand_braces(f"{prefix}{option}{suffix}"))
    return expanded


def _normalize_manifest_lines(manifest_path: Path) -> list[str]:
    raw = manifest_path.read_text(encoding="utf-8").splitlines()
    result: list[str] = []
    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        result.append(stripped)
    return result


def collect_input_files(
    base_dir: Path,
    input_values: tuple[str, ...],
    stdin_manifest: str | None,
) -> list[Path]:
    tokens = list(input_values)
    if stdin_manifest:
        manifest_path = Path(stdin_manifest).expanduser()
        if not manifest_path.is_absolute():
            manifest_path = (base_dir / manifest_path).resolve()
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        tokens.extend(_normalize_manifest_lines(manifest_path))

    if not tokens:
        raise ValueError("At least one input source must be provided via --input or --stdin-manifest")

    resolved: set[str] = set()
    for token in tokens:
        for pattern in _expand_braces(token):
            candidate = Path(pattern).expanduser()
            if glob.has_magic(pattern):
                if candidate.is_absolute():
                    matches = glob.glob(pattern, recursive=True)
                else:
                    rel_matches = glob.glob(pattern, root_dir=str(base_dir), recursive=True)
                    matches = [str((base_dir / match).resolve()) for match in rel_matches]
            else:
                literal = candidate if candidate.is_absolute() else (base_dir / candidate)
                matches = [str(literal.resolve())] if literal.exists() else []

            for match in matches:
                path = Path(match).resolve()
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    resolved.add(str(path))

    if not resolved:
        raise ValueError("No supported input files were found (.json, .yaml, .yml)")

    return [Path(item) for item in sorted(resolved)]


def _ensure_mapping(payload: Any, file_path: Path) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"File must contain a top-level mapping: {file_path}")
    return payload


def load_payload(file_path: Path) -> dict[str, Any]:
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return _ensure_mapping(json.loads(text), file_path)
    if suffix in {".yaml", ".yml"}:
        return _ensure_mapping(yaml.safe_load(text), file_path)
    raise ValueError(f"Unsupported file extension: {file_path}")


def enforce_string_keys(data: Any, context: str) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError(f"Non-string key found in {context}: {key!r}")
            enforce_string_keys(value, context)
    elif isinstance(data, list):
        for item in data:
            enforce_string_keys(item, context)


def serialize_payload(payload: dict[str, Any], output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if normalized in {"yaml", "yml"}:
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    raise ValueError(f"Unsupported output format: {output_format}")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
