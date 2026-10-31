# API Endpoints are generated at startup from config, not code-generated

The HTTP API (`telegram-c2-api`) exposes one `POST /actions/{name}` Endpoint per configured Action. Endpoints are built in memory from `actions.yaml` when the API process starts; there is no generated Python on disk. Changing config means restarting the API (`make build-api`), not editing or regenerating code.

## Considered Options

- **Code generation** (write a routes module from config): rejected because generated files drift from config and need review/commit for every config change.
- **Hot reload of routes** (`POST /reload` swapping routes on a live app): rejected because FastAPI/Starlette do not cleanly support removing routes or refreshing the OpenAPI schema at runtime, and a container restart takes seconds.

## Consequences

- The API has no `/reload_actions` equivalent; `make build-api` is the only way to pick up new Actions. Until then, the Telegram bot (after `/reload_actions`) and the API can briefly disagree on which Actions exist.
- The API runs as a separate container from the same image, so a slow or crashing API cannot stall Telegram polling.
