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
            raise ValueError(f"Operation '{operation_name}' must define a non-empty string command list")

        timeout_seconds = operation_config.get("timeout_seconds")
        if timeout_seconds is not None:
            timeout_seconds = float(timeout_seconds)

        allow_user_args = bool(operation_config.get("allow_user_args", False))
        result[operation_name] = HostOperationDefinition(
            command=list(command),
            timeout_seconds=timeout_seconds,
            allow_user_args=allow_user_args,
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
    path = Path(config_path)
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