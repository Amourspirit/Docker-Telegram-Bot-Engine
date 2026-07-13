# Telegram Docker Control Bot

This project runs a Telegram bot that can inspect and control Docker containers on the host where it is deployed. The bot is intended for private operational use: it connects to the Telegram Bot API, accepts commands from explicitly allowed Telegram user IDs, and talks to the local Docker daemon through the mounted Docker socket.

The current implementation uses Telegram polling. That means the container does not expose an inbound HTTP port and does not require a webhook, reverse proxy, or public route.

## Features

- Show Docker container status with `/status`
- Start a container with `/start <container-name>`
- Restrict access to specific Telegram user IDs via `ALLOWED_TELEGRAM_IDS`
- Run as a Docker container with Docker Compose

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
```

Notes:

- `ALLOWED_TELEGRAM_IDS` must contain numeric Telegram user IDs, not usernames.
- Multiple Telegram users can be allowed with a comma-separated list, for example `123456789,987654321`.
- On macOS with Docker Desktop, the default Docker socket mapping in `docker-compose.yaml` is already set up to use `/var/run/docker.sock` unless you override it.

## How It Works

The bot process starts inside the `telegram-c2-bot` container and uses long polling to receive updates from Telegram. It then uses the Docker Python SDK to query or control containers through the mounted Docker socket.

Current commands:

- `/status` lists all containers and whether they are running
- `/start <container-name>` starts the named container

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

Useful next commands for this bot would be:

- `/stop <container-name>`
- `/restart <container-name>`
- `/logs <container-name>`
- `/help`

If you later switch to a webhook-based deployment behind Cloudflare Tunnel or another reverse proxy, you would need to add an inbound HTTP listener and expose an internal application port such as `8080`.
