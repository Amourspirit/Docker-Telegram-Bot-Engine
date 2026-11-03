from __future__ import annotations

import logging

from bot_service.logging_setup import REDACTED, RedactSecretsFilter, configure_logging

TOKEN = "123456789:AAHtest-token-value_with-underscores"


def _record(message: str, *args: object, name: str = "httpx") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 1, message, args, None)


def test_filter_redacts_token_shaped_text() -> None:
    record = _record("HTTP Request: %s %s", "POST", f"https://api.telegram.org/bot{TOKEN}/getUpdates")

    assert RedactSecretsFilter().filter(record) is True

    message = record.getMessage()
    assert TOKEN not in message
    assert f"/bot{REDACTED}/getUpdates" in message


def test_filter_redacts_configured_secret_even_with_unusual_shape() -> None:
    record = _record("token=%s", "not-a-typical-token")

    RedactSecretsFilter(secrets=("not-a-typical-token",)).filter(record)

    assert record.getMessage() == f"token={REDACTED}"


def test_filter_leaves_clean_messages_untouched() -> None:
    record = _record("Bot is polling...")
    original_args = record.args

    RedactSecretsFilter(secrets=(TOKEN,)).filter(record)

    assert record.getMessage() == "Bot is polling..."
    assert record.args is original_args


def test_configure_logging_installs_filter_on_root_handlers() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers = [logging.StreamHandler()]

        configure_logging()

        assert any(
            isinstance(existing, RedactSecretsFilter)
            for existing in root.handlers[0].filters
        )
    finally:
        root.handlers = original_handlers
