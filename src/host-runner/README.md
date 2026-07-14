# Host Runner

This service executes curated host-side operations for the Telegram bot over a Unix domain socket.

## Configuration

```env
HOST_ACTIONS_CONFIG=/absolute/path/to/config/host-actions.yaml
HOST_ACTIONS_SOCKET=/absolute/path/to/shared/host-actions.sock
```

Operation definitions live in `config/host-actions.example.yaml` at the repository root.

## Run

```sh
HOST_ACTIONS_CONFIG="$PWD/../../config/host-actions.example.yaml" \
HOST_ACTIONS_SOCKET="$PWD/../../tmp/host-actions.sock" \
uv run python main.py
```
