# Bot Service

This service runs a Telegram bot that can inspect and control Docker containers on the host through the mounted Docker socket.

## What It Does

- replies to `/status` with the current Docker container list
- starts a container with `/start <container-name>`
- stops a container with `/stop <container-name>`
- restarts a container with `/restart <container-name>`
- shows logs with `/logs <container-name> [tail]`
- lists available commands with `/help`
- reloads host action config with `/reload_actions`
- ignores requests from Telegram users not listed in `ALLOWED_TELEGRAM_IDS`
- supports an action engine with staged handlers for each command

## Configuration

The service expects these environment variables:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
ALLOWED_TELEGRAM_IDS=123456789
BOT_ACTIONS_CONFIG=/app/config/actions.json
```

`ALLOWED_TELEGRAM_IDS` should contain numeric Telegram user IDs, separated by commas if you want to allow more than one user.

`BOT_ACTIONS_CONFIG` is optional. If set, the bot loads extra action registrations from a host-mounted JSON file.

An example config is available at `config/actions.example.json`.

Each handler entry can define `timeout_seconds` to bound execution time.

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
/stop <container-name>
/restart <container-name>
/logs <container-name> 50
/help
/reload_actions
```

If your Telegram user ID is authorized, the bot should reply with container status.

## Security Note

This service has access to the host Docker daemon through `/var/run/docker.sock`. Treat it as a privileged admin service and only allow trusted Telegram user IDs.
