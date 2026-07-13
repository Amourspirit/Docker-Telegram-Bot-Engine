from __future__ import annotations

import asyncio

from bot_service.engine import ActionEngine, ActionPolicy
from bot_service.event_args import EventArgs
from bot_service.result import Result


async def test_dispatch_runs_stages_in_order() -> None:
    engine = ActionEngine()
    call_order: list[str] = []

    async def first(event_args: EventArgs):
        call_order.append("first")
        event_args.shared_state["value"] = "hello"
        return Result.success(None)

    async def second(event_args: EventArgs):
        call_order.append("second")
        return Result.success(f"value={event_args.shared_state['value']}")

    engine.register_handler("status", "h.first", first, stage=0)
    engine.register_handler("status", "h.second", second, stage=1)

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-1",
        )
    )

    assert Result.is_success(result)
    assert result.data == "value=hello"
    assert call_order == ["first", "second"]


async def test_dispatch_stops_when_policy_requires() -> None:
    engine = ActionEngine()
    call_order: list[str] = []

    async def failing(_event_args: EventArgs):
        call_order.append("failing")
        return Result.failure(RuntimeError("boom"))

    async def should_not_run(_event_args: EventArgs):
        call_order.append("should_not_run")
        return Result.success("ok")

    engine.register_action("status", policy=ActionPolicy(stop_on_failure=True))
    engine.register_handler("status", "h.fail", failing, stage=0)
    engine.register_handler("status", "h.skip", should_not_run, stage=1)

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-2",
        )
    )

    assert Result.is_success(result)
    assert "failed" in result.data.lower()
    assert call_order == ["failing"]


async def test_unregister_handler_removes_execution() -> None:
    engine = ActionEngine()
    call_order: list[str] = []

    async def one(_event_args: EventArgs):
        call_order.append("one")
        return Result.success("one")

    async def two(_event_args: EventArgs):
        call_order.append("two")
        return Result.success("two")

    engine.register_handler("status", "h.one", one, stage=0)
    engine.register_handler("status", "h.two", two, stage=0)
    engine.unregister_handler("status", "h.two")

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-3",
        )
    )

    assert Result.is_success(result)
    assert result.data == "one"
    assert call_order == ["one"]


async def test_handler_timeout_returns_failure_message() -> None:
    engine = ActionEngine()

    async def slow_handler(_event_args: EventArgs):
        await asyncio.sleep(0.05)
        return Result.success("slow")

    async def final_handler(_event_args: EventArgs):
        return Result.success("final")

    engine.register_action("status", policy=ActionPolicy(stop_on_failure=True))
    engine.register_handler("status", "h.slow", slow_handler, stage=0, timeout_seconds=0.001)
    engine.register_handler("status", "h.final", final_handler, stage=1)

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-timeout-1",
        )
    )

    assert Result.is_success(result)
    assert "timed out" in result.data
    assert "final" not in result.data
