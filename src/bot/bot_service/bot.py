# bot.py
import os
import logging
import uuid
import docker
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bot_service.actions import register_default_actions
from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.host_loader import load_actions_from_file
from bot_service.result import Result

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


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

# Initialize action engine and register built-in handlers.
action_engine = ActionEngine()
register_default_actions(action_engine)

HOST_ACTIONS_CONFIG = os.environ.get("BOT_ACTIONS_CONFIG")
if HOST_ACTIONS_CONFIG:
    load_result = load_actions_from_file(action_engine, HOST_ACTIONS_CONFIG)
    if Result.is_success(load_result):
        logging.info(f"Loaded {load_result.data} handlers from {HOST_ACTIONS_CONFIG}")
    else:
        logging.error(f"Failed to load action config from {HOST_ACTIONS_CONFIG}: {load_result.error}")

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
        shared_state={"docker_client": docker_client},
    )

    result = await action_engine.dispatch(event_args)
    if Result.is_failure(result):
        await message.reply_text(f"Error: {result.error}")
        return

    await message.reply_text(result.data, parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _dispatch_action(update, context, "status")

async def start_container(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _dispatch_action(update, context, "start")

def main() -> None:
    if not TOKEN or not ALLOWED_IDS:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or ALLOWED_TELEGRAM_IDS")
        
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Register commands
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("start", start_container))
    
    logging.info("Bot is polling...")
    app.run_polling()

if __name__ == '__main__':
    main()