from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import BadRequest

from bot_service.engine import ActionPolicy
from bot_service.host_client import build_host_operation_handler
from bot_service.result import Result


def _load_bot_module(monkeypatch):
    sys.modules.setdefault("docker", types.ModuleType("docker"))
    if not hasattr(sys.modules["docker"], "from_env"):
        sys.modules["docker"].from_env = lambda: object()
    telegram_module = sys.modules.setdefault("telegram", types.ModuleType("telegram"))
    if not hasattr(telegram_module, "Update"):
        telegram_module.Update = object

    telegram_ext_module = sys.modules.setdefault("telegram.ext", types.ModuleType("telegram.ext"))
    if not hasattr(telegram_ext_module, "ApplicationBuilder"):
        telegram_ext_module.ApplicationBuilder = object
    if not hasattr(telegram_ext_module, "CommandHandler"):
        telegram_ext_module.CommandHandler = object
    if not hasattr(telegram_ext_module, "ContextTypes"):
        telegram_ext_module.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    if not hasattr(telegram_ext_module, "MessageHandler"):
        telegram_ext_module.MessageHandler = object
    if not hasattr(telegram_ext_module, "filters"):
        telegram_ext_module.filters = types.SimpleNamespace(COMMAND=object())
    monkeypatch.delenv("BOT_HOST_ACTION_SOCKET", raising=False)
    monkeypatch.setattr("docker.from_env", lambda: object())

    import bot_service.bot as bot_module

    bot = importlib.reload(bot_module)
    bot.action_engine.set_user_roles({1: ("admin",)})
    return bot


async def test_help_command_replies_without_parse_mode(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.help_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "Available Commands" in args[0]
    assert kwargs == {}


async def test_action_info_replies_without_parse_mode(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["status"])

    await bot.action_info(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "Action: /status" in args[0]
    assert kwargs == {}


async def test_help_command_ignores_unauthorized_user(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.help_command(update, context)

    reply_text.assert_not_awaited()


async def test_action_info_ignores_unauthorized_user(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["status"])

    await bot.action_info(update, context)

    reply_text.assert_not_awaited()


async def test_dynamic_action_command_dispatches_registered_action(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    async def handler(_event_args):
        return Result.success("dynamic-ok")

    bot.action_engine.register_action("server_uptime", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_handler("server_uptime", "test.dynamic", handler)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/server_uptime now", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0] == "dynamic-ok"
    assert kwargs.get("parse_mode") == "Markdown"


async def test_dynamic_action_command_dispatches_registered_alias(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    async def handler(_event_args):
        return Result.success("dynamic-alias-ok")

    bot.action_engine.register_action("cf_docker_url", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_aliases("cf_docker_url", ["cf_url_docker"])
    bot.action_engine.register_handler("cf_docker_url", "test.dynamic.alias", handler)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/cf_url_docker now", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0] == "dynamic-alias-ok"
    assert kwargs.get("parse_mode") == "Markdown"


async def test_dynamic_action_command_uses_host_action_client(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    class FakeHostActionClient:
        async def invoke(self, operation_name, event_args, params=None, timeout_seconds=None):
            return Result.success(
                f"host:{operation_name}:{event_args.correlation_id}:{','.join(event_args.raw_args)}"
            )

    bot.host_action_client = FakeHostActionClient()
    bot.action_engine.register_action("lms_ps", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_handler(
        "lms_ps",
        "host.server.lms_action",
        build_host_operation_handler("server.lms_action"),
    )

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/lms_ps --json", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0].startswith("host:server.lms_action:")
    assert args[0].endswith(":--json")
    assert kwargs.get("parse_mode") == "Markdown"


async def test_dynamic_action_command_falls_back_to_plain_text_on_markdown_parse_error(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    class FakeHostActionClient:
        async def invoke(self, operation_name, event_args, params=None, timeout_seconds=None):
            return Result.success(
                f'{{"operation":"{operation_name}","args":["{event_args.raw_args[0]}"]}}'
            )

    bot.host_action_client = FakeHostActionClient()
    bot.action_engine.register_action("lms_ps", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_handler(
        "lms_ps",
        "host.server.lms_action",
        build_host_operation_handler("server.lms_action"),
    )

    reply_text = AsyncMock(
        side_effect=[BadRequest("Can't parse entities: can't find end of the entity"), None]
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/lms_ps --json", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    assert reply_text.await_count == 2
    first_args, first_kwargs = reply_text.await_args_list[0]
    second_args, second_kwargs = reply_text.await_args_list[1]
    assert first_args[0] == '{"operation":"server.lms_action","args":["--json"]}'
    assert first_kwargs.get("parse_mode") == "Markdown"
    assert second_args[0] == first_args[0]
    assert second_kwargs == {}


async def test_dynamic_action_command_rejects_too_many_user_args(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    async def handler(_event_args):
        return Result.success("should-not-run")

    bot.action_engine.register_action("server_uptime", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_handler("server_uptime", "test.dynamic.limit", handler)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(
            text="/server_uptime a b c d e f g h i j k",
            reply_text=reply_text,
        ),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0] == "❌ Invalid arguments."
    assert kwargs == {}


async def test_dynamic_action_command_ignores_reserved_commands(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/help", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_not_awaited()


async def test_dynamic_action_command_ignores_actions_by_tag_reserved_command(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/actions_by_tag docker", reply_text=reply_text),
    )
    context = SimpleNamespace(args=["docker"])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_not_awaited()


async def test_reload_actions_requires_admin_role(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.set_user_roles({1: ("operator",)})

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.reload_actions(update, context)

    reply_text.assert_awaited_once()
    args, _kwargs = reply_text.await_args
    assert "not allowed" in args[0]


async def test_action_info_accepts_alias(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.register_action("cf_docker_url", policy=ActionPolicy(allowed_roles=("admin",)))
    bot.action_engine.register_aliases("cf_docker_url", ["cf_url_docker"])

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["cf_url_docker"])

    await bot.action_info(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "Action: /cf_docker_url" in args[0]
    assert "Aliases: /cf_url_docker" in args[0]
    assert kwargs == {}


async def test_help_command_shows_aliases(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.register_action("cf_docker_url", policy=ActionPolicy(allowed_roles=("admin",)))
    bot.action_engine.register_aliases("cf_docker_url", ["cf_url_docker"])

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.help_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "/cf_docker_url - 0 handler(s) (aliases: /cf_url_docker)" in args[0]
    assert kwargs == {}


async def test_help_command_shows_tags(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.register_action(
        "status",
        policy=ActionPolicy(allowed_roles=("admin",), tags=("docker", "util")),
    )

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.help_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "tags: docker, util" in args[0]
    assert kwargs == {}


async def test_actions_by_tag_lists_matching_actions(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.register_action(
        "status",
        policy=ActionPolicy(allowed_roles=("admin",), tags=("docker", "util")),
    )
    bot.action_engine.register_action(
        "cf_docker_url",
        policy=ActionPolicy(allowed_roles=("admin",), tags=("cloudflare", "route")),
    )

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["route", "docker"])

    await bot.actions_by_tag(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "🏷️ Actions By Tag" in args[0]
    assert "Showing actions matching any tag: route, docker" in args[0]
    assert "/status - 3 handler(s) (tags: docker, util)" in args[0]
    assert "/cf_docker_url - 0 handler(s) (tags: cloudflare, route)" in args[0]
    assert kwargs == {}


async def test_actions_by_tag_supports_reserved_untagged_filters(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)
    bot.action_engine.register_action("server_uptime", policy=ActionPolicy(allowed_roles=("admin",)))
    bot.action_engine.register_action(
        "status",
        policy=ActionPolicy(allowed_roles=("admin",), tags=("docker",)),
    )

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=["unknown", "docker"])

    await bot.actions_by_tag(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert "Showing untagged actions" in args[0]
    assert "/server_uptime - 0 handler(s)" in args[0]
    assert "/status" not in args[0]
    assert kwargs == {}


async def test_actions_by_tag_requires_arguments(monkeypatch) -> None:
    bot = _load_bot_module(monkeypatch)

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.actions_by_tag(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0] == "Usage: /actions_by_tag <tag> [<tag> ...]"
    assert kwargs == {}


def test_reload_rejects_reserved_action_names(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text("actions: {}", encoding="utf-8")

    bot = _load_bot_module(monkeypatch)
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (config_path,))
    bot.action_engine.set_user_roles({1: ("admin",)})
    result = bot._load_actions_config_from_text(
        "actions:\n"
        "  help:\n"
        "    handlers:\n"
        "      - id: host.help.blocked\n"
        "        target: host\n"
        "        operation: helper.blocked\n",
        config_path,
        update_last_known_good=False,
    )

    assert Result.is_failure(result)
    assert "reserved command names" in str(result.error)


def test_reload_rejects_reserved_alias_names(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text("actions: {}", encoding="utf-8")

    bot = _load_bot_module(monkeypatch)
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (config_path,))
    bot.action_engine.set_user_roles({1: ("admin",)})
    result = bot._load_actions_config_from_text(
        "actions:\n"
        "  cf_docker_url:\n"
        "    aliases:\n"
        "      - help\n"
        "    handlers:\n"
        "      - id: host.help.blocked\n"
        "        target: host\n"
        "        operation: helper.blocked\n",
        config_path,
        update_last_known_good=False,
    )

    assert Result.is_failure(result)
    assert "reserved command names" in str(result.error)


def test_reload_rejects_actions_by_tag_reserved_action_name(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text("actions: {}", encoding="utf-8")

    bot = _load_bot_module(monkeypatch)
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (config_path,))
    bot.action_engine.set_user_roles({1: ("admin",)})
    result = bot._load_actions_config_from_text(
        "actions:\n"
        "  actions_by_tag:\n"
        "    handlers:\n"
        "      - id: host.actions_by_tag.blocked\n"
        "        target: host\n"
        "        operation: helper.blocked\n",
        config_path,
        update_last_known_good=False,
    )

    assert Result.is_failure(result)
    assert "reserved command names" in str(result.error)


def test_reload_fails_when_no_required_actions_file_exists(monkeypatch, tmp_path: Path) -> None:
    bot = _load_bot_module(monkeypatch)
    missing_yaml = tmp_path / "missing-actions.yaml"
    missing_yml = tmp_path / "missing-actions.yml"
    missing_json = tmp_path / "missing-actions.json"
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (missing_yaml, missing_yml, missing_json))

    result = bot._read_actions_config_text()

    assert Result.is_failure(result)
    assert "Action config file not found" in str(result.error)


def test_reload_prefers_yaml_then_yml_then_json(monkeypatch, tmp_path: Path) -> None:
    yaml_path = tmp_path / "actions.yaml"
    yml_path = tmp_path / "actions.yml"
    json_path = tmp_path / "actions.json"
    yml_path.write_text("actions: {}", encoding="utf-8")
    json_path.write_text('{"actions": {}}', encoding="utf-8")

    bot = _load_bot_module(monkeypatch)
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (yaml_path, yml_path, json_path))

    path_result = bot._resolve_actions_config_path()
    assert Result.is_success(path_result)
    assert path_result.data == yml_path

    yaml_path.write_text("actions: {}", encoding="utf-8")
    path_result = bot._resolve_actions_config_path()
    assert Result.is_success(path_result)
    assert path_result.data == yaml_path


def test_reload_fails_when_no_required_users_file_exists(monkeypatch, tmp_path: Path) -> None:
    bot = _load_bot_module(monkeypatch)
    missing_yaml = tmp_path / "missing-users.yaml"
    missing_yml = tmp_path / "missing-users.yml"
    missing_json = tmp_path / "missing-users.json"
    monkeypatch.setattr(bot, "USERS_CONFIG_CANDIDATES", (missing_yaml, missing_yml, missing_json))

    result = bot._read_users_config_text()

    assert Result.is_failure(result)
    assert "User config file not found" in str(result.error)


async def test_reload_actions_success_mentions_resolved_config_path(monkeypatch, tmp_path: Path) -> None:
    actions_path = tmp_path / "actions.yaml"
    users_path = tmp_path / "users.yaml"
    actions_path.write_text("actions: {}", encoding="utf-8")
    users_path.write_text('users:\n  "1":\n    roles:\n      - admin\n', encoding="utf-8")

    bot = _load_bot_module(monkeypatch)
    monkeypatch.setattr(bot, "ACTIONS_CONFIG_CANDIDATES", (actions_path,))
    monkeypatch.setattr(bot, "USERS_CONFIG_CANDIDATES", (users_path,))

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.reload_actions(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert str(actions_path) in args[0]
    assert str(users_path) in args[0]
    assert "`1` users" in args[0]
    assert "Registered handlers: `0`" in args[0]
    assert kwargs.get("parse_mode") == "Markdown"
