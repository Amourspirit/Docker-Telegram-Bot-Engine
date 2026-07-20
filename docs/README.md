# Telegram Bot Configuration Guide

This guide explains how to configure the telegram-bot project with custom bot actions, host operations, and user access controls.

## Quick Overview

The telegram-bot uses a **template-based configuration system** that generates two main configuration files:

- **`actions.yaml`** – Defines bot commands/actions and user permissions
- **`host-actions.yaml`** – Defines host operations executed by the bot

The configuration system consists of:

1. **Templates** – Individual YAML/JSON files defining actions, host operations, and users
2. **Config-Builder** – Merges templates into final configuration files
3. **Make Commands** – Convenience commands to build configurations

## Architecture

```
Project Root
├── storage/                          # Production configuration (production layout)
│   ├── templates/
│   │   ├── actions/                 # Bot action templates
│   │   ├── host-actions/            # Host operation templates
│   │   └── users/                   # User role templates
│   ├── config/
│   │   ├── bot/
│   │   │   ├── actions.yaml         # ⚙️ Generated: Bot actions
│   │   │   └── users.yaml           # ⚙️ Generated: User roles
│   │   └── host/
│   │       └── host-actions.yaml    # ⚙️ Generated: Host operations
│   └── scripts/                     # Helper scripts for host operations
│
├── examples/storage/                # Example reference structure
│   ├── templates/                   # Example templates
│   ├── config/                      # Example generated configs
│   └── scripts/                     # Example scripts
│
└── config-builder/                  # Tool to merge templates into configs
```

## Getting Started

### 1. Initialize Your Configuration

Start with the example structure:

```bash
# Copy example storage to production storage
cp -r examples/storage/templates storage/
cp -r examples/storage/scripts storage/
mkdir -p storage/config/{bot,host}
```

### 2. Create Your First Templates

Create template files in `storage/templates/`:

**Bot Actions** (`storage/templates/actions/my-actions.yaml`):
```yaml
actions:
  my_status:
    stop_on_failure: true
    allowed_roles:
      - admin
    handlers:
      - id: host.my.status
        target: host
        operation: server.my_operation
        timeout_seconds: 10
        stage: 0
```

**Host Operations** (`storage/templates/host-actions/my-operations.yaml`):
```yaml
operations:
  server.my_operation:
    command:
      - /bin/bash
      - -lc
      - echo "Hello from host"
    timeout_seconds: 15
    allow_user_args: false
    allowed_placeholders: []
```

**Users** (`storage/templates/users/my-users.yaml`):
```yaml
users:
  "1234567890":
    roles:
      - admin
```

### 3. Build Configurations

```bash
# Build bot actions and users
make build-bot-actions

# Build host operations
make build-host-actions

# Build both
make build-actions
```

### 4. Verify Generated Files

After building, check the generated configurations:

- `storage/config/bot/actions.yaml` – Merged bot actions
- `storage/config/bot/users.yaml` – Merged user roles
- `storage/config/host/host-actions.yaml` – Merged host operations

## Key Concepts

### Handler Timeout Override ⭐

Handler `timeout_seconds` overrides the operation's default timeout:

```yaml
# In actions template
handlers:
  - id: my_handler
    operation: server.long_task
    timeout_seconds: 120      # ← Override operation's default 15s
    
# In host-actions template
operations:
  server.long_task:
    timeout_seconds: 15       # Default (if handler doesn't override)
```

**Precedence:**
1. Handler `timeout_seconds` (highest priority)
2. Operation `timeout_seconds` (fallback)
3. No timeout (lowest priority)

See [Priority Overrides](priority-overrides.md) for complete details.

### Action Stages

Actions can have multiple handler stages that execute sequentially:

```yaml
handlers:
  - id: handler_1
    stage: 0        # Runs first
  - id: handler_2
    stage: 0        # Runs in parallel with handler_1
  - id: handler_3
    stage: 1        # Runs after stage 0 completes
```

### User Roles

Roles control action access:

```yaml
# In users template
users:
  "123456":
    roles:
      - admin
      - operator

# In actions template
actions:
  restricted_action:
    allowed_roles:
      - admin        # Only admin users can execute
```

## Configuration File Formats

All templates support YAML, YML, or JSON:

- `my-actions.yaml` ✓
- `my-actions.yml` ✓
- `my-actions.json` ✓

The builder automatically merges all files in the template directories.

## Next Steps

- 📖 [Bot Configuration](bot-configuration.md) – Detailed actions and users setup
- 🖥️ [Host Configuration](host-configuration.md) – Host operations and scripts
- 🏗️ [Templates & Build](templates-and-build.md) – Template structure and building
- ⏱️ [Priority Overrides](priority-overrides.md) – Timeout and other priority settings
- 📁 [Folder Layout](folder-layout.md) – Complete directory structure

## Common Tasks

### Add a New Action

1. Create `storage/templates/actions/my-feature.yaml`
2. Define actions and handlers
3. Run `make build-bot-actions`
4. Reload bot: `/reload_actions` (in Telegram)

### Override a Timeout

1. Edit the template action or operation
2. Add/modify `timeout_seconds` field
3. Run `make build-actions`
4. Changes take effect on reload

### Add New Users

1. Create `storage/templates/users/team-users.yaml`
2. Add user IDs and roles
3. Run `make build-bot-actions`
4. Reload bot: `/reload_actions`

### Environment Variables

Template values can use environment variables:

```yaml
handlers:
  - operation: server.my_op
    params:
      domain: $MY_DOMAIN       # Expanded at runtime
      path: ~/data             # ~ expands to home directory
```

## Troubleshooting

**Templates not merging?**
- Check glob patterns in `.env`
- Verify template files have `.yaml`, `.yml`, or `.json` extension
- Run `make build-actions` with verbose output

**Action not appearing?**
- Verify `allowed_roles` is set
- Check user has required role in `users.yaml`
- Reload bot with `/reload_actions`

**Timeout not working?**
- Handler timeout overrides operation timeout
- Check both values: `handler.timeout_seconds` and `operation.timeout_seconds`
- See [Priority Overrides](priority-overrides.md) for precedence rules

## Files Organization

See the [Folder Layout](folder-layout.md) guide for complete directory structure and file descriptions.
