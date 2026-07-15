from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot_service.engine import ActionPolicy
from bot_service.host_client import build_host_operation_handler
from bot_service.result import Result


def _load_bot_module(monkeypatch):
    monkeypatch.delenv("BOT_ACTIONS_CONFIG", raising=False)
    monkeypatch.delenv("BOT_HOST_ACTION_SOCKET", raising=False)
    monkeypatch.setattr("docker.from_env", lambda: object())

    import bot_service.bot as bot_module

    bot = importlib.reload(bot_module)
    bot.action_engine.set_user_roles({1: ("admin",)})
    return bot


async def test_help_command_replies_with_markdown(monkeypatch) -> None:
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
    assert kwargs.get("parse_mode") == "Markdown"


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
        async def invoke(self, operation_name, event_args, params=None):
            return Result.success(
                f"host:{operation_name}:{event_args.correlation_id}:{','.join(event_args.raw_args)}"
            )

    bot.host_action_client = FakeHostActionClient()
    bot.action_engine.register_action("server_uptime", policy=ActionPolicy(allowed_roles=("operator",)))
    bot.action_engine.register_handler(
        "server_uptime",
        "host.server.uptime",
        build_host_operation_handler("server.uptime"),
    )

    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=SimpleNamespace(text="/server_uptime now", reply_text=reply_text),
    )
    context = SimpleNamespace(args=[])

    await bot.dispatch_action_command(update, context)

    reply_text.assert_awaited_once()
    args, kwargs = reply_text.await_args
    assert args[0].startswith("host:server.uptime:")
    assert args[0].endswith(":now")
    assert kwargs.get("parse_mode") == "Markdown"


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
    assert kwargs.get("parse_mode") == "Markdown"


def test_reload_rejects_reserved_action_names(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text("actions: {}", encoding="utf-8")

    monkeypatch.setenv("BOT_ACTIONS_CONFIG", str(config_path))
    monkeypatch.delenv("BOT_HOST_ACTION_SOCKET", raising=False)
    monkeypatch.setattr("docker.from_env", lambda: object())

    import bot_service.bot as bot_module

    bot = importlib.reload(bot_module)
    bot.action_engine.set_user_roles({1: ("admin",)})
    result = bot._load_host_actions_config_from_text(
        "actions:\n"
        "  help:\n"
        "    handlers:\n"
        "      - id: host.help.blocked\n"
        "        target: host\n"
        "        operation: helper.blocked\n",
        update_last_known_good=False,
    )

    assert Result.is_failure(result)
    assert "reserved command names" in str(result.error)


def test_reload_rejects_reserved_alias_names(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "actions.yaml"
    config_path.write_text("actions: {}", encoding="utf-8")

    monkeypatch.setenv("BOT_ACTIONS_CONFIG", str(config_path))
    monkeypatch.delenv("BOT_HOST_ACTION_SOCKET", raising=False)
    monkeypatch.setattr("docker.from_env", lambda: object())

    import bot_service.bot as bot_module

    bot = importlib.reload(bot_module)
    bot.action_engine.set_user_roles({1: ("admin",)})
    result = bot._load_host_actions_config_from_text(
        "actions:\n"
        "  cf_docker_url:\n"
        "    aliases:\n"
        "      - help\n"
        "    handlers:\n"
        "      - id: host.help.blocked\n"
        "        target: host\n"
        "        operation: helper.blocked\n",
        update_last_known_good=False,
    )

    assert Result.is_failure(result)
    assert "reserved command names" in str(result.error)
