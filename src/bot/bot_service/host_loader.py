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


def _resolve_handler_callback(handler: dict[str, Any]) -> Any:
    target = str(handler.get("target", "local")).strip().lower()
    if target == "local":
        module_name = handler["module"]
        callable_name = handler["callable"]
        return _resolve_callable(module_name, callable_name)

    if target == "host":
        operation_name = handler["operation"]
        return build_host_operation_handler(operation_name)

    raise ValueError(f"Unsupported handler target: {target}")


def _load_actions_from_payload(
    engine: ActionEngine,
    payload: dict[str, Any],
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    snapshot = engine.snapshot_state()
    try:
        actions = payload.get("actions", {})
        total_registered = 0
        for action_name, action_config in actions.items():
            if replace_configured_actions:
                engine.clear_action(action_name)

            stop_on_failure = action_config.get("stop_on_failure", True)
            default_timeout_seconds = action_config.get("default_timeout_seconds")
            engine.register_action(
                action_name,
                policy=ActionPolicy(
                    stop_on_failure=stop_on_failure,
                    default_timeout_seconds=default_timeout_seconds,
                ),
            )

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
