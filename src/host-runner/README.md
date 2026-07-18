# Host Runner

This service executes curated host-side operations for the Telegram bot over either a Unix domain socket or TCP.

## What It Does

- loads operation definitions from `HOST_ACTIONS_CONFIG`
- validates incoming operation name, params, and optional args
- executes approved commands without invoking a shell
- supports placeholder substitution via `{{name}}` tokens
- supports optional arg allowlists per operation
- can resolve and return `reply_format` based on which optional args are present

## Configuration

```env
HOST_ACTIONS_CONFIG=/absolute/path/to/config/host-actions.yaml
```

or TCP mode:

```env
HOST_ACTIONS_CONFIG=/absolute/path/to/config/host-actions.yaml
HOST_ACTIONS_HOST=0.0.0.0
HOST_ACTIONS_PORT=8787
```

Operation definitions live in `config/host-actions.example.yaml` at the repository root.

## Operation Schema

Each operation supports:

- `command`: non-empty list of command parts
- `timeout_seconds`: optional command timeout
- `allow_user_args`: whether Telegram user args are appended
- `allowed_placeholders`: optional allowlist for substitution keys
- `allowed_optional_params`: optional allowlist for Telegram-provided optional args
- `reply_format`: optional reply format policy

When `allow_user_args` is enabled:

- raw args are validated for size and control characters
- every arg must be present in `allowed_optional_params`
- leading em-dash variants in args are normalized (`—json` becomes `--json`)

Host operations can opt into static param substitution:

- define `allowed_placeholders` as a list of accepted placeholder names
- use `{{placeholder_name}}` tokens inside command parts
- the runner rejects unknown params and unresolved placeholders

Example:

```yaml
operations:
 server.generic_url:
  command:
   - /bin/bash
   - -lc
   - printf '%s\n' "https://{{domain_var}}"
  allowed_placeholders:
   - domain_var
```

## Reply Format Rules

You can define operation-level `reply_format` as either:

- shorthand string, for example `reply_format: json`
- matrix rules keyed by format name with a default fallback

Matrix rule structure:

- `default`: fallback format name
- `<format>.single`: OR match, format is selected if any listed param is present
- `<format>.ands`: list of AND groups, format is selected if all params in any one group are present

Example:

```yaml
operations:
   server.my_action:
      command:
         - /bin/mybin
         - "{{subcmd}}"
      allow_user_args: true
      allowed_placeholders:
         - subcmd
      allowed_optional_params:
         - -a
         - -b
         - -d
         - -e
      reply_format:
         - default: markdown
            json:
               - single:
                     - -d
               - ands:
                     - and:
                           - -a
                           - -b
            text:
               - single:
                     - -e
```

If a command succeeds and `reply_format` is configured, the host runner includes a resolved `reply_format` value in the response to the bot.

## Run With Make

From the project root:

```sh
make start-host-runner
```

To stop it:

```sh
make stop-host-runner
```

To follow its log output:

```sh
make host-runner-logs
```
