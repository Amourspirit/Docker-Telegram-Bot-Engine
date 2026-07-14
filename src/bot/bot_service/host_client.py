from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from bot_service.event_args import EventArgs
from bot_service.result import Result


class HostActionError(RuntimeError):
    """Represents a host action transport or protocol failure."""


class HostActionClient:
    def __init__(self, socket_path: str | None) -> None:
        self.socket_path = socket_path

    async def invoke(
        self,
        operation_name: str,
        event_args: EventArgs,
    ) -> Result[str | None, BaseException]:
        if not self.socket_path:
            return Result.failure(ValueError("BOT_HOST_ACTION_SOCKET is not set"))

        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            request_payload = {
                "operation": operation_name,
                "action_name": event_args.action_name,
                "user_id": event_args.user_id,
                "raw_args": list(event_args.raw_args),
                "correlation_id": event_args.correlation_id,
            }
            writer.write(json.dumps(request_payload).encode("utf-8") + b"\n")
            await writer.drain()

            response_line = await reader.readline()
            if not response_line:
                return Result.failure(HostActionError("Host action runner closed the connection"))

            response_payload = json.loads(response_line.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return Result.failure(HostActionError(f"Host action request failed: {exc}"))
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # noqa: BLE001
                    pass

        if not isinstance(response_payload, dict):
            return Result.failure(HostActionError("Host action runner returned a non-object response"))

        ok = response_payload.get("ok")
        if ok is True:
            message = response_payload.get("message")
            if message is not None and not isinstance(message, str):
                return Result.failure(HostActionError("Host action success response must contain a string message"))
            return Result.success(message)

        error_message = response_payload.get("error") or "Host action failed"
        return Result.failure(HostActionError(str(error_message)))


def build_host_operation_handler(
    operation_name: str,
) -> Callable[[EventArgs], Awaitable[Result[str | None, BaseException | None]]]:
    async def _handler(event_args: EventArgs) -> Result[str | None, BaseException | None]:
        client = event_args.shared_state.get("host_action_client")
        invoke = getattr(client, "invoke", None)
        if not callable(invoke):
            return Result.failure(
                HostActionError("Host action client is not available in event shared_state")
            )

        return await invoke(operation_name, event_args)

    return _handler