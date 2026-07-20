# Project Folder Layout

This document describes the complete folder structure for the telegram-bot project.

## Complete Directory Tree

```
telegram-bot/
├── docs/                              # 📖 Configuration documentation (you are here)
│   ├── README.md
│   ├── bot-configuration.md
│   ├── host-configuration.md
│   ├── templates-and-build.md
│   ├── priority-overrides.md
│   └── folder-layout.md
│
├── storage/                           # 🏗️ Production configuration (main deployment)
│   ├── templates/                     # 📋 Template files (input to build)
│   │   ├── actions/                   # Bot action templates
│   │   │   ├── actions-stack.yaml
│   │   │   ├── actions-cf.yaml
│   │   │   ├── actions-logs.yaml
│   │   │   └── ...
│   │   │
│   │   ├── host-actions/              # Host operation templates
│   │   │   ├── host-actions-stack.yaml
│   │   │   ├── host-actions-cf.yaml
│   │   │   └── ...
│   │   │
│   │   └── users/                     # User and role templates
│   │       ├── admin-users.yaml
│   │       ├── team-users.yaml
│   │       └── ...
│   │
│   ├── config/                        # ⚙️ Generated configurations (auto-generated)
│   │   ├── bot/
│   │   │   ├── actions.yaml          # GENERATED: All bot actions merged
│   │   │   └── users.yaml            # GENERATED: All users merged
│   │   │
│   │   └── host/
│   │       └── host-actions.yaml     # GENERATED: All host operations merged
│   │
│   ├── scripts/                       # 🔧 Helper shell scripts
│   │   ├── cf.sh                      # Cloudflare operations
│   │   ├── stack.sh                   # Stack management
│   │   ├── logs.sh                    # Log retrieval
│   │   └── ...
│   │
│   ├── runner/                        # 🖥️ Host runner state
│   │   ├── host-runner.pid            # Process ID file
│   │   └── host-runner.log            # Runtime logs
│   │
│   └── build/                         # 🔨 Build outputs/reports
│       ├── action-duplicates.json     # Duplicate action report
│       ├── action-summary.json        # Action summary
│       └── ...
│
├── examples/                          # 📚 Reference/example structure
│   └── storage/                       # Reference layout (same as production storage/)
│       ├── templates/
│       │   ├── actions/
│       │   ├── host-actions/
│       │   └── users/
│       ├── config/
│       │   ├── bot/
│       │   └── host/
│       └── scripts/
│
├── src/                               # 💻 Source code
│   ├── bot/                           # Bot service
│   │   ├── bot_service/
│   │   │   ├── bot.py
│   │   │   ├── engine.py
│   │   │   ├── host_client.py         # Host communication
│   │   │   ├── host_loader.py         # Configuration loading
│   │   │   ├── event_args.py
│   │   │   ├── presentation.py
│   │   │   ├── reply_format.py
│   │   │   ├── result.py
│   │   │   └── actions/
│   │   │
│   │   ├── tests/
│   │   │   ├── test_bot.py
│   │   │   ├── test_engine.py
│   │   │   ├── test_host_client.py
│   │   │   ├── test_host_loader.py
│   │   │   ├── test_presentation.py
│   │   │   └── ...
│   │   │
│   │   ├── main.py                    # Entry point
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   ├── host-runner/                   # Host runner service (runs on host)
│   │   ├── host_runner/
│   │   │   ├── server.py              # Operation execution
│   │   │   ├── config.py              # Configuration parsing
│   │   │   ├── project_root.py        # Path resolution
│   │   │   └── __init__.py
│   │   │
│   │   ├── tests/
│   │   │   └── test_server.py
│   │   │
│   │   ├── main.py                    # Entry point
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   │
│   └── config-builder/                # Configuration builder tool
│       ├── builder/
│       │   ├── cli.py                 # CLI interface
│       │   ├── merge.py               # Merging logic
│       │   ├── io.py                  # File I/O
│       │   ├── project_root.py        # Path handling
│       │   └── __init__.py
│       │
│       ├── tests/
│       │   └── test_*.py
│       │
│       ├── main.py                    # Entry point
│       ├── pyproject.toml
│       ├── README.md
│       └── .python-version
│
├── config/                            # 📋 Docker-compose overrides (optional)
│   ├── actions.example.json
│   ├── actions.example.yaml
│   ├── users.example.json
│   ├── users.example.yaml
│   ├── host-actions.example.yaml
│   └── host-actions.example.json
│
├── tmp/                               # 📦 Temporary build artifacts
│   └── build/
│       ├── action-duplicates.json
│       ├── action-summary.json
│       └── ...
│
├── docker-compose.yaml                # Docker compose configuration
├── Makefile                           # Build automation
├── .env.example                       # Environment template
├── .env                               # Environment configuration (created from .env.example)
├── LICENSE
├── README.md                          # Project README
├── Project-local-paul.code-workspace  # VS Code workspace config
└── .gitignore
```

## Key Directories

### `docs/` – Documentation

Configuration guides and reference materials.

```
docs/
├── README.md                    # Overview and getting started
├── bot-configuration.md         # Bot actions and users
├── host-configuration.md        # Host operations
├── templates-and-build.md       # Template structure and build process
├── priority-overrides.md        # Timeout and override precedence
└── folder-layout.md             # This file
```

### `storage/` – Production Configuration

Main deployment configuration (created from templates).

```
storage/
├── templates/                   # Input templates (hand-edited)
│   ├── actions/                 # Action templates
│   ├── host-actions/            # Host operation templates
│   └── users/                   # User templates
├── config/                      # Generated configurations (auto-generated)
│   ├── bot/
│   │   ├── actions.yaml        # Generated from templates/actions/*
│   │   └── users.yaml          # Generated from templates/users/*
│   └── host/
│       └── host-actions.yaml   # Generated from templates/host-actions/*
├── scripts/                     # Helper shell scripts (hand-edited)
├── runner/                      # Runtime state
└── build/                       # Build reports
```

### `examples/storage/` – Reference Example

Reference copy of production storage structure for documentation.

```
examples/storage/
├── templates/                   # Example templates
│   ├── actions/                 # Example actions
│   ├── host-actions/            # Example operations
│   └── users/                   # Example users
├── config/                      # Example generated configs
│   ├── bot/
│   │   ├── actions.yaml
│   │   └── users.yaml
│   └── host/
│       └── host-actions.yaml
└── scripts/                     # Example scripts
```

### `src/` – Source Code

Python source code for bot, host-runner, and config-builder.

```
src/
├── bot/                         # Bot service (Telegram bot)
├── host-runner/                 # Host runner (executes operations)
└── config-builder/              # Configuration builder tool
```

### `tmp/build/` – Build Artifacts

Temporary files generated during build:

```
tmp/build/
├── action-duplicates.json       # Report of duplicate actions
├── action-summary.json          # Summary of all actions
├── host-action-duplicates.json  # Duplicate host operations
└── host-action-summary.json     # Host operations summary
```

## Template to Generated Mapping

### Bot Actions

| Templates | Generated | Command |
|-----------|-----------|---------|
| `storage/templates/actions/*.{yaml,yml,json}` | `storage/config/bot/actions.yaml` | `make build-bot-actions` |

### Bot Users

| Templates | Generated | Command |
|-----------|-----------|---------|
| `storage/templates/users/*.{yaml,yml,json}` | `storage/config/bot/users.yaml` | `make build-bot-actions` |

### Host Operations

| Templates | Generated | Command |
|-----------|-----------|---------|
| `storage/templates/host-actions/*.{yaml,yml,json}` | `storage/config/host/host-actions.yaml` | `make build-host-actions` |

## File Types

| Extension | Used For | Example |
|-----------|----------|---------|
| `.yaml` / `.yml` | YAML configuration | `actions-stack.yaml` |
| `.json` | JSON configuration | `users-admin.json` |
| `.sh` | Bash helper scripts | `cf.sh`, `stack.sh` |
| `.py` | Python source code | `bot.py`, `engine.py` |
| `.md` | Documentation | `README.md`, `docs/` |
| `.txt` | Logs and text | `host-runner.log` |

## Workflow

### Typical Configuration Workflow

```
1. Create template file
   └─> storage/templates/actions/my-actions.yaml

2. Define actions/operations/users

3. Build configurations
   └─> make build-actions

4. Verify generated config
   └─> cat storage/config/bot/actions.yaml

5. Reload bot
   └─> /reload_actions (in Telegram)

6. Test
   └─> /my_action (in Telegram)
```

### Git Workflow

**Commit templates, not generated configs:**

```bash
# ✓ DO commit these
git add storage/templates/

# ✓ DO commit these
git add storage/scripts/

# ✗ DON'T commit these (auto-generated)
git add storage/config/         # NO! Generated files

# ✗ DON'T commit these (temporary)
git add tmp/                    # NO! Temporary builds
```

Add to `.gitignore`:

```
storage/config/             # Auto-generated configs
storage/runner/             # Runtime state
tmp/build/                  # Build artifacts
storage/config/             # Generated files
.env                        # Local environment
```

## Directory Permissions

### Scripts Directory

Scripts must be executable:

```bash
chmod +x storage/scripts/*.sh
```

### Config Directory

Configs should be readable by bot container:

```bash
chmod 644 storage/config/bot/*.yaml
chmod 644 storage/config/host/*.yaml
```

### Runner Directory

Runtime state should be writable by host-runner:

```bash
chmod 755 storage/runner/
```

## Environment Configuration

### `.env` File

Contains build configuration and environment variables:

```bash
# From .env.example, create .env
cp .env.example .env

# Edit .env with your settings
vim .env
```

**Common settings:**

```bash
# Docker
COMPOSE_PROJECT_NAME=telegram-bot
TELEGRAM_BOT_TOKEN=your_token_here

# Paths
CONFIG_PATH=./config
DOCKER_SOCKET_PATH=/var/run/docker.sock

# Bot configuration
BOT_HOST_ACTION_SOCKET=/var/run/telegram-bot/host-actions.sock
BOT_HOST_ACTION_ENDPOINT=host.docker.internal:8787

# Build configuration
BOT_ACTIONS_OUTPUT_PATH=storage/config/bot/actions.yaml
HOST_ACTIONS_OUTPUT_PATH=storage/config/host/host-actions.yaml
```

## Related Documentation

- [README](README.md) – Getting started
- [Bot Configuration](bot-configuration.md) – Action template details
- [Host Configuration](host-configuration.md) – Operation template details
- [Templates & Build](templates-and-build.md) – Build process
