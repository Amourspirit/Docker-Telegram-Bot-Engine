# Host Runner

This service executes curated host-side operations for the Telegram bot over either a Unix domain socket or TCP.

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
