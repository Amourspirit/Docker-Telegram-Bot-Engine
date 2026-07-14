from __future__ import annotations

import asyncio

from bot_service.event_args import EventArgs
from bot_service.result import Result


async def external_status_collect(event_args: EventArgs):
    event_args.shared_state["external"] = "ok"
    return Result.success(None)


async def external_status_render(event_args: EventArgs):
    value = event_args.shared_state.get("external", "missing")
    return Result.success(f"external={value}")


async def external_slow(_event_args: EventArgs):
    await asyncio.sleep(0.05)
    return Result.success("slow")
