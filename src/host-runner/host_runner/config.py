from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class HostOperationDefinition:
    command: list[str]
    timeout_seconds: float | None = None
    allow_user_args: bool = False
    allowed_placeholders: tuple[str, ...] = ()


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path).expanduser()
    if path.is_absolute():
        return path

    project_root = Path(__file__).resolve().parents[3]
    return (project_root / path).resolve()


def _load_operations_from_payload(payload: dict[str, Any]) -> dict[str, HostOperationDefinition]:
    operations = payload.get("operations", {})
    if not isinstance(operations, dict):
        raise ValueError("Host action config must contain an 'operations' mapping")

    result: dict[str, HostOperationDefinition] = {}
    for operation_name, operation_config in operations.items():
        if not isinstance(operation_config, dict):
            raise ValueError(f"Operation '{operation_name}' must be a mapping")

        command = operation_config.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ValueError(f"Operation '{operation_name}' must define a non-empty string command list. Ensure that any command numbers are converted to strings in the config file.")

        timeout_seconds = operation_config.get("timeout_seconds")
        if timeout_seconds is not None:
            timeout_seconds = float(timeout_seconds)

        allow_user_args = bool(operation_config.get("allow_user_args", False))
        raw_allowed_placeholders = operation_config.get("allowed_placeholders", [])
        if raw_allowed_placeholders is None:
            raw_allowed_placeholders = []
        if not isinstance(raw_allowed_placeholders, list):
            raise ValueError(
                f"Operation '{operation_name}' allowed_placeholders must be a list of strings"
            )

        normalized_allowed_placeholders: list[str] = []
        for placeholder_name in raw_allowed_placeholders:
            if not isinstance(placeholder_name, str) or not placeholder_name.strip():
                raise ValueError(
                    f"Operation '{operation_name}' allowed_placeholders entries must be non-empty strings"
                )
            if placeholder_name not in normalized_allowed_placeholders:
                normalized_allowed_placeholders.append(placeholder_name)

        result[operation_name] = HostOperationDefinition(
            command=list(command),
            timeout_seconds=timeout_seconds,
            allow_user_args=allow_user_args,
            allowed_placeholders=tuple(normalized_allowed_placeholders),
        )

    return result


def load_operations_from_text(config_text: str, config_format: str) -> dict[str, HostOperationDefinition]:
    normalized = config_format.strip().lower()
    if normalized == "json":
        payload = json.loads(config_text)
    elif normalized in {"yaml", "yml"}:
        payload = yaml.safe_load(config_text)
        if payload is None:
            payload = {}
    else:
        raise ValueError(f"Unsupported host action config format: {config_format}")

    if not isinstance(payload, dict):
        raise ValueError("Host action config must be a mapping with an 'operations' key")

    return _load_operations_from_payload(payload)


def load_operations_from_file(config_path: str) -> dict[str, HostOperationDefinition]:
    path = _resolve_config_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Host action config file not found: {config_path}")

    config_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        config_format = "json"
    elif suffix in {".yaml", ".yml"}:
        config_format = "yaml"
    else:
        raise ValueError("Unsupported host action config extension. Use .json, .yaml, or .yml")

    return load_operations_from_text(config_text, config_format)