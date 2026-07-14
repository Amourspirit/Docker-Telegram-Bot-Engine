from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _load_bot_module(monkeypatch):
    monkeypatch.setenv("ALLOWED_TELEGRAM_IDS", "1")
    monkeypatch.delenv("BOT_ACTIONS_CONFIG", raising=False)
    monkeypatch.setattr("docker.from_env", lambda: object())

    import bot_service.bot as bot_module

    return importlib.reload(bot_module)


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
