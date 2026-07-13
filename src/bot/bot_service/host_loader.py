from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from bot_service.engine import ActionEngine, ActionPolicy
from bot_service.result import Result


def _resolve_callable(module_name: str, callable_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, callable_name)


def load_actions_from_file(
    engine: ActionEngine,
    config_path: str,
    replace_configured_actions: bool = False,
) -> Result[int, BaseException]:
    """Load and register actions from a host-mounted JSON config file."""
    path = Path(config_path)
    if not path.exists():
        return Result.failure(FileNotFoundError(f"Action config file not found: {config_path}"))

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    try:
        actions = payload.get("actions", {})
        total_registered = 0
        for action_name, action_config in actions.items():
            if replace_configured_actions:
                engine.clear_action(action_name)

            stop_on_failure = action_config.get("stop_on_failure", True)
            engine.register_action(action_name, policy=ActionPolicy(stop_on_failure=stop_on_failure))

            for handler in action_config.get("handlers", []):
                handler_id = handler["id"]
                module_name = handler["module"]
                callable_name = handler["callable"]
                stage = int(handler.get("stage", 0))
                handler_stop_on_failure = handler.get("stop_on_failure")

                callback = _resolve_callable(module_name, callable_name)
                engine.register_handler(
                    action_name=action_name,
                    handler_id=handler_id,
                    callback=callback,
                    stage=stage,
                    stop_on_failure=handler_stop_on_failure,
                )
                total_registered += 1

            for handler_id in action_config.get("unregister", []):
                engine.unregister_handler(action_name=action_name, handler_id=handler_id)

        return Result.success(total_registered)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)
