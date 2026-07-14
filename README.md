# Telegram Docker Control Bot

This project runs a Telegram bot that can inspect and control Docker containers on the host where it is deployed. The bot is intended for private operational use: it connects to the Telegram Bot API, accepts commands from explicitly allowed Telegram user IDs, and talks to the local Docker daemon through the mounted Docker socket.

The current implementation uses Telegram polling. That means the container does not expose an inbound HTTP port and does not require a webhook, reverse proxy, or public route.

## Features

- Show Docker container status with `/status`
- Start a container with `/start <container-name>`
- Stop a container with `/stop <container-name>`
- Restart a container with `/restart <container-name>`
- Read container logs with `/logs <container-name> [tail]`
- List available commands with `/help`
- Inspect action stages with `/action_info <action_name>`
- Reload host action config with `/reload_actions`
- Run curated host actions such as `/server_uptime` through a local host runner
- Restrict access to specific Telegram user IDs via `ALLOWED_TELEGRAM_IDS`
- Run as a Docker container with Docker Compose
- Use an event-driven action engine with host-loaded registrations

## Project Structure

```text
.
├── docker-compose.yaml
├── main.py
└── src/
 └── bot/
  ├── Dockerfile
  ├── main.py
  ├── pyproject.toml
  └── bot_service/
   └── bot.py
```

## Requirements

- Docker and Docker Compose
- A Telegram bot token from BotFather
- Your numeric Telegram user ID
- Network access from the container to Telegram over HTTPS on port `443`

## Configuration

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=1234567890:replace-with-your-bot-token
ALLOWED_TELEGRAM_IDS=123456789
DOCKER_SOCKET_PATH=/var/run/docker.sock
BOT_ACTIONS_CONFIG=/app/config/actions.json
BOT_HOST_ACTION_ENDPOINT=host.docker.internal:8787
BOT_HOST_ACTION_SOCKET=/var/run/telegram-bot/host-actions.sock
```

Notes:

- `ALLOWED_TELEGRAM_IDS` must contain numeric Telegram user IDs, not usernames.
- Multiple Telegram users can be allowed with a comma-separated list, for example `123456789,987654321`.
- On macOS with Docker Desktop, the default Docker socket mapping in `docker-compose.yaml` is already set up to use `/var/run/docker.sock` unless you override it.
- `BOT_ACTIONS_CONFIG` is optional and points to a host-mounted JSON or YAML action config. Templates exist at `config/actions.example.json` and `config/actions.example.yaml`.
- `BOT_HOST_ACTION_ENDPOINT` is optional and enables TCP transport to the host runner using `host:port` (or `tcp://host:port`).
- `BOT_HOST_ACTION_SOCKET` is optional unless you configure host-backed actions. It should point to the Unix socket created by the host runner inside the container.
- If both endpoint and socket are set, endpoint is preferred.
- Actions can define `default_timeout_seconds`; handlers can optionally override with `timeout_seconds`.
- Action config handlers can include `timeout_seconds` to enforce per-handler execution limits.
- Host runner operations are declared separately in `config/host-actions.example.yaml`.

## How It Works

The bot process starts inside the `telegram-c2-bot` container and uses long polling to receive updates from Telegram. It then uses the Docker Python SDK to query or control containers through the mounted Docker socket.

For host-backed actions, the bot sends a small JSON request to a dedicated host runner process over TCP or Unix socket. The runner validates the configured operation and executes an approved host command, then returns the result text to the bot.

Current commands:

- `/status` lists all containers and whether they are running
- `/start <container-name>` starts the named container
- `/stop <container-name>` stops the named container
- `/restart <container-name>` restarts the named container
- `/logs <container-name> [tail]` returns recent container logs
- `/help` shows currently registered actions
- `/action_info <action_name>` shows policy and staged handlers for one action
- `/reload_actions` reloads host action config from `BOT_ACTIONS_CONFIG`
- `/server_uptime` is an example host-backed command when the example configs are enabled

If action reload fails, the bot restores the last known good action configuration snapshot in memory.

Configured actions cannot claim the reserved command names `/help`, `/action_info`, or `/reload_actions`.

If a Telegram user is not listed in `ALLOWED_TELEGRAM_IDS`, the bot ignores the request.

## Run With Docker Compose

From the project root:

```sh
docker compose up -d --build
```

Check container status:

```sh
docker compose ps
```

View logs:

```sh
docker compose logs -f telegram-c2-bot
```

Run the host runner on the host if you want host-backed actions (TCP mode for Docker Desktop macOS):

```sh
cd src/host-runner
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_HOST=0.0.0.0 \
HOST_ACTIONS_PORT=8787 \
uv run python main.py
```

Linux hosts can keep Unix socket mode:

```sh
cd src/host-runner
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_SOCKET="$PWD/../../tmp/host-actions.sock" \
uv run python main.py
```

If startup succeeds, the logs should include a line showing that the bot is polling.

## Test From Telegram

1. Open Telegram and search for your bot username.
2. Start a chat with the bot.
3. Send `/status`.
4. Confirm that the bot replies with a list of Docker containers.
5. Send `/start <container-name>` for a stopped test container.
6. Send `/status` again to confirm the container state changed.

If the bot does not reply:

- confirm `TELEGRAM_BOT_TOKEN` is valid
- confirm your numeric Telegram ID is in `ALLOWED_TELEGRAM_IDS`
- confirm the bot container is running
- confirm the container can reach Telegram on outbound port `443`
- inspect logs with `docker compose logs -f telegram-c2-bot`

## No Port Exposure Required

Because this bot uses polling, no container port needs to be published. Telegram clients do not connect directly to your container. Instead:

1. your Telegram client sends a message to Telegram
2. Telegram stores the update
3. the bot polls Telegram for updates
4. the bot replies through the Telegram Bot API

This is simpler than a webhook deployment and is usually the better fit for a small private admin bot.

## Security Considerations

Mounting the Docker socket gives the bot broad control over the host Docker daemon. Treat this bot as a privileged administrative service.

Minimum recommendations:

- only allow your own Telegram user ID or a very small trusted set
- use a dedicated bot token
- do not expose the Docker socket to untrusted workloads
- review logs for unauthorized access attempts
- deploy only on hosts where Docker control through Telegram is an acceptable risk

## Development Notes

The Python package for the bot lives under `src/bot/` and is built into the runtime image defined in `src/bot/Dockerfile`.

Key implementation details:

- Telegram integration: `python-telegram-bot`
- Docker integration: Docker SDK for Python
- Runtime mode: polling via `app.run_polling()`

## Future Improvements

If you later switch to a webhook-based deployment behind Cloudflare Tunnel or another reverse proxy, you would need to add an inbound HTTP listener and expose an internal application port such as `8080`.
