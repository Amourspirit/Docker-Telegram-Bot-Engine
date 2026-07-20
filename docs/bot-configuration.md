# Bot Configuration Guide

This document explains how to configure bot actions and user access control.

## Overview

Bot configuration consists of two files:

1. **`storage/config/bot/actions.yaml`** – Defines bot commands/actions and handlers
2. **`storage/config/bot/users.yaml`** – Maps Telegram user IDs to roles

Both are **auto-generated** from templates in `storage/templates/`.

## Creating Action Templates

Actions are defined in `storage/templates/actions/` with YAML, YML, or JSON format.

### Basic Action Example

```yaml
actions:
  my_status:
    stop_on_failure: true
    allowed_roles:
      - admin
    tags:
      - monitoring
      - status
    handlers:
      - id: host.my.status
        target: host
        operation: server.status_cmd
        stage: 0
        timeout_seconds: 10
    reply_format:
      format: markdown
      fenced: true
      fence_lang: text
```

### Action Properties

| Property | Type | Description |
|----------|------|-------------|
| `stop_on_failure` | boolean | Stop execution if a handler fails (default: `true`) |
| `default_timeout_seconds` | number | Timeout for all handlers (can be overridden per-handler) |
| `allowed_roles` | list | Roles required to execute this action (empty = denied by default) |
| `tags` | list | Tags for organizing/filtering actions |
| `aliases` | list | Alternative command names for this action |
| `handlers` | list | Handler configurations (see below) |
| `reply_format` | object | How to format handler responses |
| `unregister` | list | Handler IDs to remove from this action |

### Handlers

Handlers define what runs when an action is executed. They can target local Python functions or remote host operations.

#### Local Handler Example

```yaml
handlers:
  - id: local.my_handler
    target: local
    module: my_module
    callable: my_function
    stage: 0
    stop_on_failure: true
```

#### Host Operation Handler Example

```yaml
handlers:
  - id: host.my.operation
    target: host
    operation: server.my_operation
    params:
      domain: $MY_DOMAIN
      action: status
    stage: 0
    timeout_seconds: 120      # ← Override operation timeout
```

### Handler Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique handler identifier |
| `target` | string | `local` or `host` |
| `operation` (host) | string | Name of host operation to call |
| `module` (local) | string | Python module name |
| `callable` (local) | string | Python function name |
| `params` | object | Parameters to pass to operation |
| `stage` | number | Execution stage (0, 1, 2...) |
| `stop_on_failure` | boolean | Stop if this handler fails |
| `timeout_seconds` | number | Handler timeout (overrides operation default) |

### Multi-Stage Handlers

Stage 0 handlers run in parallel. Stage 1 handlers run after stage 0 completes:

```yaml
handlers:
  - id: check_db
    operation: server.check_db
    stage: 0              # Runs first, in parallel with migrate_db
  - id: migrate_db
    operation: server.migrate
    stage: 0              # Runs first, in parallel with check_db
  - id: start_service
    operation: server.start
    stage: 1              # Runs second, after stage 0 completes
```

### Response Formatting

Control how handler output is formatted for Telegram:

```yaml
reply_format:
  format: markdown        # markdown, plain_text, html
  fenced: true           # Wrap in code fence
  fence_lang: text       # Language for syntax highlighting
```

Or use a conditional format matrix:

```yaml
reply_format:
  default: markdown
  rules:
    - format_name: json
      and_groups:
        - [--json, --verbose]  # Use JSON format if both --json AND --verbose
    - format_name: plain_text
      singles:
        - --plain               # Use plain text if --plain present
```

### Aliases

Provide alternate command names:

```yaml
actions:
  server_restart:
    aliases:
      - server_reboot
      - srv_restart
```

All three commands will trigger the same action:
- `/server_restart`
- `/server_reboot`
- `/srv_restart`

### Tags

Organize actions with tags for filtering:

```yaml
actions:
  deploy_app:
    tags:
      - deployment
      - production
      - app
```

## Creating User Templates

Users are defined in `storage/templates/users/` with YAML, YML, or JSON format.

### User Template Example

```yaml
users:
  "1234567890":          # Telegram user ID (as string)
    name: "Alice"        # Optional display name
    roles:
      - admin
      - operator
  "9876543210":
    name: "Bob"
    roles:
      - operator
  "1111111111":
    name: "Charlie"
    roles:
      - viewer
```

### User Properties

| Property | Type | Description |
|----------|------|-------------|
| Telegram ID | string | Key = user's Telegram ID (required) |
| `name` | string | Optional display name for reference |
| `roles` | list | List of role names assigned to user |

## Roles and Permissions

### Default Roles

The project doesn't define built-in roles—you create them. Common examples:

- `admin` – Full access to all actions
- `operator` – Limited operational access
- `viewer` – Read-only access
- `team_a` – Team-specific access

### Restricting Actions by Role

```yaml
actions:
  dangerous_operation:
    allowed_roles:
      - admin        # Only admin role can execute
  
  status_check:
    allowed_roles:
      - admin
      - operator     # Both admin and operator can execute
  
  public_action:
    allowed_roles: []  # Empty list = denied by default
    # Must explicitly list roles to allow access
```

### Permission Examples

```yaml
# Example 1: Admin-only action
actions:
  restart_service:
    allowed_roles:
      - admin

# Example 2: Team lead + manager access
actions:
  approve_deployment:
    allowed_roles:
      - team_lead
      - manager

# Example 3: No restrictions (all authenticated users)
actions:
  help:
    allowed_roles:
      - ""  # Leave empty to deny, or assign to all users in users.yaml
```

## Complete Example

### Template: `storage/templates/actions/deployment.yaml`

```yaml
actions:
  deploy_staging:
    stop_on_failure: true
    allowed_roles:
      - admin
      - deploy_user
    tags:
      - deployment
      - staging
    default_timeout_seconds: 30
    handlers:
      - id: deploy.check_ready
        target: host
        operation: server.deploy_check
        stage: 0
        timeout_seconds: 15
        params:
          env: staging
      - id: deploy.run
        target: host
        operation: server.deploy_run
        stage: 1              # Runs after check_ready completes
        timeout_seconds: 120
        params:
          env: staging
    reply_format:
      format: markdown
      fenced: true
      fence_lang: yaml
    
  deploy_prod:
    stop_on_failure: true
    allowed_roles:
      - admin
    tags:
      - deployment
      - production
    handlers:
      - id: deploy.confirm
        target: host
        operation: server.deploy_confirm
        stage: 0
        timeout_seconds: 60
```

### Template: `storage/templates/users/deployment-team.yaml`

```yaml
users:
  "1234567890":
    name: "Alice Admin"
    roles:
      - admin
  "1111111111":
    name: "Bob Deploy User"
    roles:
      - deploy_user
```

### Build Generated `storage/config/bot/actions.yaml`

```bash
make build-actions
```

Result: Merged configuration with all templates combined.

## Best Practices

1. **One action per file** – Split complex configurations into logical files
2. **Consistent naming** – Use underscores: `my_action`, `my_handler`
3. **Clear roles** – Create meaningful role names specific to your workflows
4. **Document timeout logic** – Add comments explaining timeout_seconds choices
5. **Use tags** – Organize actions with tags for easy filtering
6. **Test locally** – Build and reload actions before deploying

## Related Documentation

- [Host Configuration](host-configuration.md) – Configure host operations
- [Priority Overrides](priority-overrides.md) – Timeout and precedence rules
- [Templates & Build](templates-and-build.md) – Building configurations
