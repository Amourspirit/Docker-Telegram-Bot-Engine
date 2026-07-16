from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import yaml

from bot_service.engine import ActionEngine, ActionPolicy
from bot_service.host_client import build_host_operation_handler
from bot_service.result import Result


def _resolve_project_root_path(config_path: str) -> Path:
    path = Path(config_path).expanduser()
    if path.is_absolute():
        return path

    project_root = Path(__file__).resolve().parents[3]
    return (project_root / path).resolve()


def _resolve_callable(module_name: str, callable_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, callable_name)


def _normalize_handler_params(handler: dict[str, Any]) -> dict[str, str] | None:
    raw_params = handler.get("params")
    if raw_params is None:
        return None

    if not isinstance(raw_params, dict):
        raise ValueError("host handler params must be a mapping of string keys to string values")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in raw_params.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("host handler params keys must be non-empty strings")
        if not isinstance(raw_value, str):
            raise ValueError("host handler params values must be strings")
        normalized[raw_key] = raw_value

    return normalized


def _resolve_handler_callback(handler: dict[str, Any]) -> Any:
    target = str(handler.get("target", "local")).strip().lower()
    if target == "local":
        module_name = handler["module"]
        callable_name = handler["callable"]
        return _resolve_callable(module_name, callable_name)

    if target == "host":
        operation_name = handler["operation"]
        operation_params = _normalize_handler_params(handler)
        return build_host_operation_handler(operation_name, params=operation_params)

    raise ValueError(f"Unsupported handler target: {target}")


def _normalize_roles(raw_roles: Any, field_name: str) -> tuple[str, ...]:
    if raw_roles is None:
        return ()

    if not isinstance(raw_roles, list):
        raise ValueError(f"{field_name} must be a list of role names")

    normalized: list[str] = []
    for role in raw_roles:
        if not isinstance(role, str):
            raise ValueError(f"{field_name} entries must be strings")
        clean = role.strip().lower()
        if not clean:
            raise ValueError(f"{field_name} cannot contain empty role names")
        if clean not in normalized:
            normalized.append(clean)

    return tuple(normalized)


def _normalize_aliases(raw_aliases: Any, field_name: str) -> tuple[str, ...]:
    if raw_aliases is None:
        return ()

    if not isinstance(raw_aliases, list):
        raise ValueError(f"{field_name} must be a list of alias names")

    normalized: list[str] = []
    for alias in raw_aliases:
        if not isinstance(alias, str):
            raise ValueError(f"{field_name} entries must be strings")

        clean = alias.strip()
        if not clean:
            raise ValueError(f"{field_name} cannot contain empty alias names")
        normalized.append(clean)

    return tuple(normalized)


def _normalize_tags(raw_tags: Any, field_name: str) -> tuple[str, ...]:
    if raw_tags is None:
        return ()

    if not isinstance(raw_tags, list):
        raise ValueError(f"{field_name} must be a list of tag names")

    normalized: list[str] = []
    for tag in raw_tags:
        if not isinstance(tag, str):
            raise ValueError(f"{field_name} entries must be strings")

        clean = tag.strip().lower()
        if not clean:
            raise ValueError(f"{field_name} cannot contain empty tag names")
        if clean not in normalized:
            normalized.append(clean)

    return tuple(normalized)


def _parse_users(raw_users: Any) -> dict[int, tuple[str, ...]]:
    if raw_users is None:
        return {}

    if not isinstance(raw_users, dict):
        raise ValueError("users must be a mapping of Telegram user ID to user configuration")

    parsed: dict[int, tuple[str, ...]] = {}
    for raw_user_id, raw_user_config in raw_users.items():
        try:
            user_id = int(str(raw_user_id).strip())
        except ValueError as exc:
            raise ValueError(f"Invalid Telegram user ID in users: {raw_user_id}") from exc

        if isinstance(raw_user_config, dict):
            parsed[user_id] = _normalize_roles(raw_user_config.get("roles"), f"users[{raw_user_id!r}].roles")
            continue

        # Backward compatibility for older config shape: user_roles: {"123": ["admin"]}
        if isinstance(raw_user_config, list):
            parsed[user_id] = _normalize_roles(raw_user_config, f"users[{raw_user_id!r}]")
            continue

        raise ValueError(
            f"users[{raw_user_id!r}] must be a mapping with a 'roles' list"
        )

    return parsed


def _extract_users_payload(payload: dict[str, Any]) -> Result[Any, BaseException]:
    if "users" in payload:
        return Result.success(payload.get("users"))
    if "user_roles" in payload:
        return Result.success(payload.get("user_roles"))

    return Result.failure(ValueError("User config must include a 'users' key"))


def _load_users_from_payload(
    engine: ActionEngine,
    payload: dict[str, Any],
    replace_configured_users: bool = False,
) -> Result[int, BaseException]:
    snapshot = engine.snapshot_state()
    try:
        users_result = _extract_users_payload(payload)
        if Result.is_failure(users_result):
            if replace_configured_users:
                engine.set_user_roles({})
                return Result.success(0)

            return Result.failure(users_result.error)

        parsed_users = _parse_users(users_result.data)
        engine.set_user_roles(parsed_users)
        return Result.success(len(parsed_users))
    except Exception as exc:  # noqa: BLE001
        engine.restore_state(snapshot)
        return Result.failure(exc)


def _load_actions_from_payload(
    engine: ActionEngine,
    payload: dict[str, Any],
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    snapshot = engine.snapshot_state()
    try:
        if "users" in payload or "user_roles" in payload:
            return Result.failure(
                ValueError("Action config cannot include users. Move users to users.yaml, users.yml, or users.json")
            )

        actions = payload.get("actions", {})
        total_registered = 0
        for action_name, action_config in actions.items():
            if replace_configured_actions:
                engine.clear_action(action_name)

            stop_on_failure = action_config.get("stop_on_failure", True)
            default_timeout_seconds = action_config.get("default_timeout_seconds")
            allowed_roles = _normalize_roles(
                action_config.get("allowed_roles"),
                f"actions[{action_name!r}].allowed_roles",
            )
            aliases = _normalize_aliases(
                action_config.get("aliases"),
                f"actions[{action_name!r}].aliases",
            )
            tags = _normalize_tags(
                action_config.get("tags"),
                f"actions[{action_name!r}].tags",
            )
            engine.register_action(
                action_name,
                policy=ActionPolicy(
                    stop_on_failure=stop_on_failure,
                    default_timeout_seconds=default_timeout_seconds,
                    allowed_roles=allowed_roles,
                    tags=tags,
                ),
            )
            engine.register_aliases(action_name, aliases)

            for handler in action_config.get("handlers", []):
                handler_id = handler["id"]
                stage = int(handler.get("stage", 0))
                handler_stop_on_failure = handler.get("stop_on_failure")
                timeout_seconds = handler.get("timeout_seconds")

                callback = _resolve_handler_callback(handler)
                engine.register_handler(
                    action_name=action_name,
                    handler_id=handler_id,
                    callback=callback,
                    stage=stage,
                    stop_on_failure=handler_stop_on_failure,
                    timeout_seconds=timeout_seconds,
                )
                total_registered += 1

            for handler_id in action_config.get("unregister", []):
                engine.unregister_handler(action_name=action_name, handler_id=handler_id)

        return Result.success(total_registered)
    except Exception as exc:  # noqa: BLE001
        engine.restore_state(snapshot)
        return Result.failure(exc)


def load_actions_from_json(
    engine: ActionEngine,
    config_json: str,
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    try:
        payload = json.loads(config_json)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    return _load_actions_from_payload(
        engine,
        payload,
        replace_configured_actions=replace_configured_actions,
    )


def load_users_from_json(
    engine: ActionEngine,
    config_json: str,
    replace_configured_users: bool = False,
) -> Result[int, BaseException]:
    try:
        payload = json.loads(config_json)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return Result.failure(ValueError("User config must be a mapping with a 'users' key"))

    return _load_users_from_payload(
        engine,
        payload,
        replace_configured_users=replace_configured_users,
    )


def load_actions_from_yaml(
    engine: ActionEngine,
    config_yaml: str,
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    try:
        payload = yaml.safe_load(config_yaml)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return Result.failure(ValueError("Action config must be a mapping with an 'actions' key"))

    return _load_actions_from_payload(
        engine,
        payload,
        replace_configured_actions=replace_configured_actions,
    )


def load_users_from_yaml(
    engine: ActionEngine,
    config_yaml: str,
    replace_configured_users: bool = False,
) -> Result[int, BaseException]:
    try:
        payload = yaml.safe_load(config_yaml)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return Result.failure(ValueError("User config must be a mapping with a 'users' key"))

    return _load_users_from_payload(
        engine,
        payload,
        replace_configured_users=replace_configured_users,
    )


def load_actions_from_text(
    engine: ActionEngine,
    config_text: str,
    config_format: str,
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    normalized = config_format.strip().lower()
    if normalized == "json":
        return load_actions_from_json(
            engine,
            config_text,
            replace_configured_actions=replace_configured_actions,
        )
    if normalized in {"yaml", "yml"}:
        return load_actions_from_yaml(
            engine,
            config_text,
            replace_configured_actions=replace_configured_actions,
        )

    return Result.failure(ValueError(f"Unsupported action config format: {config_format}"))


def load_users_from_text(
    engine: ActionEngine,
    config_text: str,
    config_format: str,
    replace_configured_users: bool = False,
) -> Result[int, BaseException]:
    normalized = config_format.strip().lower()
    if normalized == "json":
        return load_users_from_json(
            engine,
            config_text,
            replace_configured_users=replace_configured_users,
        )
    if normalized in {"yaml", "yml"}:
        return load_users_from_yaml(
            engine,
            config_text,
            replace_configured_users=replace_configured_users,
        )

    return Result.failure(ValueError(f"Unsupported user config format: {config_format}"))


def load_actions_from_file(
    engine: ActionEngine,
    config_path: str,
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    """Load and register actions from a host-mounted JSON or YAML config file."""
    path = _resolve_project_root_path(config_path)
    if not path.exists():
        return Result.failure(FileNotFoundError(f"Action config file not found: {config_path}"))

    try:
        config_json = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    extension = path.suffix.lower()
    if extension == ".json":
        config_format = "json"
    elif extension in {".yaml", ".yml"}:
        config_format = "yaml"
    else:
        return Result.failure(
            ValueError(
                "Unsupported action config file extension. Use .json, .yaml, or .yml"
            )
        )

    return load_actions_from_text(
        engine,
        config_json,
        config_format=config_format,
        replace_configured_actions=replace_configured_actions,
    )


def load_users_from_file(
    engine: ActionEngine,
    config_path: str,
    replace_configured_users: bool = False,
) -> Result[int, BaseException]:
    """Load and register users from a host-mounted JSON or YAML config file."""
    path = _resolve_project_root_path(config_path)
    if not path.exists():
        return Result.failure(FileNotFoundError(f"User config file not found: {config_path}"))

    try:
        config_json = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    extension = path.suffix.lower()
    if extension == ".json":
        config_format = "json"
    elif extension in {".yaml", ".yml"}:
        config_format = "yaml"
    else:
        return Result.failure(
            ValueError(
                "Unsupported user config file extension. Use .json, .yaml, or .yml"
            )
        )

    return load_users_from_text(
        engine,
        config_json,
        config_format=config_format,
        replace_configured_users=replace_configured_users,
    )
