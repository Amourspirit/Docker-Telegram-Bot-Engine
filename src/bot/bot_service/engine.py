from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from bot_service.event_args import EventArgs
from bot_service.result import Result

HandlerReturn = Result[str | None, BaseException | None]
ActionHandler = Callable[[EventArgs], Awaitable[HandlerReturn]]


@dataclass(slots=True)
class ActionPolicy:
    stop_on_failure: bool = True
    default_timeout_seconds: float | None = None
    allowed_roles: tuple[str, ...] = ()


@dataclass(slots=True)
class RegisteredHandler:
    handler_id: str
    callback: ActionHandler
    stop_on_failure: bool | None = None
    timeout_seconds: float | None = None


@dataclass(slots=True)
class ActionRegistration:
    policy: ActionPolicy = field(default_factory=ActionPolicy)
    stages: list[list[RegisteredHandler]] = field(default_factory=list)


@dataclass(slots=True)
class EngineSnapshot:
    actions: dict[str, ActionRegistration]
    user_roles: dict[int, tuple[str, ...]]


class ActionEngine:
    """Event-driven action dispatcher with staged handler execution."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionRegistration] = {}
        self._user_roles: dict[int, tuple[str, ...]] = {}

    def register_action(self, action_name: str, policy: ActionPolicy | None = None) -> None:
        if action_name not in self._actions:
            self._actions[action_name] = ActionRegistration(policy=policy or ActionPolicy())
            return

        if policy is not None:
            self._actions[action_name].policy = policy

    def snapshot_state(self) -> EngineSnapshot:
        snapshot_actions: dict[str, ActionRegistration] = {}
        for action_name, registration in self._actions.items():
            cloned_policy = ActionPolicy(
                stop_on_failure=registration.policy.stop_on_failure,
                default_timeout_seconds=registration.policy.default_timeout_seconds,
                allowed_roles=registration.policy.allowed_roles,
            )
            cloned_stages: list[list[RegisteredHandler]] = []
            for stage in registration.stages:
                cloned_stage = [
                    RegisteredHandler(
                        handler_id=handler.handler_id,
                        callback=handler.callback,
                        stop_on_failure=handler.stop_on_failure,
                        timeout_seconds=handler.timeout_seconds,
                    )
                    for handler in stage
                ]
                cloned_stages.append(cloned_stage)

            snapshot_actions[action_name] = ActionRegistration(policy=cloned_policy, stages=cloned_stages)

        snapshot_roles = {user_id: roles for user_id, roles in self._user_roles.items()}

        return EngineSnapshot(actions=snapshot_actions, user_roles=snapshot_roles)

    def restore_state(self, snapshot: EngineSnapshot) -> None:
        self._actions = snapshot.actions
        self._user_roles = snapshot.user_roles

    def set_user_roles(self, user_roles: dict[int, tuple[str, ...]]) -> None:
        self._user_roles = {user_id: roles for user_id, roles in user_roles.items()}

    def get_user_roles(self, user_id: int) -> tuple[str, ...]:
        return self._user_roles.get(user_id, ())

    def can_user_execute_action(self, user_id: int, action_name: str) -> Result[None, BaseException]:
        registration = self._actions.get(action_name)
        if registration is None:
            return Result.failure(ValueError(f"No handlers registered for action: {action_name}"))

        allowed_roles = registration.policy.allowed_roles
        if not allowed_roles:
            return Result.failure(
                PermissionError(
                    f"Action '{action_name}' has no allowed roles configured and is denied by default"
                )
            )

        user_roles = set(self.get_user_roles(user_id))
        if any(role in user_roles for role in allowed_roles):
            return Result.success(None)

        return Result.failure(
            PermissionError(
                f"User {user_id} is not authorized to execute '{action_name}'. "
                f"Required roles: {', '.join(allowed_roles)}"
            )
        )

    def clear_action(self, action_name: str) -> None:
        if action_name in self._actions:
            self._actions[action_name] = ActionRegistration()

    def clear_all_actions(self) -> None:
        self._actions.clear()

    def list_actions(self) -> list[str]:
        return list(self._actions.keys())

    def register_handler(
        self,
        action_name: str,
        handler_id: str,
        callback: ActionHandler,
        stage: int = 0,
        stop_on_failure: bool | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.register_action(action_name)
        registration = self._actions[action_name]

        while len(registration.stages) <= stage:
            registration.stages.append([])

        existing = next((h for h in registration.stages[stage] if h.handler_id == handler_id), None)
        if existing is not None:
            existing.callback = callback
            existing.stop_on_failure = stop_on_failure
            existing.timeout_seconds = timeout_seconds
            return

        registration.stages[stage].append(
            RegisteredHandler(
                handler_id=handler_id,
                callback=callback,
                stop_on_failure=stop_on_failure,
                timeout_seconds=timeout_seconds,
            )
        )

    def unregister_handler(self, action_name: str, handler_id: str) -> None:
        registration = self._actions.get(action_name)
        if registration is None:
            return

        for stage in registration.stages:
            stage[:] = [h for h in stage if h.handler_id != handler_id]

    def list_handlers(self, action_name: str) -> list[str]:
        registration = self._actions.get(action_name)
        if registration is None:
            return []

        return [handler.handler_id for stage in registration.stages for handler in stage]

    def describe_action(self, action_name: str) -> dict[str, object] | None:
        registration = self._actions.get(action_name)
        if registration is None:
            return None

        stages: list[list[dict[str, object]]] = []
        for stage in registration.stages:
            stage_data: list[dict[str, object]] = []
            for handler in stage:
                stage_data.append(
                    {
                        "handler_id": handler.handler_id,
                        "stop_on_failure": handler.stop_on_failure,
                        "timeout_seconds": handler.timeout_seconds,
                    }
                )
            stages.append(stage_data)

        return {
            "policy": {
                "stop_on_failure": registration.policy.stop_on_failure,
                "default_timeout_seconds": registration.policy.default_timeout_seconds,
                "allowed_roles": list(registration.policy.allowed_roles),
            },
            "stages": stages,
        }

    async def dispatch(self, event_args: EventArgs) -> Result[str, BaseException]:
        registration = self._actions.get(event_args.action_name)
        if registration is None or not registration.stages:
            return Result.failure(ValueError(f"No handlers registered for action: {event_args.action_name}"))

        authorization_result = self.can_user_execute_action(event_args.user_id, event_args.action_name)
        if Result.is_failure(authorization_result):
            return Result.failure(authorization_result.error)

        for stage in registration.stages:
            if event_args.cancelled:
                break
            if not stage:
                continue

            stage_results = await asyncio.gather(
                *(
                    self._run_handler(
                        handler,
                        event_args,
                        registration.policy.default_timeout_seconds,
                    )
                    for handler in stage
                )
            )
            for handler, result in zip(stage, stage_results):
                event_args.results[handler.handler_id] = result
                if Result.is_failure(result):
                    should_stop = (
                        handler.stop_on_failure
                        if handler.stop_on_failure is not None
                        else registration.policy.stop_on_failure
                    )
                    if should_stop:
                        event_args.cancel(
                            f"Handler '{handler.handler_id}' failed: {result.error}"
                        )

        if event_args.cancelled and event_args.cancel_reason:
            event_args.add_section(f"⚠️ {event_args.cancel_reason}")

        text = "\n\n".join(event_args.response_sections).strip()
        if not text:
            if event_args.cancel_reason:
                return Result.failure(RuntimeError(event_args.cancel_reason))
            return Result.failure(RuntimeError("No response generated by action handlers"))

        return Result.success(text)

    async def _run_handler(
        self,
        handler: RegisteredHandler,
        event_args: EventArgs,
        default_timeout_seconds: float | None,
    ) -> HandlerReturn:
        effective_timeout = handler.timeout_seconds
        if effective_timeout is None:
            effective_timeout = default_timeout_seconds

        try:
            if effective_timeout is None:
                result = await handler.callback(event_args)
            else:
                result = await asyncio.wait_for(handler.callback(event_args), timeout=effective_timeout)
        except TimeoutError:
            return Result.failure(
                TimeoutError(
                    f"Handler '{handler.handler_id}' timed out after {effective_timeout} seconds"
                )
            )
        except Exception as exc:  # noqa: BLE001
            return Result.failure(exc)

        if Result.is_success(result) and result.data:
            event_args.add_section(result.data)

        return result