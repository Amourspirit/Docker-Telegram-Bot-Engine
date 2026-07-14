from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from host_runner.config import HostOperationDefinition
from host_runner.config import load_operations_from_file


logger = logging.getLogger(__name__)
MAX_OUTPUT_CHARS = 4000


class HostActionRunner:
    def __init__(self, operations: dict[str, HostOperationDefinition]) -> None:
        self.operations = operations

    async def handle_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation_name = payload.get("operation")
        if not isinstance(operation_name, str) or not operation_name:
            return {"ok": False, "error": "Missing operation"}

        definition = self.operations.get(operation_name)
        if definition is None:
            return {"ok": False, "error": f"Unknown operation: {operation_name}"}

        raw_args = payload.get("raw_args", [])
        if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
            return {"ok": False, "error": "raw_args must be a list of strings"}

        if raw_args and not definition.allow_user_args:
            return {"ok": False, "error": f"Operation '{operation_name}' does not allow user args"}

        command = list(definition.command)
        if definition.allow_user_args:
            command.extend(raw_args)

        return await self._run_command(command, definition.timeout_seconds)

    async def serve_forever(self, socket_path: str) -> None:
        socket_file = Path(socket_path)
        socket_file.parent.mkdir(parents=True, exist_ok=True)
        if socket_file.exists():
            socket_file.unlink()

        server = await asyncio.start_unix_server(self._handle_connection, path=socket_path)
        logger.info("Host action runner listening on %s", socket_path)
        async with server:
            await server.serve_forever()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                response = {"ok": False, "error": "Empty request"}
            else:
                payload = json.loads(request_line.decode("utf-8"))
                if not isinstance(payload, dict):
                    response = {"ok": False, "error": "Request payload must be an object"}
                else:
                    response = await self.handle_request(payload)
        except Exception as exc:  # noqa: BLE001
            response = {"ok": False, "error": str(exc)}

        writer.write(json.dumps(response).encode("utf-8") + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _run_command(self, command: list[str], timeout_seconds: float | None) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            if timeout_seconds is None:
                stdout, stderr = await process.communicate()
            else:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return {
                "ok": False,
                "error": f"Command timed out after {timeout_seconds} seconds",
            }

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        message = stdout_text or stderr_text or "OK"
        if len(message) > MAX_OUTPUT_CHARS:
            message = message[: MAX_OUTPUT_CHARS - 3] + "..."

        if process.returncode != 0:
            return {
                "ok": False,
                "error": f"Command exited with code {process.returncode}: {message}",
            }

        return {"ok": True, "message": message}


async def _async_main() -> None:
    config_path = os.environ.get("HOST_ACTIONS_CONFIG")
    socket_path = os.environ.get("HOST_ACTIONS_SOCKET")
    if not config_path or not socket_path:
        raise ValueError("Missing HOST_ACTIONS_CONFIG or HOST_ACTIONS_SOCKET")

    operations = load_operations_from_file(config_path)
    runner = HostActionRunner(operations)
    await runner.serve_forever(socket_path)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    asyncio.run(_async_main())