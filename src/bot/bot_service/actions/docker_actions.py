from __future__ import annotations

import docker

from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.result import Result


async def status_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = event_args.shared_state.get("docker_client")
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    try:
        containers = docker_client.containers.list(all=True)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    response = "🐳 **Docker Status:**\n\n"
    for container in containers:
        icon = "🟢" if container.status == "running" else "🔴"
        response += f"{icon} `{container.name}` ({container.status})\n"

    return Result.success(response)


async def start_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = event_args.shared_state.get("docker_client")
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    if not event_args.raw_args:
        return Result.success("Please provide a container name. Usage: /start <name>")

    target = event_args.raw_args[0]
    try:
        container = docker_client.containers.get(target)
        container.start()
        return Result.success(f"✅ Container `{target}` started successfully.")
    except docker.errors.NotFound:
        return Result.success(f"❌ Container `{target}` not found.")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


def register_default_actions(engine: ActionEngine) -> None:
    engine.register_handler(
        action_name="status",
        handler_id="docker.status.containers",
        callback=status_handler,
        stage=0,
    )
    engine.register_handler(
        action_name="start",
        handler_id="docker.start.container",
        callback=start_handler,
        stage=0,
    )
