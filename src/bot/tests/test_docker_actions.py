from __future__ import annotations

import docker

from bot_service.actions.docker_actions import logs_handler, restart_handler
from bot_service.event_args import EventArgs
from bot_service.result import Result


class FakeContainer:
    def __init__(self, name: str, logs: bytes = b"", missing: bool = False) -> None:
        self.name = name
        self._logs = logs
        self._missing = missing
        self.restarted = False

    def restart(self) -> None:
        if self._missing:
            raise docker.errors.NotFound("not found")
        self.restarted = True

    def logs(self, tail: int) -> bytes:  # noqa: ARG002
        if self._missing:
            raise docker.errors.NotFound("not found")
        return self._logs


class FakeContainersAPI:
    def __init__(self, mapping: dict[str, FakeContainer]) -> None:
        self.mapping = mapping

    def get(self, target: str) -> FakeContainer:
        container = self.mapping.get(target)
        if container is None:
            raise docker.errors.NotFound("not found")
        return container


class FakeDockerClient:
    def __init__(self, mapping: dict[str, FakeContainer]) -> None:
        self.containers = FakeContainersAPI(mapping)


async def test_restart_handler_success() -> None:
    container = FakeContainer("api")
    client = FakeDockerClient({"api": container})
    event_args = EventArgs(
        action_name="restart",
        user_id=1,
        raw_args=("api",),
        correlation_id="cid-restart-success",
        shared_state={"docker_client": client},
    )

    result = await restart_handler(event_args)
    assert Result.is_success(result)
    assert "restarted successfully" in result.data
    assert container.restarted is True


async def test_restart_handler_not_found() -> None:
    client = FakeDockerClient({})
    event_args = EventArgs(
        action_name="restart",
        user_id=1,
        raw_args=("missing",),
        correlation_id="cid-restart-not-found",
        shared_state={"docker_client": client},
    )

    result = await restart_handler(event_args)
    assert Result.is_success(result)
    assert "not found" in result.data


async def test_logs_handler_success_with_tail() -> None:
    container = FakeContainer("api", logs=b"line1\nline2\n")
    client = FakeDockerClient({"api": container})
    event_args = EventArgs(
        action_name="logs",
        user_id=1,
        raw_args=("api", "5"),
        correlation_id="cid-logs-success",
        shared_state={"docker_client": client},
    )

    result = await logs_handler(event_args)
    assert Result.is_success(result)
    assert "Logs for" in result.data
    assert "line1" in result.data


async def test_logs_handler_invalid_tail() -> None:
    container = FakeContainer("api", logs=b"line\n")
    client = FakeDockerClient({"api": container})
    event_args = EventArgs(
        action_name="logs",
        user_id=1,
        raw_args=("api", "bad-tail"),
        correlation_id="cid-logs-invalid-tail",
        shared_state={"docker_client": client},
    )

    result = await logs_handler(event_args)
    assert Result.is_success(result)
    assert "Tail value must be a number" in result.data
