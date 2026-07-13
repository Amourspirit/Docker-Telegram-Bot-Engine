# bot.py
import os
import logging
import docker
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Comma-separated list of your personal Telegram User IDs (NOT usernames)
ALLOWED_IDS = [int(id) for id in os.environ.get("ALLOWED_TELEGRAM_IDS", "").split(",")]

# Initialize Docker client (connects via the mounted socket)
docker_client = docker.from_env()

def is_authorized(update: Update) -> bool:
    """Security check to silently ignore unauthorized users."""
    result = update.effective_user.id in ALLOWED_IDS
    if not result:
        logging.warning(f"Unauthorized access attempt by user ID: {update.effective_user.id}")
    return result

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update): return
    
    try:
        containers = docker_client.containers.list(all=True)
        response = "🐳 **Docker Status:**\n\n"
        for c in containers:
            icon = "🟢" if c.status == "running" else "🔴"
            response += f"{icon} `{c.name}` ({c.status})\n"
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error querying Docker: {str(e)}")

async def start_container(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update): return
    
    if not context.args:
        await update.message.reply_text("Please provide a container name. Usage: /start <name>")
        return
    
    target = context.args[0]
    try:
        container = docker_client.containers.get(target)
        container.start()
        await update.message.reply_text(f"✅ Container `{target}` started successfully.", parse_mode='Markdown')
    except docker.errors.NotFound:
        await update.message.reply_text(f"❌ Container `{target}` not found.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

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