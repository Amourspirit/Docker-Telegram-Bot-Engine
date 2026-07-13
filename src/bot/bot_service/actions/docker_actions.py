from __future__ import annotations

import docker

from bot_service.engine import ActionEngine
from bot_service.event_args import EventArgs
from bot_service.result import Result


def _get_docker_client(event_args: EventArgs):
    docker_client = event_args.shared_state.get("docker_client")
    if docker_client is None:
        return None
    return docker_client


async def status_collect_handler(event_args: EventArgs) -> Result[str | None, BaseException | None]:
    docker_client = _get_docker_client(event_args)
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    try:
        containers = docker_client.containers.list(all=True)
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)

    running_count = len([c for c in containers if c.status == "running"])
    stopped_count = len(containers) - running_count

    event_args.shared_state["docker_containers"] = containers
    event_args.shared_state["docker_summary"] = {
        "total": len(containers),
        "running": running_count,
        "stopped": stopped_count,
    }

    return Result.success(None)


async def status_render_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    containers = event_args.shared_state.get("docker_containers")
    summary = event_args.shared_state.get("docker_summary")
    if containers is None or summary is None:
        return Result.failure(RuntimeError("Docker status data not available"))

    response = (
        "🐳 **Docker Status**\n"
        f"Total: {summary['total']} | Running: {summary['running']} | Stopped: {summary['stopped']}\n\n"
    )
    for container in containers:
        icon = "🟢" if container.status == "running" else "🔴"
        response += f"{icon} `{container.name}` ({container.status})\n"

    return Result.success(response)


async def status_runtime_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    handlers_completed = len(event_args.results)
    response = (
        "🧩 **Action Engine**\n"
        f"Action: `{event_args.action_name}`\n"
        f"Correlation ID: `{event_args.correlation_id}`\n"
        f"Handlers completed: `{handlers_completed}`"
    )
    return Result.success(response)


async def start_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = _get_docker_client(event_args)
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


async def stop_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = _get_docker_client(event_args)
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    if not event_args.raw_args:
        return Result.success("Please provide a container name. Usage: /stop <name>")

    target = event_args.raw_args[0]
    try:
        container = docker_client.containers.get(target)
        container.stop()
        return Result.success(f"🛑 Container `{target}` stopped successfully.")
    except docker.errors.NotFound:
        return Result.success(f"❌ Container `{target}` not found.")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


async def restart_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = _get_docker_client(event_args)
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    if not event_args.raw_args:
        return Result.success("Please provide a container name. Usage: /restart <name>")

    target = event_args.raw_args[0]
    try:
        container = docker_client.containers.get(target)
        container.restart()
        return Result.success(f"🔄 Container `{target}` restarted successfully.")
    except docker.errors.NotFound:
        return Result.success(f"❌ Container `{target}` not found.")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


async def logs_handler(event_args: EventArgs) -> Result[str, BaseException | None]:
    docker_client = _get_docker_client(event_args)
    if docker_client is None:
        return Result.failure(RuntimeError("Docker client not available"))

    if not event_args.raw_args:
        return Result.success("Please provide a container name. Usage: /logs <name> [tail]")

    target = event_args.raw_args[0]
    tail = 100
    if len(event_args.raw_args) > 1:
        try:
            tail = max(1, min(500, int(event_args.raw_args[1])))
        except ValueError:
            return Result.success("Tail value must be a number. Usage: /logs <name> [tail]")

    try:
        container = docker_client.containers.get(target)
        raw_logs = container.logs(tail=tail)
        rendered_logs = raw_logs.decode("utf-8", errors="replace").strip()
        if not rendered_logs:
            rendered_logs = "(no logs available)"

        response = (
            f"📜 **Logs for `{target}`** (tail={tail})\n\n"
            f"```\n{rendered_logs}\n```"
        )
        return Result.success(response)
    except docker.errors.NotFound:
        return Result.success(f"❌ Container `{target}` not found.")
    except Exception as exc:  # noqa: BLE001
        return Result.failure(exc)


def register_default_actions(engine: ActionEngine) -> None:
    engine.register_handler(
        action_name="status",
        handler_id="docker.status.collect",
        callback=status_collect_handler,
        stage=0,
    )
    engine.register_handler(
        action_name="status",
        handler_id="docker.status.render",
        callback=status_render_handler,
        stage=1,
    )
    engine.register_handler(
        action_name="status",
        handler_id="engine.status.runtime",
        callback=status_runtime_handler,
        stage=2,
        stop_on_failure=False,
    )
    engine.register_handler(
        action_name="start",
        handler_id="docker.start.container",
        callback=start_handler,
        stage=0,
    )
    engine.register_handler(
        action_name="stop",
        handler_id="docker.stop.container",
        callback=stop_handler,
        stage=0,
    )
    engine.register_handler(
        action_name="restart",
        handler_id="docker.restart.container",
        callback=restart_handler,
        stage=0,
    )
    engine.register_handler(
        action_name="logs",
        handler_id="docker.logs.container",
        callback=logs_handler,
        stage=0,
    )
