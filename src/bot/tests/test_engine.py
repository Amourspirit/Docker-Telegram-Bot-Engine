from __future__ import annotations

import asyncio

from bot_service.engine import ActionEngine, ActionPolicy
from bot_service.event_args import EventArgs
from bot_service.result import Result


async def test_dispatch_runs_stages_in_order() -> None:
    engine = ActionEngine()
    engine.set_user_roles({1: ("operator",)})
    call_order: list[str] = []

    async def first(event_args: EventArgs):
        call_order.append("first")
        event_args.shared_state["value"] = "hello"
        return Result.success(None)

    async def second(event_args: EventArgs):
        call_order.append("second")
        return Result.success(f"value={event_args.shared_state['value']}")

    engine.register_action("status", policy=ActionPolicy(allowed_roles=("operator",)))
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
    engine.set_user_roles({1: ("operator",)})
    call_order: list[str] = []

    async def failing(_event_args: EventArgs):
        call_order.append("failing")
        return Result.failure(RuntimeError("boom"))

    async def should_not_run(_event_args: EventArgs):
        call_order.append("should_not_run")
        return Result.success("ok")

    engine.register_action("status", policy=ActionPolicy(stop_on_failure=True, allowed_roles=("operator",)))
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
    engine.set_user_roles({1: ("operator",)})
    call_order: list[str] = []

    async def one(_event_args: EventArgs):
        call_order.append("one")
        return Result.success("one")

    async def two(_event_args: EventArgs):
        call_order.append("two")
        return Result.success("two")

    engine.register_action("status", policy=ActionPolicy(allowed_roles=("operator",)))
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
    engine.set_user_roles({1: ("operator",)})

    async def slow_handler(_event_args: EventArgs):
        await asyncio.sleep(0.05)
        return Result.success("slow")

    async def final_handler(_event_args: EventArgs):
        return Result.success("final")

    engine.register_action("status", policy=ActionPolicy(stop_on_failure=True, allowed_roles=("operator",)))
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


async def test_action_default_timeout_applies_when_handler_timeout_is_missing() -> None:
    engine = ActionEngine()
    engine.set_user_roles({1: ("operator",)})

    async def slow_handler(_event_args: EventArgs):
        await asyncio.sleep(0.05)
        return Result.success("slow")

    engine.register_action(
        "status",
        policy=ActionPolicy(
            stop_on_failure=True,
            default_timeout_seconds=0.001,
            allowed_roles=("operator",),
        ),
    )
    engine.register_handler("status", "h.slow", slow_handler, stage=0)

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-default-timeout-1",
        )
    )

    assert Result.is_success(result)
    assert "timed out" in result.data


async def test_dispatch_denies_action_when_no_allowed_roles_configured() -> None:
    engine = ActionEngine()
    engine.set_user_roles({1: ("admin",)})

    async def handler(_event_args: EventArgs):
        return Result.success("ok")

    engine.register_handler("status", "h.one", handler, stage=0)

    result = await engine.dispatch(
        EventArgs(
            action_name="status",
            user_id=1,
            raw_args=(),
            correlation_id="cid-no-roles-1",
        )
    )

    assert Result.is_failure(result)
    assert "denied by default" in str(result.error)


async def test_dispatch_resolves_alias_to_registered_action() -> None:
    engine = ActionEngine()
    engine.set_user_roles({1: ("operator",)})

    async def handler(_event_args: EventArgs):
        return Result.success("alias-ok")

    engine.register_action("cf_docker_url", policy=ActionPolicy(allowed_roles=("operator",)))
    engine.register_aliases("cf_docker_url", ["cf_url_docker"])
    engine.register_handler("cf_docker_url", "h.alias", handler, stage=0)

    result = await engine.dispatch(
        EventArgs(
            action_name="cf_url_docker",
            user_id=1,
            raw_args=(),
            correlation_id="cid-alias-1",
        )
    )

    assert Result.is_success(result)
    assert result.data == "alias-ok"
    assert engine.resolve_action_name("cf_url_docker") == "cf_docker_url"
    assert engine.get_action_aliases("cf_docker_url") == ("cf_url_docker",)


def test_register_aliases_replaces_previous_aliases() -> None:
    engine = ActionEngine()
    engine.register_action("cf_docker_url")
    engine.register_aliases("cf_docker_url", ["cf_url_docker", "docker_url_cf"])

    assert engine.resolve_action_name("cf_url_docker") == "cf_docker_url"
    assert engine.resolve_action_name("docker_url_cf") == "cf_docker_url"

    engine.register_aliases("cf_docker_url", ["cf_url_docker"])

    assert engine.get_action_aliases("cf_docker_url") == ("cf_url_docker",)
    assert engine.resolve_action_name("cf_url_docker") == "cf_docker_url"
    assert engine.resolve_action_name("docker_url_cf") is None
