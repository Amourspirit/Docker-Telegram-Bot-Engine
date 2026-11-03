# AGENTS.md

Private Telegram bot that inspects/controls Docker containers on the host through the mounted
Docker socket, plus a host-side runner that executes curated host commands.

## Repo shape

Three **independent** uv projects (there is no root workspace, no root `pyproject.toml`, no root
pytest config). Each has its own `pyproject.toml` + `uv.lock` + `pyproject` pytest options
(`asyncio_mode = "auto"`, `pythonpath = ["."]`).

| Package | Path | Role |
|---|---|---|
| bot | `src/bot/` | Telegram bot (`python-telegram-bot`, long polling). Built into the `telegram-c2-bot` image by `src/bot/Dockerfile`. |
| host-runner | `src/host-runner/` | Executes approved host commands. Runs on the **host**, not in a container. |
| config-builder | `src/config-builder/` | CLI that merges config templates into generated config files. |

Entrypoints: `src/bot/main.py` → `bot_service.bot.main`, `src/host-runner/main.py` →
`host_runner.server.main`, `src/config-builder/main.py` → `builder.cli.main`. Root `main.py` is a
stub, not the app.

Config tree (`storage/` is **gitignored**; only `examples/storage/` and root `config/` are tracked):

- `storage/templates/{actions,host-actions,users}/` — hand-edited sources.
- `storage/config/bot/{actions.yaml,users.yaml}` and `storage/config/host/host-actions.yaml` —
  generated. `storage/config/bot` is what the container mounts at `/app/config`
  (`.env: CONFIG_PATH` → `docker-compose.yaml: ${CONFIG_PATH}/bot:/app/config:ro`).
- `storage/scripts/` — helper scripts for host operations. The host runner exports
  `HOST_PROJECT_ROOT` (repo root, found via the `.project_root` marker); scripts source it.

Edit templates, not generated files. Never hand-edit `storage/config/*`.

## Commands

Tests must run **from inside a package directory** (root `uv run pytest` fails — there is no root
project). Async tests need no marker (`asyncio_mode = "auto"`).

```sh
cd src/bot && uv run pytest                 # 88 tests
cd src/host-runner && uv run pytest         # 32 tests
cd src/config-builder && uv run pytest      # 11 tests
cd src/bot && uv run pytest tests/test_engine.py -q   # single file/test
```

No lint or typecheck tooling is configured (no ruff/mypy/pytest-cov config) — don't invent commands.

Makefile (run from repo root; it `include`s `.env`, so `.env` values override the `?=` defaults):

```sh
make up              # start host runner + `docker compose up -d --build` (rebuilds image)
make down / restart  # stop / restart both services
make logs            # tail bot container logs
make status          # compose ps + host-runner PID/config/host/port
make start-host-runner / stop-host-runner / host-runner-logs
make build-actions   # = config-backup + build-bot-actions + build-host-actions
```

## Config build pipeline

- `make build-bot-actions` → `storage/templates/actions/*.{json,yaml,yml}` →
  `storage/config/bot/actions.yaml`.
- `make build-host-actions` → `storage/templates/host-actions/*` →
  `storage/config/host/host-actions.yaml`.
- **No make target builds `users.yaml`.** `docs/templates-and-build.md` claims
  `build-bot-actions` merges users too — it does not. Build it manually:

```sh
cd src/config-builder && uv run python main.py \
  --input-type users --base-dir ../.. \
  --input "storage/templates/users/*.yaml" \
  --output storage/config/bot/users.yaml
```

Config-builder details worth knowing:

- `--input` globs resolve against `--base-dir`; `--output`, `--report-duplicates`,
  `--summary-json` resolve against the **project root** (located by walking up to `.project_root`).
- Duplicate keys: **first file wins** (files processed in lexicographic path order) and the build
  still succeeds; use `--fail-on-duplicate` to make duplicates fatal. `--check` exits non-zero when
  the generated output differs from the file on disk — useful as a drift check.
- `--dry-run`, `--strict-key-type`, `--verbose` are available.

After changing templates: `make build-actions`, then `/reload_actions` in Telegram (admin role) —
the bot re-reads the mounted files without a restart. A failed reload restores the last known good
users/actions snapshot in memory.

## Bot runtime rules

- Config lookup order in the container: `/app/config/actions.yaml`, `.yml`, `.json` (and the same
  for `users.*`). One file each; the first that exists wins.
- `actions.yaml` must **not** contain a `users` key — users belong in `users.yaml`, otherwise the
  load fails.
- Reserved command names: `help`, `action_info`, `actions_by_tag`, `reload_actions`. An action or
  alias using one of them makes the whole config load fail and roll back.
- Authorization: user must exist in the `users` map **and** the action must declare
  `allowed_roles` that intersect the user's roles. Actions without `allowed_roles` are denied.
  `/reload_actions` requires the `admin` role.
- Stages: handlers with the same `stage` run in parallel; later stages run after. A failing handler
  cancels later stages unless `stop_on_failure: false` (handler value wins, else the action's
  `stop_on_failure`, default `true`).
- Timeout precedence: handler `timeout_seconds` → action `default_timeout_seconds` → host operation
  `timeout_seconds`. The host runner rejects timeouts `<= 0` or `> 600`.
- Reply format precedence: host operation resolved format → action-level `reply_format` →
  `markdown`. Formats: `markdown`, `text`, `json`, `yaml`, `html`, `fenced-text`.
- Replies are chunked at 4000 chars; if Telegram rejects the Markdown entities, the bot resends
  the chunk as plain text.

## Host runner rules

- Commands run **without a shell** (`asyncio.create_subprocess_exec`). Use
  `/bin/bash -lc "<script>"` for shell features. `$VAR` and `~` are expanded by the runner itself
  (`os.path.expandvars` / `expanduser`), not by a shell.
- Telegram-supplied args are appended only when `allow_user_args: true`, and **every** arg must be
  listed in `allowed_optional_params`; a leading em dash (`—json`) is normalized to `--json`.
- Handler `params` are substituted into `{{name}}` placeholders in the command; each placeholder
  must be listed in the operation's `allowed_placeholders`, otherwise the request is rejected.
- Transport: TCP via `HOST_ACTIONS_HOST`/`HOST_ACTIONS_PORT` (Makefile defaults `0.0.0.0:8787`) or
  a Unix socket via `HOST_ACTIONS_SOCKET`. The bot prefers `BOT_HOST_ACTION_ENDPOINT` over
  `BOT_HOST_ACTION_SOCKET`.
- The compose file mounts only the Docker socket and the bot config, so Unix-socket mode needs an
  extra mount. Both compose services declare `extra_hosts: host.docker.internal:host-gateway` so the
  TCP name resolves on Linux; if that entry is dropped, host actions fail with `[Errno -2] Name or
  service not known`. Verify TCP reachability from the container before debugging the runner.

## Operational gotchas

- Watchdog targets are `watchdog-install` / `watchdog-uninstall` / `watchdog-load` /
  `watchdog-unload` / `watchdog-logs`. `README.md` and `docs/` say `make install-watchdog` /
  `make uninstall-watchdog` — those targets **do not exist** (`No rule to make target`).
- `make config-backup` copies `storage/{config,scripts,templates}` into
  `storage/backup/config_YY-MM-DD_HH-MM-SS`; `config-backup-list` / `config-backup-cleanup`
  (keeps the newest `CONFIG_BACKUP_KEEP`, default 5).
- The host runner is started with `nohup` + a PID file at `storage/runner/host-runner.pid`, logging
  to `storage/runner/host-runner.log`.
- `.env` holds a live `TELEGRAM_BOT_TOKEN` and is gitignored — never commit it or paste its
  contents into code, docs, commits, or PRs.
- The bot mounts the Docker socket: treat every change here as privileged-host work.

## Conventions

- Git flow: `main` + `develop`; feature/hotfix branch naming per
  `.github/skills/git-flow-branch-creator/SKILL.md`.
- Commits are conventional commits (`feat:`, `fix:`, `chore:`) per `.github/skills/git-commit/SKILL.md`.
- `.github/copilot-instructions.md` is a Copilot/context-mode MCP routing doc, not repo policy.
- Docs: `docs/bot-configuration.md`, `docs/host-configuration.md`, `docs/templates-and-build.md`,
  `docs/priority-overrides.md`, `docs/watchdog.md`, `docs/folder-layout.md`. Several are stale
  (watchdog target names, the users build target) — trust the Makefile and code over the prose.
- Known local drift: the untracked `storage/scripts/sysinfo_md.sh` prints on source but no longer
  defines `markdown_table`, so the `server.system_info` host operation fails as written.
