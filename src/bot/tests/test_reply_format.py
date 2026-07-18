from __future__ import annotations

import pytest

from bot_service.engine import ActionEngine, ActionPolicy
from bot_service.event_args import EventArgs
from bot_service.host_loader import load_actions_from_yaml
from bot_service.reply_format import (
    DEFAULT_REPLY_FORMAT,
    apply_reply_format,
    get_reply_format,
    resolve_reply_format,
)
from bot_service.result import Result


def test_get_reply_format_is_case_insensitive() -> None:
    assert get_reply_format("JSON").name == "json"
    assert get_reply_format(" markdown ").name == "markdown"


def test_get_reply_format_unknown_raises() -> None:
    with pytest.raises(ValueError):
        get_reply_format("toml")


def test_resolve_reply_format_none_returns_none() -> None:
    assert resolve_reply_format(None) is None


def test_resolve_reply_format_shorthand_string() -> None:
    fmt = resolve_reply_format("json")
    assert fmt is not None
    assert fmt.name == "json"
    assert fmt.fenced is True
    assert fmt.fence_lang == "json"
    assert fmt.parse_mode == "Markdown"


def test_resolve_reply_format_empty_string_raises() -> None:
    with pytest.raises(ValueError):
        resolve_reply_format("   ")


def test_resolve_reply_format_mapping_overrides_fenced() -> None:
    fmt = resolve_reply_format({"format": "json", "fenced": False})
    assert fmt is not None
    assert fmt.name == "json"
    assert fmt.fenced is False


def test_resolve_reply_format_mapping_override_fence_lang() -> None:
    fmt = resolve_reply_format({"format": "text", "fenced": True, "fence_lang": "log"})
    assert fmt is not None
    assert fmt.fenced is True
    assert fmt.fence_lang == "log"


def test_resolve_reply_format_mapping_requires_format() -> None:
    with pytest.raises(ValueError):
        resolve_reply_format({"fenced": True})


def test_resolve_reply_format_invalid_type_raises() -> None:
    with pytest.raises(ValueError):
        resolve_reply_format(123)


def test_apply_reply_format_defaults_to_markdown() -> None:
    rendered, parse_mode = apply_reply_format("hi", None)
    assert rendered == "hi"
    assert parse_mode == DEFAULT_REPLY_FORMAT.parse_mode


def test_apply_reply_format_text_is_plain() -> None:
    rendered, parse_mode = apply_reply_format("hi", get_reply_format("text"))
    assert rendered == "hi"
    assert parse_mode is None


def test_apply_reply_format_fences_json() -> None:
    rendered, parse_mode = apply_reply_format('{"a": 1}', get_reply_format("json"))
    assert rendered == '```json\n{"a": 1}\n```'
    assert parse_mode == "Markdown"


async def test_dispatch_seeds_reply_format_from_policy() -> None:
    engine = ActionEngine()
    engine.set_user_roles({1: ("operator",)})

    async def handler(event_args: EventArgs):
        return Result.success("body")

    engine.register_action(
        "show",
        policy=ActionPolicy(allowed_roles=("operator",), reply_format=get_reply_format("json")),
    )
    engine.register_handler("show", "h.body", handler, stage=0)

    event_args = EventArgs(
        action_name="show",
        user_id=1,
        raw_args=(),
        correlation_id="cid-rf-1",
    )
    result = await engine.dispatch(event_args)

    assert Result.is_success(result)
    assert event_args.reply_format is not None
    assert event_args.reply_format.name == "json"


def test_load_actions_parses_reply_format() -> None:
    engine = ActionEngine()
    config = """
actions:
  show:
    allowed_roles:
      - operator
    reply_format: json
    handlers:
      - id: external.render
        module: tests.support_handlers
        callable: external_status_render
        stage: 0
"""
    load_result = load_actions_from_yaml(engine, config, replace_configured_actions=True)
    assert Result.is_success(load_result)

    details = engine.describe_action("show")
    assert details is not None
    assert details["policy"]["reply_format"] == "json"


def test_load_actions_invalid_reply_format_fails() -> None:
    engine = ActionEngine()
    config = """
actions:
  show:
    allowed_roles:
      - operator
    reply_format: toml
    handlers:
      - id: external.render
        module: tests.support_handlers
        callable: external_status_render
        stage: 0
"""
    load_result = load_actions_from_yaml(engine, config, replace_configured_actions=True)
    assert Result.is_failure(load_result)
    assert "reply_format" in str(load_result.error)
