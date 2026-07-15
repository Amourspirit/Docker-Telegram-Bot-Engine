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
- lists actions by tag with `/actions_by_tag <tag> [<tag> ...]`
- shows action details with `/action_info <action_name>`
- reloads host action config with `/reload_actions`
- ignores requests from Telegram users not listed in action config `users`
- applies role-based checks per action from `BOT_ACTIONS_CONFIG`
- supports an action engine with staged handlers for each command

## Configuration

The service expects these environment variables:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
BOT_ACTIONS_CONFIG=/app/config/actions.yaml
BOT_HOST_ACTION_ENDPOINT=host.docker.internal:8787
BOT_HOST_ACTION_SOCKET=/var/run/telegram-bot/host-actions.sock
```

`BOT_ACTIONS_CONFIG` is optional. If set, the bot loads extra action registrations from a host-mounted JSON or YAML file.

`BOT_HOST_ACTION_ENDPOINT` is optional. If set, the bot uses TCP transport to the host runner in `host:port` (or `tcp://host:port`) format.

`BOT_HOST_ACTION_SOCKET` is optional unless you use host-backed actions. It should point at the Unix socket exposed by the host runner inside the container.

If both endpoint and socket are set, the bot prefers `BOT_HOST_ACTION_ENDPOINT`.

Example configs are available at `config/actions.example.json` and `config/actions.example.yaml`.

The host runner operation template lives at `config/host-actions.example.yaml`.

Each action can define `default_timeout_seconds`, and each handler entry can override with `timeout_seconds`.

Each action can also define optional `tags`:

- `tags` must be a list of strings
- tags are normalized by trimming whitespace and lowercasing
- `/help` shows tags next to each action when present
- `/actions_by_tag <tag> [<tag> ...]` matches actions by any supplied tag
- reserved filters `none` and `unknown` show only actions with no tags assigned

Handler entries support two execution targets:

- local handlers use `module` and `callable` and run inside the container
- host handlers use `target: host` and `operation: <operation-id>` and execute through the host runner

Host handlers can also define static params that are sent to the host runner:

- use `params` as a mapping of string keys to string values
- example: `params: {domain_var: CF_SPIRAL_UI_DOMAIN_NAME}`
- list formats such as `- name: ...` are rejected

If `/reload_actions` fails, the bot restores the last known good action configuration snapshot in memory.

Role-based authorization uses `BOT_ACTIONS_CONFIG`:

- `users` maps Telegram user IDs to user definitions
- each user definition can contain `roles`
- each action must define `allowed_roles`
- actions without `allowed_roles` are denied by default
- `/reload_actions` requires `admin` role

Configured actions cannot use reserved command names: `/help`, `/action_info`, `/actions_by_tag`, and `/reload_actions`.

## Runtime

- Python 3.12
- `python-telegram-bot` for Telegram integration
- Docker SDK for Python for Docker control
- polling mode, so no inbound port is required

The container image is built from `src/bot/Dockerfile` and starts with:

```sh
python /app/main.py
```

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

Run the host runner when you want host-backed actions:

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
- confirm your numeric Telegram ID exists in `users` inside `BOT_ACTIONS_CONFIG`
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
