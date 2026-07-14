# bot.py
import logging
import os
import uuid
from pathlib import Path

import docker
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from bot_service.actions import register_default_actions
from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.host_client import HostActionClient
from bot_service.host_loader import load_actions_from_text
from bot_service.presentation import build_action_info_text
from bot_service.presentation import build_help_text
from bot_service.result import Result

# Configure logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
HOST_ACTION_SOCKET = os.environ.get("BOT_HOST_ACTION_SOCKET")
HOST_ACTION_ENDPOINT = os.environ.get("BOT_HOST_ACTION_ENDPOINT")
RESERVED_COMMAND_NAMES = {"reload_actions", "action_info", "help"}


def _parse_allowed_ids(raw_ids: str) -> list[int]:
    ids: list[int] = []
    for raw_id in raw_ids.split(","):
        clean = raw_id.strip()
        if not clean:
            continue
        ids.append(int(clean))
    return ids


# Comma-separated list of your personal Telegram User IDs (NOT usernames)
ALLOWED_IDS = _parse_allowed_ids(os.environ.get("ALLOWED_TELEGRAM_IDS", ""))

# Initialize Docker client (connects via the mounted socket)
docker_client = docker.from_env()
host_action_client = HostActionClient(HOST_ACTION_SOCKET, endpoint=HOST_ACTION_ENDPOINT)

# Initialize action engine and register built-in handlers.
action_engine = ActionEngine()
register_default_actions(action_engine)

HOST_ACTIONS_CONFIG = os.environ.get("BOT_ACTIONS_CONFIG")
LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT: str | None = None


def _read_host_actions_config_text() -> Result[str, BaseException]:
    if not HOST_ACTIONS_CONFIG:
        return Result.failure(ValueError("BOT_ACTIONS_CONFIG is not set"))

    path = Path(HOST_ACTIONS_CONFIG)
    if not path.exists():
        return Result.failure(FileNotFoundError(f"Action config file not found: {HOST_ACTIONS_CONFIG}"))

    try:
        return Result.success(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


def _load_host_actions_config_from_text(
    config_text: str,
    update_last_known_good: bool,
) -> Result[int, BaseException]:
    global LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT

    if not HOST_ACTIONS_CONFIG:
        return Result.failure(ValueError("BOT_ACTIONS_CONFIG is not set"))

    extension = Path(HOST_ACTIONS_CONFIG).suffix.lower()
    if extension == ".json":
        config_format = "json"
    elif extension in {".yaml", ".yml"}:
        config_format = "yaml"
    else:
        return Result.failure(
            ValueError("Unsupported BOT_ACTIONS_CONFIG extension. Use .json, .yaml, or .yml")
        )

    snapshot = action_engine.snapshot_state()
    result = load_actions_from_text(
        action_engine,
        config_text,
        config_format=config_format,
        replace_configured_actions=True,
    )

    if Result.is_success(result):
        reserved_conflicts = sorted(
            action_name
            for action_name in RESERVED_COMMAND_NAMES
            if action_engine.describe_action(action_name) is not None
        )
        if reserved_conflicts:
            action_engine.restore_state(snapshot)
            return Result.failure(
                ValueError(
                    "Configured actions cannot use reserved command names: "
                    + ", ".join(reserved_conflicts)
                )
            )

    if Result.is_success(result) and update_last_known_good:
        LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT = config_text

    return result


def _load_host_actions_config() -> Result[int, BaseException]:
    if not HOST_ACTIONS_CONFIG:
        return Result.success(0)

    text_result = _read_host_actions_config_text()
    if Result.is_failure(text_result):
        return Result.failure(text_result.error)

    return _load_host_actions_config_from_text(
        text_result.data,
        update_last_known_good=True,
    )


def _reload_host_actions_with_rollback() -> tuple[Result[int, BaseException], bool]:
    load_result = _load_host_actions_config()
    if Result.is_success(load_result):
        return load_result, False

    if LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT:
        restore_result = _load_host_actions_config_from_text(
            LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT,
            update_last_known_good=False,
        )
        if Result.is_success(restore_result):
            return restore_result, True

    return Result.failure(load_result.error), False


def is_authorized(update: Update) -> bool:
    """Security check to silently ignore unauthorized users."""
    user = update.effective_user
    if user is None:
        return False

    result = user.id in ALLOWED_IDS
    if not result:
        logging.warning(f"Unauthorized access attempt by user ID: {user.id}")
    return result


async def _dispatch_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action_name: str) -> None:
    if not is_authorized(update):
        return

    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    event_args = EventArgs(
        action_name=action_name,
        user_id=user.id,
        raw_args=tuple(context.args),
        correlation_id=uuid.uuid4().hex,
        shared_state={
            "docker_client": docker_client,
            "host_action_client": host_action_client,
        },
    )

    result = await action_engine.dispatch(event_args)
    if Result.is_failure(result):
        await message.reply_text(f"Error: {result.error}")
        return

    await message.reply_text(result.data, parse_mode="Markdown")


def _parse_message_command(message_text: str) -> tuple[str, tuple[str, ...]] | None:
    stripped = message_text.strip()
    if not stripped.startswith("/"):
        return None

    segments = stripped.split()
    if not segments:
        return None

    command_token = segments[0][1:]
    if not command_token:
        return None

    command_name = command_token.split("@", 1)[0]
    return command_name, tuple(segments[1:])


async def dispatch_action_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    if message is None or not message.text:
        return

    parsed = _parse_message_command(message.text)
    if parsed is None:
        return

    action_name, raw_args = parsed
    if action_name in RESERVED_COMMAND_NAMES:
        return

    if action_engine.describe_action(action_name) is None:
        await message.reply_text(f"Action '{action_name}' is not registered.")
        return

    context.args = list(raw_args)
    await _dispatch_action(update, context, action_name)


async def reload_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    if message is None:
        return

    if not HOST_ACTIONS_CONFIG:
        await message.reply_text("BOT_ACTIONS_CONFIG is not set.")
        return

    reload_result, restored = _reload_host_actions_with_rollback()
    if Result.is_success(reload_result):
        if restored:
            await message.reply_text(
                "⚠️ Reload failed. Restored last known good action configuration.",
            )
            return

        await message.reply_text(
            f"✅ Reloaded actions from `{HOST_ACTIONS_CONFIG}`. Registered handlers: `{reload_result.data}`",
            parse_mode="Markdown",
        )
        return

    await message.reply_text(f"❌ Failed to reload actions: {reload_result.error}")


async def action_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    if message is None:
        return

    if not context.args:
        await message.reply_text("Usage: /action_info <action_name>")
        return

    action_name = context.args[0].lstrip("/")
    details = action_engine.describe_action(action_name)
    if details is None:
        await message.reply_text(f"Action '{action_name}' is not registered.")
        return

    await message.reply_text(build_action_info_text(action_name, details))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    if message is None:
        return

    action_names = action_engine.list_actions()
    action_handler_counts = {
        action_name: len(action_engine.list_handlers(action_name))
        for action_name in action_names
    }
    await message.reply_text(
        build_help_text(action_names, action_handler_counts),
        parse_mode="Markdown",
    )


def main() -> None:
    if not TOKEN or not ALLOWED_IDS:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or ALLOWED_TELEGRAM_IDS")

    if HOST_ACTIONS_CONFIG:
        reload_result, restored = _reload_host_actions_with_rollback()
        if Result.is_success(reload_result):
            if restored:
                logging.warning(
                    "Startup reload failed. Restored last known good action configuration from memory."
                )
            else:
                logging.info(
                    "Reloaded actions at startup from %s. Registered handlers: %s",
                    HOST_ACTIONS_CONFIG,
                    reload_result.data,
                )
        else:
            logging.error("Failed to reload actions at startup: %s", reload_result.error)

    app = ApplicationBuilder().token(TOKEN).build()

    # Register commands
    app.add_handler(CommandHandler("reload_actions", reload_actions))
    app.add_handler(CommandHandler("action_info", action_info))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.COMMAND, dispatch_action_command))

    logging.info("Bot is polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
