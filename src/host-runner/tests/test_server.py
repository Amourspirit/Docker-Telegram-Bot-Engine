from __future__ import annotations

import sys

import pytest

from host_runner.config import HostOperationDefinition
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