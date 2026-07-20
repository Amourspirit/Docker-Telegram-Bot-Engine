# Templates and Build Process

This document explains how to organize templates and build final configurations.

## Overview

The build system uses **config-builder** to merge multiple template files into consolidated configuration:

```
Templates (multiple files)
    ↓
config-builder merges
    ↓
Generated Config (single file)
```

## Template Structure

### Directory Layout

```
storage/
├── templates/
│   ├── actions/               # Bot action templates
│   │   ├── actions-stack.yaml
│   │   ├── actions-cf.yaml
│   │   ├── actions-logs.yaml
│   │   └── ...
│   │
│   ├── host-actions/          # Host operation templates
│   │   ├── host-actions-stack.yaml
│   │   ├── host-actions-cf.yaml
│   │   └── ...
│   │
│   └── users/                 # User templates
│       ├── admin-users.yaml
│       ├── team-users.yaml
│       └── ...
│
├── config/                    # Generated configs (auto-generated)
│   ├── bot/
│   │   ├── actions.yaml      # ⚙️ Generated from storage/templates/actions/*
│   │   └── users.yaml        # ⚙️ Generated from storage/templates/users/*
│   │
│   └── host/
│       └── host-actions.yaml # ⚙️ Generated from storage/templates/host-actions/*
│
└── scripts/                   # Helper scripts (not generated)
    ├── cf.sh
    ├── stack.sh
    └── ...
```

## File Organization Best Practices

### 1. One Feature Per File

```
storage/templates/actions/
├── actions-stack.yaml        # Stack operations
├── actions-cf.yaml           # Cloudflare operations
├── actions-logs.yaml         # Log viewing
├── actions-deployment.yaml   # Deployment operations
└── actions-monitoring.yaml   # Monitoring operations
```

Benefits:
- Easy to find related actions
- Simple to add/remove features
- Reduces merge conflicts
- Clear organization

### 2. Logical Grouping by Operation

```
storage/templates/host-actions/
├── host-actions-stack.yaml   # Stack management operations
├── host-actions-cf.yaml      # Cloudflare API operations
├── host-actions-logs.yaml    # Log retrieval operations
└── host-actions-docker.yaml  # Docker operations
```

### 3. Role-Based User Organization

```
storage/templates/users/
├── admin-users.yaml          # Admin role
├── team-devops-users.yaml    # DevOps team
├── team-infra-users.yaml     # Infrastructure team
└── team-qa-users.yaml        # QA team
```

## Supported File Formats

All files support YAML, YML, or JSON:

```
✓ actions-myfeature.yaml
✓ actions-myfeature.yml
✓ actions-myfeature.json
✓ host-actions-stack.yaml
✓ host-actions-stack.json
✓ users-admin.yaml
```

## Configuration Settings

Build behavior is configured in `.env` file:

### Bot Actions Build Settings

```bash
# Input template directory and glob pattern
BOT_ACTIONS_INPUT_DIR=storage/templates/actions
BOT_ACTIONS_INPUT_GLOB=${BOT_ACTIONS_INPUT_DIR}/*.{json,yaml,yml}

# Output merged configuration
BOT_ACTIONS_OUTPUT_PATH=storage/config/bot/actions.yaml

# Reports (for debugging)
BOT_ACTIONS_DUPLICATES_REPORT=tmp/build/action-duplicates.json
BOT_ACTIONS_SUMMARY_JSON=tmp/build/action-summary.json
```

### Host Actions Build Settings

```bash
# Input template directory and glob pattern
HOST_ACTIONS_INPUT_DIR=storage/templates/host-actions
HOST_ACTIONS_INPUT_GLOB=${HOST_ACTIONS_INPUT_DIR}/*.{json,yaml,yml}

# Output merged configuration
HOST_ACTIONS_OUTPUT_PATH=storage/config/host/host-actions.yaml

# Reports (for debugging)
HOST_ACTIONS_DUPLICATES_REPORT=tmp/build/host-action-duplicates.json
HOST_ACTIONS_SUMMARY_JSON=tmp/build/host-action-summary.json
```

### Base Directory

```bash
# Base directory for relative paths
ACTIONS_BASE_DIR=../..
```

## Building Configurations

### Build Bot Actions Only

```bash
make build-bot-actions
```

Merges:
- `storage/templates/actions/*.{yaml,yml,json}` → `storage/config/bot/actions.yaml`
- `storage/templates/users/*.{yaml,yml,json}` → `storage/config/bot/users.yaml`

### Build Host Actions Only

```bash
make build-host-actions
```

Merges:
- `storage/templates/host-actions/*.{yaml,yml,json}` → `storage/config/host/host-actions.yaml`

### Build Everything

```bash
make build-actions
```

Runs both bot and host actions builds.

## Build Process

### 1. File Discovery

Config-builder finds all matching files:

```
Input: storage/templates/actions/*.{yaml,yml,json}
Found:
  - actions-stack.yaml
  - actions-cf.yaml
  - actions-logs.json
  - actions-monitoring.yaml
```

### 2. Parse Each File

Each file is parsed and validated:

```
✓ actions-stack.yaml - 4 actions found
✓ actions-cf.yaml - 6 actions found
✓ actions-logs.json - 2 actions found
✗ actions-monitoring.yaml - ERROR: duplicate action 'monitor'
```

### 3. Merge Templates

Merge all templates into single structure:

```yaml
# Result: storage/config/bot/actions.yaml
actions:
  spiral_stack_status: ...    # from actions-stack.yaml
  spiral_stack_start: ...     # from actions-stack.yaml
  cf_arcane_status: ...       # from actions-cf.yaml
  cf_arcane_enable: ...       # from actions-cf.yaml
  view_logs: ...              # from actions-logs.json
  ...
```

### 4. Validate and Report

Generate reports if errors found:

```
Report: tmp/build/action-duplicates.json
Report: tmp/build/action-summary.json
```

Check reports for:
- Duplicate action names
- Invalid configuration syntax
- Missing required fields

## Handling Duplicates

If multiple templates define same action, build fails:

```yaml
# actions-stack.yaml
actions:
  my_status: ...

# actions-logs.yaml  
actions:
  my_status: ...    # ← DUPLICATE! Build fails
```

**Resolution:** Rename one action or consolidate into single file.

## Template Examples

### Example 1: Simple Bot Action

**File:** `storage/templates/actions/simple-actions.yaml`

```yaml
actions:
  hello_world:
    stop_on_failure: true
    allowed_roles:
      - admin
    handlers:
      - id: host.hello
        target: host
        operation: server.hello
        stage: 0
```

### Example 2: Complex Action with Multiple Handlers

**File:** `storage/templates/actions/deployment.yaml`

```yaml
actions:
  deploy_app:
    stop_on_failure: true
    allowed_roles:
      - admin
      - deploy_user
    tags:
      - deployment
    default_timeout_seconds: 30
    handlers:
      - id: check_ready
        target: host
        operation: server.check
        stage: 0
        timeout_seconds: 10
      - id: backup_db
        target: host
        operation: server.backup
        stage: 1
        timeout_seconds: 60
      - id: run_deploy
        target: host
        operation: server.deploy
        stage: 1
        timeout_seconds: 300
```

### Example 3: Host Operations

**File:** `storage/templates/host-actions/monitoring.yaml`

```yaml
operations:
  server.health:
    command:
      - /bin/bash
      - -lc
      - echo "OK"
    timeout_seconds: 5
  
  server.metrics:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/metrics.sh" && get_metrics
    timeout_seconds: 15
```

### Example 4: Users

**File:** `storage/templates/users/team-a.yaml`

```yaml
users:
  "1234567890":
    name: "Alice"
    roles:
      - admin
  "1111111111":
    name: "Bob"
    roles:
      - deploy_user
```

## Adding New Templates

### Step 1: Create Template File

```bash
# New action template
touch storage/templates/actions/actions-myfeature.yaml

# New host operation template
touch storage/templates/host-actions/host-actions-myfeature.yaml

# New users template
touch storage/templates/users/myteam-users.yaml
```

### Step 2: Define Content

Edit the new template file with your actions/operations/users.

### Step 3: Build

```bash
make build-actions
```

### Step 4: Verify

Check generated configuration:

```bash
cat storage/config/bot/actions.yaml      # Verify actions
cat storage/config/host/host-actions.yaml # Verify operations
```

### Step 5: Reload Bot

In Telegram with admin role:

```
/reload_actions
```

## Debugging Builds

### Check Build Logs

```bash
# Verbose output
make build-actions 2>&1 | tee build.log

# Check for errors
grep -i error build.log
```

### Inspect Generated Config

```bash
# View generated actions
cat storage/config/bot/actions.yaml | head -50

# View generated host operations
cat storage/config/host/host-actions.yaml | head -50

# Validate YAML syntax
yamllint storage/config/bot/actions.yaml
yamllint storage/config/host/host-actions.yaml
```

### Check Reports

```bash
# View duplicates report
cat tmp/build/action-duplicates.json | jq .

# View summary
cat tmp/build/action-summary.json | jq .
```

## Environment Variable Expansion

Template values can use environment variables:

```yaml
handlers:
  - operation: server.my_op
    params:
      domain: $MY_DOMAIN         # Expands at template build time
      path: ~/config             # ~ expands to home directory
```

Set in `.env`:

```bash
MY_DOMAIN=example.com
```

## Best Practices

1. **One feature per file** – `actions-featurename.yaml`
2. **Consistent naming** – Use lowercase with hyphens: `actions-my-feature.yaml`
3. **Descriptive comments** – Explain complex configurations
4. **Validate before committing** – Run `make build-actions`
5. **Small incremental changes** – Easier to debug if build fails
6. **Keep templates simple** – Complex logic belongs in host scripts
7. **Version control** – Commit templates, not generated configs
8. **Document dependencies** – Note which templates depend on scripts

## Related Documentation

- [Bot Configuration](bot-configuration.md) – Action template details
- [Host Configuration](host-configuration.md) – Host operation template details
- [Priority Overrides](priority-overrides.md) – Timeout precedence
- [README](README.md) – Getting started guide
