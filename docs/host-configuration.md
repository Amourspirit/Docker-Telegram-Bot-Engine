# Host Configuration Guide

This document explains how to configure host operations that execute commands on the host system.

## Overview

Host operations are defined in `storage/templates/host-actions/` and merged into `storage/config/host/host-actions.yaml`.

Host operations execute shell commands on the host machine and return results to the bot.

## Creating Host Operation Templates

Host operations are defined with YAML, YML, or JSON format in `storage/templates/host-actions/`.

### Basic Operation Example

```yaml
operations:
  server.status:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/helpers.sh" && get_status
    timeout_seconds: 10
    allow_user_args: false
    allowed_placeholders: []
```

### Operation Properties

| Property | Type | Description |
|----------|------|-------------|
| `command` | list | Shell command parts (never shell expansion) |
| `timeout_seconds` | number | Default operation timeout in seconds |
| `allow_user_args` | boolean | Allow user-supplied CLI arguments |
| `allowed_placeholders` | list | Parameter names allowed in command |
| `allowed_optional_params` | list | Optional parameters if `allow_user_args: true` |
| `reply_format` | object | Response format rules |

## Commands

Commands are specified as arrays (no shell expansion):

```yaml
# ✓ Correct - array format
command:
  - /bin/bash
  - -lc
  - echo "Hello"

# ✗ Avoid - single string (won't work)
command: "echo Hello"
```

**Why arrays?** Direct subprocess execution bypasses shell expansion, avoiding injection attacks. The `-lc` flag runs as login shell for sourcing scripts.

### Sourcing Helper Scripts

```yaml
command:
  - /bin/bash
  - -lc
  - source "$HOST_PROJECT_ROOT/storage/scripts/cf.sh" && cf_cmd "{{domain}}"
```

Helper scripts should be in `storage/scripts/` and sourced before execution.

## Parameters and Placeholders

Parameters allow dynamic values injected at runtime.

### Using Placeholders

```yaml
operations:
  server.cf_action:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/cf.sh" && cf_cmd "{{domain}}" "{{action}}"
    timeout_seconds: 15
    allow_user_args: false
    allowed_placeholders:
      - domain
      - action
```

### In Bot Action Handler

```yaml
handlers:
  - id: cf_status
    target: host
    operation: server.cf_action
    params:
      domain: $CF_MY_DOMAIN    # Environment variable
      action: status           # Literal value
```

### Parameter Expansion

Parameters support:
- **Environment variables**: `$VAR_NAME` → expands to environment value
- **Home directory**: `~/path` → expands to `/home/user/path`
- **Literal values**: `literal_string` → used as-is

```yaml
params:
  domain: $MY_DOMAIN           # ← From environment
  config_path: ~/app/config    # ← From home directory
  action: deploy               # ← Literal value
```

## User Arguments

Allow users to pass command-line arguments:

```yaml
operations:
  server.run_script:
    command:
      - /bin/bash
      - -lc
      - ./script.sh
    timeout_seconds: 30
    allow_user_args: true
    allowed_optional_params:
      - --verbose
      - --dry-run
      - --env
```

Then in Telegram:
```
/my_action --verbose --dry-run
```

The arguments are validated before execution.

## Timeout Control

### Operation Default Timeout

```yaml
operations:
  server.quick_task:
    timeout_seconds: 5
  server.long_task:
    timeout_seconds: 300      # 5 minutes
```

### Handler Override ⭐

Handler timeout overrides the operation timeout:

```yaml
# In host-actions.yaml
operations:
  server.long_task:
    timeout_seconds: 15       # Default

# In actions.yaml
handlers:
  - id: long_operation
    operation: server.long_task
    timeout_seconds: 300      # Override to 5 minutes
```

**Precedence:**
1. Handler `timeout_seconds` (highest)
2. Operation `timeout_seconds` (fallback)
3. No timeout (lowest)

See [Priority Overrides](priority-overrides.md) for details.

## Response Formatting

Control how command output is formatted:

```yaml
operations:
  server.get_status:
    reply_format: markdown
    
  server.get_json:
    reply_format: json
```

Or use conditional rules:

```yaml
operations:
  server.complex:
    reply_format:
      default: markdown
      rules:
        - format_name: json
          singles:
            - --json              # Use JSON if --json present
        - format_name: plain_text
          and_groups:
            - [--plain, --lines]  # Use plain text if both --plain AND --lines
```

## Complete Example

### Template: `storage/templates/host-actions/cloudflare.yaml`

```yaml
operations:
  server.cf_domain_check:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/cf.sh" && cf_check_domain "{{domain}}"
    timeout_seconds: 10
    allow_user_args: false
    allowed_placeholders:
      - domain
  
  server.cf_dns_update:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/cf.sh" && cf_update_dns "{{domain}}" "{{record}}"
    timeout_seconds: 30
    allow_user_args: false
    allowed_placeholders:
      - domain
      - record
    reply_format:
      default: json
```

### Template: `storage/templates/actions/cloudflare-actions.yaml`

```yaml
actions:
  cf_check_domain:
    allowed_roles:
      - admin
    handlers:
      - id: host.cf.check
        target: host
        operation: server.cf_domain_check
        timeout_seconds: 15         # Override operation's 10s to 15s
        params:
          domain: $CF_DOMAIN
  
  cf_update_dns:
    allowed_roles:
      - admin
    handlers:
      - id: host.cf.update
        target: host
        operation: server.cf_dns_update
        timeout_seconds: 60         # Override operation's 30s to 60s
        params:
          domain: $CF_DOMAIN
          record: "www"
```

### Helper Script: `storage/scripts/cf.sh`

```bash
#!/bin/bash

cf_check_domain() {
    local domain="$1"
    echo "Checking domain: $domain"
    # Call Cloudflare API...
}

cf_update_dns() {
    local domain="$1"
    local record="$2"
    echo "Updating $record.$domain"
    # Call Cloudflare API...
}
```

## Security Considerations

1. **Validate placeholders** – List all allowed placeholders explicitly
2. **Restrict user args** – Only allow specific optional parameters
3. **Timeout limits** – Host-runner validates max timeout is ≤600 seconds
4. **Script permissions** – Make helper scripts executable: `chmod +x script.sh`
5. **Environment variables** – Only safe, non-sensitive values in templates

## Environment Variables

Access environment variables in operations:

```yaml
command:
  - /bin/bash
  - -lc
  - echo "Host: $HOSTNAME, User: $USER"
```

Set in `.env` file for docker-compose or export in shell:

```bash
export HOST_PROJECT_ROOT=/path/to/project
export MY_DOMAIN=example.com
```

## Troubleshooting

**Operation timeout exceeded:**
- Increase `timeout_seconds` in operation definition
- Or override in handler: `timeout_seconds: 120`
- See [Priority Overrides](priority-overrides.md)

**Command not found:**
- Verify script path includes `$HOST_PROJECT_ROOT`
- Ensure script is executable: `chmod +x script.sh`
- Check PATH in bash `-lc` login shell

**Placeholder not substituted:**
- Verify placeholder is in `allowed_placeholders`
- Check placeholder syntax: `{{name}}` (not `$name`)
- Confirm handler provides value in `params`

**Output truncated:**
- Default max output is 4000 characters
- Long outputs are truncated with `...`

## Related Documentation

- [Bot Configuration](bot-configuration.md) – Configure bot actions
- [Priority Overrides](priority-overrides.md) – Timeout and precedence rules
- [Templates & Build](templates-and-build.md) – Building configurations
