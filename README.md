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
- Reload action config with `/reload_actions`
- Run curated host actions such as `/server_uptime` through a local host runner
- Restrict access and roles via `users` and `allowed_roles` in action config
- Run the full stack through the Makefile
- Use an event-driven action engine with config-loaded registrations

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
DOCKER_SOCKET_PATH=/var/run/docker.sock
BOT_HOST_ACTION_ENDPOINT=host.docker.internal:8787
BOT_HOST_ACTION_SOCKET=/var/run/telegram-bot/host-actions.sock
```

Notes:

- On macOS with Docker Desktop, the default Docker socket mapping in `docker-compose.yaml` is already set up to use `/var/run/docker.sock` unless you override it.
- The bot requires one users config file in `/app/config` and checks in this order: `users.yaml`, `users.yml`, then `users.json`.
- The bot also requires one action config file in `/app/config` and checks in this order: `actions.yaml`, `actions.yml`, then `actions.json`.
- Templates are available at `config/users.example.yaml`, `config/users.example.json`, `config/actions.example.yaml`, and `config/actions.example.json`.
- `BOT_HOST_ACTION_ENDPOINT` is optional and enables TCP transport to the host runner using `host:port` (or `tcp://host:port`).
- `BOT_HOST_ACTION_SOCKET` is optional unless you configure host-backed actions. It should point to the Unix socket created by the host runner inside the container.
- If both endpoint and socket are set, endpoint is preferred.
- Actions can define `default_timeout_seconds`; handlers can optionally override with `timeout_seconds`.
- action config handlers can include `timeout_seconds` to enforce per-handler execution limits.
- users config supports role controls:
  - `users`: map of Telegram user ID to user configuration
    - `roles`: list of role names for that user
  - `actions.<name>.allowed_roles`: roles allowed to execute that action
  - actions without `allowed_roles` are denied by default
- Host runner operations are declared separately in `config/host-actions.example.yaml`.
- Host runner operations can define `allowed_optional_params`; every Telegram-supplied arg must be listed there when `allow_user_args` is true.
- If any Telegram-supplied arg is not approved in `allowed_optional_params`, the bot returns an error message to the Telegram client.

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
- `/reload_actions` reloads users config from `/app/config/users.yaml`, `/app/config/users.yml`, or `/app/config/users.json`
- `/reload_actions` reloads action config from `/app/config/actions.yaml`, `/app/config/actions.yml`, or `/app/config/actions.json`
- `/reload_actions` requires `admin` role
- `/server_uptime` is an example host-backed command when the example configs are enabled

If reload fails, the bot restores the last known good users/actions configuration snapshot in memory.

Configured actions cannot claim the reserved command names `/help`, `/action_info`, or `/reload_actions`.

If a Telegram user is not listed in the users config `users` mapping, the bot ignores the request.

Authorization order is:

1. user must be in `users`
2. action must declare `allowed_roles`
3. user roles from `users.<id>.roles` must intersect with action `allowed_roles`

## Run With Make

From the project root:

```sh
make up
```

Check container status:

```sh
make status
```

View logs:

```sh
make logs
```

Run the host runner on the host if you want host-backed actions (TCP mode for Docker Desktop macOS):

```sh
make start-host-runner
```

Linux hosts can keep Unix socket mode:

```sh
make start-host-runner
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
- confirm your numeric Telegram ID is present in `users` within the selected `/app/config/users.*` file
- confirm the bot container is running
- confirm the container can reach Telegram on outbound port `443`
- inspect logs with `make logs`

## Make Targets

- `make up` starts the host runner and bot container
- `make down` stops the bot container and host runner
- `make restart` restarts both services
- `make logs` tails the bot container logs
- `make host-runner-logs` tails the host runner log
- `make status` shows bot container and host runner status
- `make start-host-runner` starts only the host runner
- `make stop-host-runner` stops only the host runner

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
