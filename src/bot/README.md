# Bot Service

This service runs a Telegram bot that can inspect and control Docker containers on the host through the mounted Docker socket.

## What It Does

- replies to `/status` with the current Docker container list
- starts a container with `/start <container-name>`
- ignores requests from Telegram users not listed in `ALLOWED_TELEGRAM_IDS`

## Configuration

The service expects these environment variables:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
ALLOWED_TELEGRAM_IDS=123456789
```

`ALLOWED_TELEGRAM_IDS` should contain numeric Telegram user IDs, separated by commas if you want to allow more than one user.

## Runtime

- Python 3.12
- `python-telegram-bot` for Telegram integration
- Docker SDK for Python for Docker control
- polling mode, so no inbound port is required

The container image is built from `src/bot/Dockerfile` and starts with:

```sh
python /app/main.py
```

## Local Run

From the project root:

```sh
docker compose up -d --build
docker compose logs -f telegram-c2-bot
```

When the service starts correctly, it begins polling Telegram for updates.

## Test

Open a chat with your bot in Telegram and send:

```text
/status
```

If your Telegram user ID is authorized, the bot should reply with container status.

## Security Note

This service has access to the host Docker daemon through `/var/run/docker.sock`. Treat it as a privileged admin service and only allow trusted Telegram user IDs.
