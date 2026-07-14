from __future__ import annotations

import asyncio
import json
from pathlib import Path
import uuid

from bot_service.event_args import EventArgs
from bot_service.host_client import HostActionClient
from bot_service.result import Result


async def test_host_action_client_round_trips_over_unix_socket(tmp_path) -> None:
    socket_path = Path("/tmp") / f"host-actions-{uuid.uuid4().hex}.sock"

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = await reader.readline()
        request_payload = json.loads(request_line.decode("utf-8"))
        response_payload = {
            "ok": True,
            "message": (
                f"{request_payload['operation']}:{request_payload['user_id']}:"
                f"{','.join(request_payload['raw_args'])}"
            ),
        }
        writer.write(json.dumps(response_payload).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_connection, path=str(socket_path))
    try:
        client = HostActionClient(str(socket_path))
        result = await client.invoke(
            "server.uptime",
            EventArgs(
                action_name="server_uptime",
                user_id=1,
                raw_args=("now",),
                correlation_id="cid-client-1",
            ),
        )

        assert Result.is_success(result)
        assert result.data == "server.uptime:1:now"
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)


async def test_host_action_client_reports_runner_error(tmp_path) -> None:
    socket_path = Path("/tmp") / f"host-actions-{uuid.uuid4().hex}.sock"

    async def handle_connection(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(json.dumps({"ok": False, "error": "runner-denied"}).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_connection, path=str(socket_path))
    try:
        client = HostActionClient(str(socket_path))
        result = await client.invoke(
            "server.uptime",
            EventArgs(
                action_name="server_uptime",
                user_id=1,
                raw_args=(),
                correlation_id="cid-client-2",
            ),
        )

        assert Result.is_failure(result)
        assert "runner-denied" in str(result.error)
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)