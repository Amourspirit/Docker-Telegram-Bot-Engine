"""Logging configuration with secret redaction.

Telegram API URLs embed the bot token in the path
(``https://api.telegram.org/bot<token>/getUpdates``). ``httpx`` logs whole request
URLs at INFO, so without redaction the token ends up in container logs. Install a
filter on the root handlers to mask it before any record is written.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
REDACTED = "<redacted>"

# <bot_id>:<secret>, e.g. 123456789:AAH... — also matches the `/bot<token>/` URL path,
# where the digits are preceded by the literal "bot".
_TELEGRAM_TOKEN_PATTERN = re.compile(r"(?<!\d)\d{5,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")


class RedactSecretsFilter(logging.Filter):
    """Masks known secrets (and anything shaped like a bot token) in log messages."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return _TELEGRAM_TOKEN_PATTERN.sub(REDACTED, text)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.redact(message)
        if redacted != message:
            # Collapse the already-formatted message so handlers cannot re-expand
            # record.args back into the original token.
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging and make sure every root handler redacts secrets."""
    logging.basicConfig(format=LOG_FORMAT, level=level)

    redaction_filter = RedactSecretsFilter(
        secrets=(os.environ.get("TELEGRAM_BOT_TOKEN", ""),),
    )
    for handler in logging.getLogger().handlers:
        if not any(isinstance(existing, RedactSecretsFilter) for existing in handler.filters):
            handler.addFilter(redaction_filter)
