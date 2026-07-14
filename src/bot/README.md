# Bot Service

This service runs a Telegram bot that can inspect and control Docker containers on the host through the mounted Docker socket.

## What It Does

- replies to `/status` with the current Docker container list
- starts a container with `/start <container-name>`
- stops a container with `/stop <container-name>`
- restarts a container with `/restart <container-name>`
- shows logs with `/logs <container-name> [tail]`
- dispatches configured slash commands such as `/server_uptime`
- lists available commands with `/help`
- shows action details with `/action_info <action_name>`
- reloads host action config with `/reload_actions`
- ignores requests from Telegram users not listed in `ALLOWED_TELEGRAM_IDS`
- supports an action engine with staged handlers for each command

## Configuration

The service expects these environment variables:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
ALLOWED_TELEGRAM_IDS=123456789
BOT_ACTIONS_CONFIG=/app/config/actions.yaml
BOT_HOST_ACTION_SOCKET=/var/run/telegram-bot/host-actions.sock
```

`ALLOWED_TELEGRAM_IDS` should contain numeric Telegram user IDs, separated by commas if you want to allow more than one user.

`BOT_ACTIONS_CONFIG` is optional. If set, the bot loads extra action registrations from a host-mounted JSON or YAML file.

`BOT_HOST_ACTION_SOCKET` is optional unless you use host-backed actions. It should point at the Unix socket exposed by the host runner inside the container.

Example configs are available at `config/actions.example.json` and `config/actions.example.yaml`.

The host runner operation template lives at `config/host-actions.example.yaml`.

Each action can define `default_timeout_seconds`, and each handler entry can override with `timeout_seconds`.

Handler entries support two execution targets:

- local handlers use `module` and `callable` and run inside the container
- host handlers use `target: host` and `operation: <operation-id>` and execute through the host runner

If `/reload_actions` fails, the bot restores the last known good action configuration snapshot in memory.

Configured actions cannot use reserved command names: `/help`, `/action_info`, and `/reload_actions`.

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

To enable host-backed actions, run the host runner on the host and point it at the shared socket directory. For example:

```sh
cd src/host-runner
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_SOCKET="$PWD/../../tmp/host-actions.sock" \
uv run python main.py
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
/action_info status
/reload_actions
/server_uptime
```

If your Telegram user ID is authorized, the bot should reply with container status.

## Security Note

This service has access to the host Docker daemon through `/var/run/docker.sock`. Treat it as a privileged admin service and only allow trusted Telegram user IDs.
