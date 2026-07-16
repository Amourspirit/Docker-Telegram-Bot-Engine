# Configurations

This config folder would be mapped as a volume in the docker-compose.yaml file `- /path/to/this/config:/app/config:ro`.

Provide both files for the bot container:

- `users.yaml` (or `users.yml` / `users.json`) with Telegram user roles
- `actions.yaml` (or `actions.yml` / `actions.json`) with action definitions
