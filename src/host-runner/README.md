# Host Runner

This service executes curated host-side operations for the Telegram bot over either a Unix domain socket or TCP.

## Configuration

```env
HOST_ACTIONS_CONFIG=/absolute/path/to/config/host-actions.yaml
HOST_ACTIONS_SOCKET=/absolute/path/to/shared/host-actions.sock
```

or TCP mode:

```env
HOST_ACTIONS_CONFIG=/absolute/path/to/config/host-actions.yaml
HOST_ACTIONS_HOST=0.0.0.0
HOST_ACTIONS_PORT=8787
```

Operation definitions live in `config/host-actions.example.yaml` at the repository root.

## Run

```sh
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_SOCKET="$PWD/../../tmp/host-actions.sock" \
uv run python main.py
```

Run (TCP mode, recommended on Docker Desktop macOS):

```sh
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_HOST=0.0.0.0 \
HOST_ACTIONS_PORT=8787 \
uv run python main.py
```
