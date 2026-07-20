# Priority Overrides and Configuration Precedence

This document explains how priority settings like `timeout_seconds` work across layers.

## Timeout Seconds Override ⭐

The most common override is `timeout_seconds`, which determines how long operations are allowed to run.

### Three Layers of Timeout Control

```
Handler timeout_seconds (Highest Priority)
    ↓ (if not set)
Operation timeout_seconds
    ↓ (if not set)
No timeout (Lowest Priority)
```

### Layer 1: Handler Timeout (Highest Priority)

Handler-level timeout overrides the operation default:

```yaml
# In storage/templates/actions/my-actions.yaml
handlers:
  - id: long_running_task
    target: host
    operation: server.process_data
    timeout_seconds: 300         # ← Handler override (5 minutes)
```

**Effect:** This handler gets 300 seconds regardless of operation timeout.

### Layer 2: Operation Timeout (Fallback)

Operation defines the default timeout:

```yaml
# In storage/templates/host-actions/my-operations.yaml
operations:
  server.process_data:
    command:
      - /bin/bash
      - -lc
      - process_data.sh
    timeout_seconds: 60          # ← Operation default (1 minute)
```

**Effect:** Handlers use this 60 seconds if they don't specify their own.

### Layer 3: No Timeout (Lowest Priority)

If neither is set, operation runs indefinitely (not recommended):

```yaml
operations:
  server.infinite_task:
    command: [...]
    # timeout_seconds: not set  # ← No timeout!
```

## Complete Timeout Example

### Scenario: Multiple actions calling same operation with different needs

#### Operation Definition

```yaml
# storage/templates/host-actions/stack-operations.yaml
operations:
  server.stack_action:
    command:
      - /bin/bash
      - -lc
      - source "$HOST_PROJECT_ROOT/storage/scripts/spiral-stack.sh" && stack_cmd "{{action}}"
    timeout_seconds: 15          # Default timeout
    allow_user_args: false
    allowed_placeholders:
      - action
```

#### Action Definitions

```yaml
# storage/templates/actions/stack-actions.yaml
actions:
  spiral_stack_status:
    allowed_roles:
      - admin
    handlers:
      - id: host.server.spiral_stack_status
        target: host
        operation: server.stack_action
        timeout_seconds: 12      # Override: 12 seconds
        params:
          action: stack-status

  spiral_stack_start:
    allowed_roles:
      - admin
    handlers:
      - id: host.server.spiral_stack_start
        target: host
        operation: server.stack_action
        timeout_seconds: 120     # Override: 120 seconds (2 minutes)
        params:
          action: stack-start

  spiral_stack_stop:
    allowed_roles:
      - admin
    handlers:
      - id: host.server.spiral_stack_stop
        target: host
        operation: server.stack_action
        timeout_seconds: 30      # Override: 30 seconds
        params:
          action: stack-stop

  spiral_stack_help:
    allowed_roles:
      - admin
    handlers:
      - id: host.server.spiral_stack_help
        target: host
        operation: server.stack_action
        # No override: uses operation default of 15 seconds
        params:
          action: help
```

### Effective Timeouts

| Action | Handler Timeout | Operation Timeout | **Effective Timeout** |
|--------|-----------------|-------------------|----------------------|
| spiral_stack_status | 12s | 15s | **12s** (handler wins) |
| spiral_stack_start | 120s | 15s | **120s** (handler wins) |
| spiral_stack_stop | 30s | 15s | **30s** (handler wins) |
| spiral_stack_help | (not set) | 15s | **15s** (operation used) |

## Action-Level Timeout

Set default timeout for all handlers in an action:

```yaml
actions:
  my_complex_action:
    default_timeout_seconds: 60     # ← Default for all handlers
    handlers:
      - id: handler_1
        operation: server.task1
        # Uses action default: 60 seconds
      - id: handler_2
        operation: server.task2
        timeout_seconds: 120        # Override: 120 seconds
```

### Effective Timeouts

| Handler | Handler Timeout | Action Timeout | Operation Timeout | **Effective** |
|---------|-----------------|----------------|-------------------|--------------|
| handler_1 | (not set) | 60s | 15s | **60s** (action used) |
| handler_2 | 120s | 60s | 15s | **120s** (handler wins) |

## Stop on Failure

Control whether to stop on handler failure:

### Handler-Level Override

```yaml
handlers:
  - id: handler_1
    operation: server.task1
    stop_on_failure: true        # Stop if this fails
  - id: handler_2
    operation: server.task2
    stop_on_failure: false       # Continue even if fails
```

### Action-Level Default

```yaml
actions:
  my_action:
    stop_on_failure: true        # Default for all handlers
    handlers:
      - id: handler_1
        operation: server.task1
        # Uses action default: stop on failure
      - id: handler_2
        operation: server.task2
        stop_on_failure: false   # Override: don't stop
```

## Stage-Based Ordering

Stages control execution order; handlers in same stage run in parallel:

```yaml
handlers:
  - id: check_db
    operation: server.check_db
    stage: 0                     # ← Stage 0: runs first
  - id: migrate_db
    operation: server.migrate
    stage: 0                     # ← Stage 0: parallel with check_db
  - id: start_service
    operation: server.start
    stage: 1                     # ← Stage 1: runs after stage 0 completes
```

## Validation and Limits

Host-runner validates timeout values:

| Property | Validation | Notes |
|----------|-----------|-------|
| `timeout_seconds` | Must be > 0 and ≤ 600 | Max 10 minutes |
| (if ≤ 0) | Rejected | Error returned |
| (if > 600) | Rejected | Error returned |

Set `timeout_seconds: null` to disable timeout validation.

## Best Practices

1. **Set operation defaults** – Every operation should have a default timeout
2. **Override only when needed** – Most handlers use operation default
3. **Use action defaults** – For consistency across multiple handlers
4. **Document large overrides** – Add comments explaining why 300+ second timeouts
5. **Test timeout values** – Verify operations complete within timeout

## Examples by Use Case

### Quick Status Check

```yaml
operations:
  server.health_check:
    timeout_seconds: 5           # Quick response expected

handlers:
  - id: health.check
    operation: server.health_check
    # Uses 5 second default
```

### Long-Running Deployment

```yaml
operations:
  server.deploy:
    timeout_seconds: 120         # Default 2 minutes

handlers:
  - id: deploy.prod
    operation: server.deploy
    timeout_seconds: 600         # Override: 10 minutes for production
```

### API Call with Fallback

```yaml
operations:
  server.api_call:
    timeout_seconds: 30

handlers:
  - id: api.fast
    operation: server.api_call
    # Uses 30 seconds
  - id: api.retry
    operation: server.api_call
    timeout_seconds: 60          # Retry gets more time
```

### Parallel Tasks with Different Speeds

```yaml
handlers:
  - id: db_check
    operation: server.check_db
    stage: 0
    timeout_seconds: 10          # Quick check
  - id: file_scan
    operation: server.scan_files
    stage: 0
    timeout_seconds: 60          # Longer scan
  - id: report
    operation: server.generate_report
    stage: 1                      # After both stage 0 complete
    timeout_seconds: 30
```

## Troubleshooting

**Handler timing out at operation timeout:**
- Override handler timeout: `timeout_seconds: 300`
- Or increase operation default: `timeout_seconds: 300`
- Check effective timeout in precedence table above

**Handler completing too slowly:**
- Reduce timeout: `timeout_seconds: 5`
- Optimize underlying script
- Check for network delays

**"timeout_seconds must not exceed 600 seconds":**
- Reduce timeout to ≤ 600 (10 minutes)
- Or check if operation should be split into smaller tasks

## Related Documentation

- [Host Configuration](host-configuration.md) – Operation timeout_seconds field
- [Bot Configuration](bot-configuration.md) – Handler timeout_seconds field
- [Templates & Build](templates-and-build.md) – Building configurations
