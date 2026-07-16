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
RESERVED_COMMAND_NAMES = {"reload_actions", "action_info", "actions_by_tag", "help"}
RESERVED_UNTAGGED_FILTERS = {"none", "unknown"}
ADMIN_ROLE = "admin"

# Initialize Docker client (connects via the mounted socket)
docker_client = docker.from_env()
host_action_client = HostActionClient(HOST_ACTION_SOCKET, endpoint=HOST_ACTION_ENDPOINT)

# Initialize action engine and register built-in handlers.
action_engine = ActionEngine()
register_default_actions(action_engine)

ACTIONS_CONFIG_CANDIDATES = (
    Path("/app/config/actions.yaml"),
    Path("/app/config/actions.yml"),
    Path("/app/config/actions.json"),
)
LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT: str | None = None
LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH: Path | None = None


def _resolve_actions_config_path() -> Result[Path, BaseException]:
    for candidate in ACTIONS_CONFIG_CANDIDATES:
        if candidate.exists():
            return Result.success(candidate)

    expected_paths = ", ".join(str(candidate) for candidate in ACTIONS_CONFIG_CANDIDATES)
    return Result.failure(FileNotFoundError(f"Action config file not found. Expected one of: {expected_paths}"))


def _read_host_actions_config_text() -> Result[tuple[Path, str], BaseException]:
    path_result = _resolve_actions_config_path()
    if Result.is_failure(path_result):
        return Result.failure(path_result.error)

    path = path_result.data

    try:
        return Result.success((path, path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


def _load_host_actions_config_from_text(
    config_text: str,
    config_path: Path,
    update_last_known_good: bool,
) -> Result[int, BaseException]:
    global LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT
    global LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH

    extension = config_path.suffix.lower()
    if extension == ".json":
        config_format = "json"
    elif extension in {".yaml", ".yml"}:
        config_format = "yaml"
    else:
        return Result.failure(
            ValueError("Unsupported actions config extension. Use .json, .yaml, or .yml")
        )

    snapshot = action_engine.snapshot_state()
    result = load_actions_from_text(
        action_engine,
        config_text,
        config_format=config_format,
        replace_configured_actions=True,
    )

    if Result.is_success(result):
        reserved_conflicts: list[str] = []
        for reserved_name in sorted(RESERVED_COMMAND_NAMES):
            resolved_action_name = action_engine.resolve_action_name(reserved_name)
            if resolved_action_name is None:
                continue

            if resolved_action_name == reserved_name:
                reserved_conflicts.append(reserved_name)
                continue

            reserved_conflicts.append(f"{reserved_name} (alias for {resolved_action_name})")

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
        LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH = config_path

    return result


def _load_host_actions_config() -> Result[tuple[int, Path], BaseException]:
    text_result = _read_host_actions_config_text()
    if Result.is_failure(text_result):
        return Result.failure(text_result.error)

    config_path, config_text = text_result.data
    load_result = _load_host_actions_config_from_text(
        config_text,
        config_path,
        update_last_known_good=True,
    )

    if Result.is_failure(load_result):
        return Result.failure(load_result.error)

    return Result.success((load_result.data, config_path))


def _reload_host_actions_with_rollback() -> tuple[Result[tuple[int, Path], BaseException], bool]:
    load_result = _load_host_actions_config()
    if Result.is_success(load_result):
        return load_result, False

    if LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT and LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH:
        restore_result = _load_host_actions_config_from_text(
            LAST_KNOWN_GOOD_ACTIONS_CONFIG_TEXT,
            LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH,
            update_last_known_good=False,
        )
        if Result.is_success(restore_result):
            return Result.success((restore_result.data, LAST_KNOWN_GOOD_ACTIONS_CONFIG_PATH)), True

    return Result.failure(load_result.error), False


def is_authorized(update: Update) -> bool:
    """Security check to silently ignore unauthorized users."""
    user = update.effective_user
    if user is None:
        return False

    result = action_engine.is_known_user(user.id)
    if not result:
        logging.warning(f"Unauthorized access attempt by user ID: {user.id}")
    return result


def has_role(user_id: int, role_name: str) -> bool:
    user_roles = set(action_engine.get_user_roles(user_id))
    return role_name.strip().lower() in user_roles


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


def _normalize_requested_tags(raw_tags: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_tag in raw_tags:
        clean = raw_tag.strip().lower()
        if clean and clean not in normalized:
            normalized.append(clean)

    return tuple(normalized)


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

    resolved_action_name = action_engine.resolve_action_name(action_name)
    if resolved_action_name is None or action_engine.describe_action(resolved_action_name) is None:
        await message.reply_text(f"Action '{action_name}' is not registered.")
        return

    context.args = list(raw_args)
    await _dispatch_action(update, context, resolved_action_name)


async def reload_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    if not has_role(user.id, ADMIN_ROLE):
        await message.reply_text("❌ You are not allowed to run /reload_actions.")
        logging.warning("Denied reload_actions for user ID %s due to missing role '%s'", user.id, ADMIN_ROLE)
        return

    reload_result, restored = _reload_host_actions_with_rollback()
    if Result.is_success(reload_result):
        reload_count, config_path = reload_result.data
        if restored:
            await message.reply_text(
                "⚠️ Reload failed. Restored last known good action configuration.",
            )
            return

        await message.reply_text(
            f"✅ Reloaded actions from `{config_path}`. Registered handlers: `{reload_count}`",
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
    resolved_action_name = action_engine.resolve_action_name(action_name)
    details = action_engine.describe_action(resolved_action_name or action_name)
    if details is None:
        await message.reply_text(f"Action '{action_name}' is not registered.")
        return

    await message.reply_text(build_action_info_text(resolved_action_name or action_name, details))


async def actions_by_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return

    message = update.message
    if message is None:
        return

    requested_tags = _normalize_requested_tags(context.args)
    if not requested_tags:
        await message.reply_text("Usage: /actions_by_tag <tag> [<tag> ...]")
        return

    if RESERVED_UNTAGGED_FILTERS.intersection(requested_tags):
        action_names = action_engine.list_untagged_actions()
        summary_line = "Showing untagged actions. Reserved filters: none, unknown"
    else:
        action_names = action_engine.list_actions_by_tags(requested_tags)
        summary_line = "Showing actions matching any tag: " + ", ".join(requested_tags)

    action_handler_counts = {
        action_name: len(action_engine.list_handlers(action_name))
        for action_name in action_names
    }
    action_aliases = {
        action_name: action_engine.get_action_aliases(action_name)
        for action_name in action_names
    }
    action_tags = {
        action_name: action_engine.get_action_tags(action_name)
        for action_name in action_names
    }

    if not action_names:
        if RESERVED_UNTAGGED_FILTERS.intersection(requested_tags):
            await message.reply_text("No untagged actions are registered.")
            return

        await message.reply_text("No actions matched the requested tags.")
        return

    await message.reply_text(
        build_help_text(
            action_names,
            action_handler_counts,
            action_aliases,
            action_tags,
            heading="🏷️ Actions By Tag",
            summary_line=summary_line,
            include_admin_commands=False,
        )
    )


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
    action_aliases = {
        action_name: action_engine.get_action_aliases(action_name)
        for action_name in action_names
    }
    action_tags = {
        action_name: action_engine.get_action_tags(action_name)
        for action_name in action_names
    }
    await message.reply_text(
        build_help_text(action_names, action_handler_counts, action_aliases, action_tags),
    )


def main() -> None:
    if not TOKEN:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN")

    reload_result, restored = _reload_host_actions_with_rollback()
    if Result.is_success(reload_result):
        reload_count, config_path = reload_result.data
        if restored:
            logging.warning(
                "Startup reload failed. Restored last known good action configuration from memory."
            )
        else:
            logging.info(
                "Reloaded actions at startup from %s. Registered handlers: %s",
                config_path,
                reload_count,
            )
    else:
        logging.error("Failed to reload actions at startup: %s", reload_result.error)

    app = ApplicationBuilder().token(TOKEN).build()

    # Register commands
    app.add_handler(CommandHandler("reload_actions", reload_actions))
    app.add_handler(CommandHandler("action_info", action_info))
    app.add_handler(CommandHandler("actions_by_tag", actions_by_tag))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.COMMAND, dispatch_action_command))

    logging.info("Bot is polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
