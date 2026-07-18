from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from host_runner.config import HostOperationDefinition
from host_runner.config import load_operations_from_file
from host_runner.project_root import find_project_root


logger = logging.getLogger(__name__)
MAX_OUTPUT_CHARS = 4000
MAX_USER_ARGS = 10
MAX_USER_ARG_LENGTH = 256
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


class HostActionRunner:
    def __init__(self, operations: dict[str, HostOperationDefinition]) -> None:
        self.operations = operations

    def _normalize_optional_param_prefix(self, raw_args: list[str]) -> list[str]:
        normalized_args: list[str] = []
        for raw_arg in raw_args:
            if raw_arg.startswith("—"):
                normalized_args.append("--" + raw_arg[1:])
            else:
                normalized_args.append(raw_arg)

        return normalized_args

    def _validate_optional_params(self, operation_name: str, raw_args: list[str], allowed: tuple[str, ...]) -> str | None:
        if not raw_args:
            return None

        allowed_params = set(allowed)
        disallowed_params = [arg for arg in raw_args if arg not in allowed_params]
        if not disallowed_params:
            return None

        return (
            f"Optional param '{disallowed_params[0]}' is not allowed for operation "
            f"'{operation_name}'. "
            f"Only the following optional params are allowed: {', '.join(sorted(allowed_params))}"
        )

    def _validate_raw_args(self, raw_args: list[str]) -> str | None:
        if len(raw_args) > MAX_USER_ARGS:
            return f"Too many arguments (max {MAX_USER_ARGS})"

        for index, raw_arg in enumerate(raw_args, start=1):
            if len(raw_arg) > MAX_USER_ARG_LENGTH:
                return f"Argument {index} is too long (max {MAX_USER_ARG_LENGTH} characters)"

            if any(ord(character) < 32 or ord(character) == 127 for character in raw_arg):
                return f"Argument {index} contains control characters"

        return None

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

        params = payload.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return {"ok": False, "error": "params must be a mapping of string keys to string values"}

        normalized_params: dict[str, str] = {}
        for key, value in params.items():
            if not isinstance(key, str) or not key.strip():
                return {"ok": False, "error": "params keys must be non-empty strings"}
            if not isinstance(value, str):
                return {"ok": False, "error": "params values must be strings"}

            # Expand $VARS and ~ because commands run without a shell.
            expanded_value = os.path.expanduser(os.path.expandvars(value))
            normalized_params[key] = expanded_value

        allowed_placeholders = set(definition.allowed_placeholders)
        if normalized_params and not allowed_placeholders:
            return {
                "ok": False,
                "error": f"Operation '{operation_name}' does not allow params",
            }

        unknown_params = sorted(set(normalized_params.keys()) - allowed_placeholders)
        if unknown_params:
            return {
                "ok": False,
                "error": (
                    f"Operation '{operation_name}' received unexpected params: "
                    + ", ".join(unknown_params)
                ),
            }

        if raw_args and not definition.allow_user_args:
            return {"ok": False, "error": f"Operation '{operation_name}' does not allow user args"}

        normalized_raw_args = self._normalize_optional_param_prefix(raw_args)

        if normalized_raw_args:
            validation_error = self._validate_raw_args(normalized_raw_args)
            if validation_error is not None:
                return {"ok": False, "error": validation_error}

            optional_param_error = self._validate_optional_params(
                operation_name,
                normalized_raw_args,
                definition.allowed_optional_params,
            )
            if optional_param_error is not None:
                return {"ok": False, "error": optional_param_error}

        try:
            command = self._apply_placeholder_substitution(
                operation_name=operation_name,
                command=definition.command,
                params=normalized_params,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        if definition.allow_user_args:
            command.extend(normalized_raw_args)

        response = await self._run_command(command, definition.timeout_seconds)

        if response.get("ok") and definition.reply_format is not None:
            present_params = set(normalized_raw_args)
            response["reply_format"] = definition.reply_format.resolve(present_params)

        return response

    async def serve_forever(self, socket_path: str | None = None, host: str | None = None, port: int | None = None) -> None:
        if host and port is not None:
            server = await asyncio.start_server(self._handle_connection, host=host, port=port)
            logger.info("Host action runner listening on tcp://%s:%s", host, port)
            async with server:
                await server.serve_forever()
            return

        if not socket_path:
            raise ValueError("socket_path is required when HOST_ACTIONS_HOST/HOST_ACTIONS_PORT are not set")

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

    def _apply_placeholder_substitution(
        self,
        operation_name: str,
        command: list[str],
        params: dict[str, str],
    ) -> list[str]:
        rendered: list[str] = []
        unresolved_placeholders: set[str] = set()

        for part in command:
            replaced = part
            for key, value in params.items():
                replaced = replaced.replace(f"{{{{{key}}}}}", value)

            # Expand command parts because subprocess execution bypasses shell expansion.
            expanded_part = os.path.expanduser(os.path.expandvars(replaced))

            matches = PLACEHOLDER_PATTERN.findall(expanded_part)
            if matches:
                unresolved_placeholders.update(matches)

            rendered.append(expanded_part)

        if unresolved_placeholders:
            names = ", ".join(sorted(unresolved_placeholders))
            raise ValueError(
                f"Operation '{operation_name}' has unresolved placeholders: {names}"
            )

        return rendered


async def _async_main() -> None:
    config_path = os.environ.get("HOST_ACTIONS_CONFIG")
    socket_path = os.environ.get("HOST_ACTIONS_SOCKET")
    host = os.environ.get("HOST_ACTIONS_HOST")
    raw_port = os.environ.get("HOST_ACTIONS_PORT")
    port = int(raw_port) if raw_port else None

    if not config_path:
        raise ValueError("Missing HOST_ACTIONS_CONFIG")

    if (host and port is None) or (port is not None and not host):
        raise ValueError("HOST_ACTIONS_HOST and HOST_ACTIONS_PORT must be set together")

    if not host and not socket_path:
        raise ValueError("Missing HOST_ACTIONS_SOCKET for Unix socket mode")

    operations = load_operations_from_file(config_path)
    runner = HostActionRunner(operations)
    await runner.serve_forever(socket_path=socket_path, host=host, port=port)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    pj_root = os.environ.get("HOST_PROJECT_ROOT")
    if pj_root is None:
        try:
            base_dir_path = Path(__file__)
            project_root = find_project_root(base_dir_path)
            os.environ["HOST_PROJECT_ROOT"] = str(project_root)
        except FileNotFoundError:
            logger.warning("Could not locate .project_root in parent directories. HOST_PROJECT_ROOT not set.")


    asyncio.run(_async_main())