from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse
from typing import Any, Awaitable, Callable

from bot_service.event_args import EventArgs
from bot_service.reply_format import get_reply_format
from bot_service.result import Result


class HostActionError(RuntimeError):
    """Represents a host action transport or protocol failure."""


class HostActionClient:
    def __init__(self, socket_path: str | None, endpoint: str | None = None) -> None:
        self.socket_path = socket_path
        self.endpoint = endpoint

    async def invoke(
        self,
        operation_name: str,
        event_args: EventArgs,
        params: dict[str, str] | None = None,
    ) -> Result[str | None, BaseException]:
        if not self.endpoint and not self.socket_path:
            return Result.failure(
                ValueError("BOT_HOST_ACTION_ENDPOINT or BOT_HOST_ACTION_SOCKET must be set")
            )

        writer: asyncio.StreamWriter | None = None
        try:
            if params is not None:
                if not isinstance(params, dict):
                    raise ValueError("Host action params must be a mapping")
                for key, value in params.items():
                    if not isinstance(key, str) or not key.strip():
                        raise ValueError("Host action param keys must be non-empty strings")
                    if not isinstance(value, str):
                        raise ValueError("Host action param values must be strings")

            reader, writer = await self._open_connection()
            request_payload = {
                "operation": operation_name,
                "action_name": event_args.action_name,
                "user_id": event_args.user_id,
                "raw_args": list(event_args.raw_args),
                "correlation_id": event_args.correlation_id,
                "params": params,
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

            reply_format_name = response_payload.get("reply_format")
            if isinstance(reply_format_name, str) and reply_format_name.strip():
                try:
                    event_args.reply_format = get_reply_format(reply_format_name)
                except ValueError:
                    # Unknown format from host: keep any existing action-level format.
                    pass

            return Result.success(message)

        error_message = response_payload.get("error") or "Host action failed"
        return Result.failure(HostActionError(str(error_message)))

    async def _open_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self.endpoint:
            host, port = _parse_endpoint(self.endpoint)
            return await asyncio.open_connection(host, port)

        if not self.socket_path:
            raise ValueError("BOT_HOST_ACTION_SOCKET is not set")

        return await asyncio.open_unix_connection(self.socket_path)


def _parse_endpoint(endpoint: str) -> tuple[str, int]:
    candidate = endpoint.strip()
    if not candidate:
        raise ValueError("BOT_HOST_ACTION_ENDPOINT is empty")

    parsed = urlparse(candidate if "://" in candidate else f"tcp://{candidate}")
    if not parsed.hostname or parsed.port is None:
        raise ValueError(
            "BOT_HOST_ACTION_ENDPOINT must be in host:port or tcp://host:port format"
        )

    return parsed.hostname, parsed.port


def build_host_operation_handler(
    operation_name: str,
    params: dict[str, str] | None = None,
) -> Callable[[EventArgs], Awaitable[Result[str | None, BaseException | None]]]:
    async def _handler(event_args: EventArgs) -> Result[str | None, BaseException | None]:
        client = event_args.shared_state.get("host_action_client")
        invoke = getattr(client, "invoke", None)
        if not callable(invoke):
            return Result.failure(
                HostActionError("Host action client is not available in event shared_state")
            )

        return await invoke(operation_name, event_args, params=params)

    return _handler