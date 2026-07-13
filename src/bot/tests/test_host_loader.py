from __future__ import annotations

import json
from pathlib import Path

from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.host_loader import load_actions_from_file
from bot_service.host_loader import load_actions_from_json
from bot_service.result import Result


async def test_load_actions_from_file_registers_handlers(tmp_path: Path) -> None:
    config_path = tmp_path / "actions.json"
    config_path.write_text(
        json.dumps(
            {
                "actions": {
                    "status": {
                        "stop_on_failure": True,
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
                }
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


async def test_load_actions_from_json_rolls_back_on_failure() -> None:
    engine = ActionEngine()
    seed_result = load_actions_from_json(
        engine,
        json.dumps(
            {
                "actions": {
                    "status": {
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
                }
            }
        ),
        replace_configured_actions=True,
    )
    assert Result.is_success(seed_result)

    bad_result = load_actions_from_json(
        engine,
        json.dumps(
            {
                "actions": {
                    "status": {
                        "handlers": [
                            {
                                "id": "bad.handler",
                                "module": "tests.support_handlers",
                                "callable": "does_not_exist",
                                "stage": 0,
                            }
                        ],
                    }
                }
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
