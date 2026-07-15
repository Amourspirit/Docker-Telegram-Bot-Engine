from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

import host_runner.config as config_module
from host_runner.config import HostOperationDefinition
from host_runner.config import load_operations_from_file
from host_runner.config import load_operations_from_text
from host_runner.server import HostActionRunner


def test_load_operations_from_yaml() -> None:
    operations = load_operations_from_text(
        """
operations:
  server.uptime:
    command:
      - /usr/bin/uptime
    timeout_seconds: 5
    allow_user_args: false
""".strip(),
        "yaml",
    )

    assert operations["server.uptime"].command == ["/usr/bin/uptime"]
    assert operations["server.uptime"].timeout_seconds == 5.0
    assert operations["server.uptime"].allow_user_args is False


def test_load_operations_from_file_resolves_relative_project_root_path(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "telegram-bot"
    config_dir = project_root / "storage" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "host-actions.yaml"
    config_path.write_text(
        """
operations:
  server.uptime:
    command:
      - /usr/bin/uptime
""".strip(),
        encoding="utf-8",
    )

    fake_module_path = project_root / "src" / "host-runner" / "host_runner" / "config.py"
    monkeypatch.setattr(config_module, "__file__", str(fake_module_path))

    loaded = load_operations_from_file(str(config_path.relative_to(project_root)))

    assert loaded["server.uptime"].command == ["/usr/bin/uptime"]


@pytest.mark.asyncio
async def test_handle_request_executes_configured_operation() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    response = await runner.handle_request({"operation": "server.uptime", "raw_args": []})

    assert response == {"ok": True, "message": "up"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unknown_operation() -> None:
    runner = HostActionRunner({})

    response = await runner.handle_request({"operation": "missing", "raw_args": []})

    assert response == {"ok": False, "error": "Unknown operation: missing"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unapproved_user_args() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
                allow_user_args=False,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "server.uptime", "raw_args": ["unexpected"]}
    )

    assert response == {
        "ok": False,
        "error": "Operation 'server.uptime' does not allow user args",
    }


@pytest.mark.asyncio
async def test_handle_request_appends_allowed_user_args() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["alpha", "beta"]}
    )

    assert response == {"ok": True, "message": "alpha beta"}


@pytest.mark.asyncio
async def test_handle_request_reports_timeouts() -> None:
    runner = HostActionRunner(
        {
            "slow": HostOperationDefinition(
                command=[sys.executable, "-c", "import time; time.sleep(0.2)"],
                timeout_seconds=0.01,
            )
        }
    )

    response = await runner.handle_request({"operation": "slow", "raw_args": []})

    assert response["ok"] is False
    assert "timed out" in response["error"]


@pytest.mark.asyncio
async def test_runner_serves_over_tcp() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    server = await asyncio.start_server(runner._handle_connection, host="127.0.0.1", port=0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(
            json.dumps({"operation": "server.uptime", "raw_args": []}).encode("utf-8") + b"\n"
        )
        await writer.drain()
        response = json.loads((await reader.readline()).decode("utf-8"))
        writer.close()
        await writer.wait_closed()

        assert response == {"ok": True, "message": "up"}
    finally:
        server.close()
        await server.wait_closed()