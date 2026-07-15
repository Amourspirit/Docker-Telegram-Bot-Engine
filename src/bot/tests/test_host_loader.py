from __future__ import annotations

import json
from pathlib import Path

import bot_service.host_loader as host_loader_module
from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.host_loader import load_actions_from_file
from bot_service.host_loader import load_actions_from_json
from bot_service.host_loader import load_actions_from_yaml
from bot_service.result import Result


async def test_load_actions_from_file_registers_handlers(tmp_path: Path) -> None:
    config_path = tmp_path / "actions.json"
    config_path.write_text(
        json.dumps(
            {
                "user_roles": {
                    "1": ["operator"],
                },
                "actions": {
                    "status": {
                        "stop_on_failure": True,
                        "allowed_roles": ["operator"],
                        "handlers": [
                            {
                                "id": "external.collect",
                                "module": "tests.support_handlers",
                                "callable": "external_status_collect",
                                "stage": 0,
                            },
                            {
                                "id": "external.render",
                                "module": "tests.support_handlers",
                                "callable": "external_status_render",
                                "stage": 1,
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    engine = ActionEngine()
    load_result = load_actions_from_file(engine, str(config_path), replace_configured_actions=True)
    assert Result.is_success(load_result)
    assert load_result.data == 2

    dispatch_result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-loader-1",
        )
    )
    assert Result.is_success(dispatch_result)
    assert dispatch_result.data == "external=ok"


def test_load_actions_from_file_missing_file() -> None:
    engine = ActionEngine()
    result = load_actions_from_file(engine, "/tmp/non-existent-actions-config.json")
    assert Result.is_failure(result)


async def test_load_actions_from_file_resolves_relative_project_root_path(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "telegram-bot"
    config_dir = project_root / "storage" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "actions.yaml"
    config_path.write_text(
        """
user_roles:
  "1":
    - operator
actions:
  status:
    allowed_roles:
      - operator
    handlers:
      - id: external.collect
        module: tests.support_handlers
        callable: external_status_collect
        stage: 0
""".strip(),
        encoding="utf-8",
    )

    fake_module_path = project_root / "src" / "bot" / "bot_service" / "host_loader.py"
    monkeypatch.setattr(host_loader_module, "__file__", str(fake_module_path))

    engine = ActionEngine()
    result = load_actions_from_file(engine, "./storage/config/actions.yaml", replace_configured_actions=True)
    assert Result.is_success(result)
    assert result.data == 1


async def test_load_actions_from_yaml_file_registers_handlers(tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text(
        """
user_roles:
  "1":
    - operator
actions:
  status:
    stop_on_failure: true
    allowed_roles:
      - operator
    handlers:
      - id: external.collect
        module: tests.support_handlers
        callable: external_status_collect
        stage: 0
      - id: external.render
        module: tests.support_handlers
        callable: external_status_render
        stage: 1
""".strip(),
        encoding="utf-8",
    )

    engine = ActionEngine()
    load_result = load_actions_from_file(engine, str(config_path), replace_configured_actions=True)
    assert Result.is_success(load_result)
    assert load_result.data == 2

    dispatch_result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-loader-yaml-1",
        )
    )
    assert Result.is_success(dispatch_result)
    assert dispatch_result.data == "external=ok"


async def test_load_actions_from_yaml_registers_host_handlers() -> None:
    class FakeHostActionClient:
        async def invoke(self, operation_name: str, event_args: EventArgs):
            return Result.success(
                f"host:{operation_name}:{event_args.user_id}:{','.join(event_args.raw_args)}"
            )

    engine = ActionEngine()
    load_result = load_actions_from_yaml(
        engine,
        """
user_roles:
  "1":
    - operator
actions:
  server_uptime:
    stop_on_failure: true
    allowed_roles:
      - operator
    handlers:
      - id: host.server.uptime
        target: host
        operation: server.uptime
        stage: 0
""".strip(),
        replace_configured_actions=True,
    )
    assert Result.is_success(load_result)
    assert load_result.data == 1

    dispatch_result = await engine.dispatch(
        EventArgs(
            action_name="server_uptime",
            user_id=1,
            raw_args=("now",),
            correlation_id="cid-loader-host-1",
            shared_state={"host_action_client": FakeHostActionClient()},
        )
    )
    assert Result.is_success(dispatch_result)
    assert dispatch_result.data == "host:server.uptime:1:now"


def test_load_actions_from_file_unsupported_extension(tmp_path: Path) -> None:
    config_path = tmp_path / "actions.txt"
    config_path.write_text("actions: {}", encoding="utf-8")

    engine = ActionEngine()
    result = load_actions_from_file(engine, str(config_path), replace_configured_actions=True)
    assert Result.is_failure(result)


async def test_load_actions_from_json_rolls_back_on_failure() -> None:
    engine = ActionEngine()
    seed_result = load_actions_from_json(
        engine,
        json.dumps(
            {
                "user_roles": {
                    "1": ["operator"],
                },
                "actions": {
                    "status": {
                        "allowed_roles": ["operator"],
                        "handlers": [
                            {
                                "id": "external.collect",
                                "module": "tests.support_handlers",
                                "callable": "external_status_collect",
                                "stage": 0,
                            },
                            {
                                "id": "external.render",
                                "module": "tests.support_handlers",
                                "callable": "external_status_render",
                                "stage": 1,
                            },
                        ],
                    }
                },
            }
        ),
        replace_configured_actions=True,
    )
    assert Result.is_success(seed_result)

    bad_result = load_actions_from_json(
        engine,
        json.dumps(
            {
                "user_roles": {
                    "1": ["operator"],
                },
                "actions": {
                    "status": {
                        "allowed_roles": ["operator"],
                        "handlers": [
                            {
                                "id": "bad.handler",
                                "module": "tests.support_handlers",
                                "callable": "does_not_exist",
                                "stage": 0,
                            }
                        ],
                    }
                },
            }
        ),
        replace_configured_actions=True,
    )
    assert Result.is_failure(bad_result)

    dispatch_result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-loader-rollback-1",
        )
    )
    assert Result.is_success(dispatch_result)
    assert dispatch_result.data == "external=ok"


def test_load_actions_from_yaml_rejects_malformed_user_roles() -> None:
    engine = ActionEngine()
    result = load_actions_from_yaml(
        engine,
        """
user_roles:
  abc:
    - admin
actions:
  status:
    allowed_roles: [admin]
    handlers: []
""".strip(),
        replace_configured_actions=True,
    )

    assert Result.is_failure(result)
    assert "Invalid Telegram user ID" in str(result.error)
