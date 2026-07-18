from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True, frozen=True)
class ReplyFormatRule:
    """A single parameter-based reply-format rule for an operation.

    ``singles`` matches when *any* listed param is present (OR).
    ``and_groups`` matches when *all* params in *any* group are present.
    """

    format_name: str
    singles: tuple[str, ...] = ()
    and_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(slots=True, frozen=True)
class ReplyFormatMatrix:
    """Resolves a reply-format name from the optional params that are present."""

    default: str = "markdown"
    rules: tuple[ReplyFormatRule, ...] = ()

    def resolve(self, present_params: set[str]) -> str:
        for rule in self.rules:
            if any(single in present_params for single in rule.singles):
                return rule.format_name
            if any(
                group and set(group).issubset(present_params)
                for group in rule.and_groups
            ):
                return rule.format_name
        return self.default


@dataclass(slots=True)
class HostOperationDefinition:
    command: list[str]
    timeout_seconds: float | None = None
    allow_user_args: bool = False
    allowed_placeholders: tuple[str, ...] = ()
    allowed_optional_params: tuple[str, ...] = ()
    reply_format: ReplyFormatMatrix | None = None


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path).expanduser()
    if path.is_absolute():
        return path

    project_root = Path(__file__).resolve().parents[3]
    return (project_root / path).resolve()


def _normalize_param_list(raw: Any, operation_name: str, context: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(
            f"Operation '{operation_name}' reply_format {context} must be a list of strings"
        )
    params: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"Operation '{operation_name}' reply_format {context} entries must be non-empty strings"
            )
        params.append(item)
    return tuple(params)


def _parse_reply_format_rule_blocks(
    format_name: str, raw_blocks: Any, operation_name: str
) -> ReplyFormatRule:
    # Accept a single block mapping or a list of block mappings.
    if isinstance(raw_blocks, dict):
        blocks = [raw_blocks]
    elif isinstance(raw_blocks, list):
        blocks = raw_blocks
    else:
        raise ValueError(
            f"Operation '{operation_name}' reply_format '{format_name}' must be a mapping or list of mappings"
        )

    singles: list[str] = []
    and_groups: list[tuple[str, ...]] = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError(
                f"Operation '{operation_name}' reply_format '{format_name}' blocks must be mappings"
            )
        if "single" in block:
            singles.extend(
                _normalize_param_list(block.get("single"), operation_name, f"'{format_name}'.single")
            )
        if "ands" in block:
            raw_ands = block.get("ands")
            if not isinstance(raw_ands, list):
                raise ValueError(
                    f"Operation '{operation_name}' reply_format '{format_name}'.ands must be a list"
                )
            for and_entry in raw_ands:
                if not isinstance(and_entry, dict) or "and" not in and_entry:
                    raise ValueError(
                        f"Operation '{operation_name}' reply_format '{format_name}'.ands "
                        "entries must be mappings with an 'and' list"
                    )
                and_groups.append(
                    _normalize_param_list(
                        and_entry.get("and"), operation_name, f"'{format_name}'.ands.and"
                    )
                )

    return ReplyFormatRule(
        format_name=format_name,
        singles=tuple(singles),
        and_groups=tuple(and_groups),
    )


def _parse_reply_format(raw: Any, operation_name: str) -> ReplyFormatMatrix | None:
    if raw is None:
        return None

    # Shorthand: a single format name applied to every reply.
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            raise ValueError(f"Operation '{operation_name}' reply_format string cannot be empty")
        return ReplyFormatMatrix(default=name, rules=())

    # The matrix form may be a mapping or a list of mappings (which are merged).
    if isinstance(raw, list):
        merged: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(
                    f"Operation '{operation_name}' reply_format list entries must be mappings"
                )
            merged.update(item)
        mapping = merged
    elif isinstance(raw, dict):
        mapping = raw
    else:
        raise ValueError(
            f"Operation '{operation_name}' reply_format must be a string, mapping, or list of mappings"
        )

    default = "markdown"
    rules: list[ReplyFormatRule] = []
    for key, value in mapping.items():
        if key == "default":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Operation '{operation_name}' reply_format default must be a non-empty string"
                )
            default = value.strip()
            continue
        rules.append(_parse_reply_format_rule_blocks(str(key), value, operation_name))

    return ReplyFormatMatrix(default=default, rules=tuple(rules))


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

        raw_allowed_optional_params = operation_config.get("allowed_optional_params", [])
        if raw_allowed_optional_params is None:
            raw_allowed_optional_params = []
        if not isinstance(raw_allowed_optional_params, list):
            raise ValueError(
                f"Operation '{operation_name}' allowed_optional_params must be a list of strings"
            )

        normalized_allowed_optional_params: list[str] = []
        for optional_param in raw_allowed_optional_params:
            if not isinstance(optional_param, str) or not optional_param.strip():
                raise ValueError(
                    f"Operation '{operation_name}' allowed_optional_params entries must be non-empty strings"
                )
            if optional_param not in normalized_allowed_optional_params:
                normalized_allowed_optional_params.append(optional_param)

        reply_format = _parse_reply_format(
            operation_config.get("reply_format"), operation_name
        )

        result[operation_name] = HostOperationDefinition(
            command=list(command),
            timeout_seconds=timeout_seconds,
            allow_user_args=allow_user_args,
            allowed_placeholders=tuple(normalized_allowed_placeholders),
            allowed_optional_params=tuple(normalized_allowed_optional_params),
            reply_format=reply_format,
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