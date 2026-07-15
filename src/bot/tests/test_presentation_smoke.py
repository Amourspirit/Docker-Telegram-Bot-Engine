from __future__ import annotations

from bot_service.presentation import build_action_info_text
from bot_service.presentation import build_help_text


def test_help_text_contains_actions_and_admin_commands() -> None:
    text = build_help_text(
        action_names=["status", "logs", "restart"],
        action_handler_counts={"status": 3, "logs": 1, "restart": 1},
        action_tags={"status": ("docker", "util")},
    )

    assert "🤖 Available Commands" in text
    assert "/status - 3 handler(s)" in text
    assert "tags: docker, util" in text
    assert "/logs - 1 handler(s)" in text
    assert "/restart - 1 handler(s)" in text
    assert "/reload_actions - Reload host action config" in text
    assert "/action_info <action> - Show policy and handler stages" in text
    assert "/actions_by_tag <tag> [<tag> ...] - Show actions matching any tag" in text


def test_action_info_text_contains_policy_and_stage_details() -> None:
    details = {
        "policy": {
            "stop_on_failure": True,
            "default_timeout_seconds": 5,
            "tags": ["docker", "util"],
        },
        "stages": [
            [
                {
                    "handler_id": "docker.status.collect",
                    "stop_on_failure": None,
                    "timeout_seconds": None,
                }
            ],
            [
                {
                    "handler_id": "docker.status.render",
                    "stop_on_failure": None,
                    "timeout_seconds": 5,
                }
            ],
        ],
    }

    text = build_action_info_text("status", details)

    assert "Action: /status" in text
    assert "Tags: docker, util" in text
    assert "stop_on_failure: True" in text
    assert "default_timeout_seconds: 5" in text
    assert "stage 0:" in text
    assert "docker.status.collect" in text
    assert "stage 1:" in text
    assert "docker.status.render" in text


def test_help_text_supports_tag_filtered_heading() -> None:
    text = build_help_text(
        action_names=["status"],
        action_handler_counts={"status": 2},
        action_tags={"status": ("docker",)},
        heading="🏷️ Actions By Tag",
        summary_line="Showing actions matching any tag: docker",
        include_admin_commands=False,
    )

    assert "🏷️ Actions By Tag" in text
    assert "Showing actions matching any tag: docker" in text
    assert "/status - 2 handler(s) (tags: docker)" in text
    assert "/reload_actions" not in text
