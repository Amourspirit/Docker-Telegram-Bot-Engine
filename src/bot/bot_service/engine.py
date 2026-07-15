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
    action_aliases: dict[str, tuple[str, ...]]


class ActionEngine:
    """Event-driven action dispatcher with staged handler execution."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionRegistration] = {}
        self._user_roles: dict[int, tuple[str, ...]] = {}
        self._action_aliases: dict[str, tuple[str, ...]] = {}
        self._alias_to_action: dict[str, str] = {}

    def register_action(self, action_name: str, policy: ActionPolicy | None = None) -> None:
        existing_action = self._alias_to_action.get(action_name)
        if existing_action is not None and existing_action != action_name:
            raise ValueError(
                f"Action name '{action_name}' is already configured as an alias for '{existing_action}'"
            )

        if action_name not in self._actions:
            self._actions[action_name] = ActionRegistration(policy=policy or ActionPolicy())
            self._action_aliases.setdefault(action_name, ())
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
        snapshot_aliases = {
            action_name: tuple(self._action_aliases.get(action_name, ()))
            for action_name in self._actions
        }

        return EngineSnapshot(
            actions=snapshot_actions,
            user_roles=snapshot_roles,
            action_aliases=snapshot_aliases,
        )

    def restore_state(self, snapshot: EngineSnapshot) -> None:
        self._actions = snapshot.actions
        self._user_roles = snapshot.user_roles
        self._action_aliases = {
            action_name: tuple(snapshot.action_aliases.get(action_name, ()))
            for action_name in self._actions
        }
        self._rebuild_alias_index()

    def _rebuild_alias_index(self) -> None:
        self._alias_to_action = {}
        for action_name in self._actions:
            self._action_aliases.setdefault(action_name, ())

        for action_name, aliases in self._action_aliases.items():
            for alias_name in aliases:
                self._alias_to_action[alias_name] = action_name

    def resolve_action_name(self, action_name: str) -> str | None:
        if action_name in self._actions:
            return action_name
        return self._alias_to_action.get(action_name)

    def register_aliases(self, action_name: str, aliases: tuple[str, ...] | list[str]) -> None:
        resolved_action_name = self.resolve_action_name(action_name)
        if resolved_action_name is None:
            raise ValueError(f"Cannot register aliases for unknown action: {action_name}")

        normalized_aliases: list[str] = []
        seen_aliases: set[str] = set()
        for raw_alias in aliases:
            alias_name = raw_alias.strip()
            if not alias_name:
                raise ValueError(f"Action aliases for '{resolved_action_name}' cannot contain empty values")
            if alias_name == resolved_action_name:
                raise ValueError(
                    f"Action alias '{alias_name}' duplicates its canonical action name"
                )
            if alias_name in seen_aliases:
                raise ValueError(f"Action alias '{alias_name}' is duplicated for '{resolved_action_name}'")
            if alias_name in self._actions and alias_name != resolved_action_name:
                raise ValueError(
                    f"Action alias '{alias_name}' conflicts with existing action '{alias_name}'"
                )

            existing_action = self._alias_to_action.get(alias_name)
            if existing_action is not None and existing_action != resolved_action_name:
                raise ValueError(
                    f"Action alias '{alias_name}' conflicts with alias for '{existing_action}'"
                )

            seen_aliases.add(alias_name)
            normalized_aliases.append(alias_name)

        for existing_alias in self._action_aliases.get(resolved_action_name, ()):
            self._alias_to_action.pop(existing_alias, None)

        self._action_aliases[resolved_action_name] = tuple(normalized_aliases)
        for alias_name in normalized_aliases:
            self._alias_to_action[alias_name] = resolved_action_name

    def get_action_aliases(self, action_name: str) -> tuple[str, ...]:
        resolved_action_name = self.resolve_action_name(action_name)
        if resolved_action_name is None:
            return ()
        return self._action_aliases.get(resolved_action_name, ())

    def set_user_roles(self, user_roles: dict[int, tuple[str, ...]]) -> None:
        self._user_roles = {user_id: roles for user_id, roles in user_roles.items()}

    def get_user_roles(self, user_id: int) -> tuple[str, ...]:
        return self._user_roles.get(user_id, ())

    def is_known_user(self, user_id: int) -> bool:
        return user_id in self._user_roles

    def can_user_execute_action(self, user_id: int, action_name: str) -> Result[None, BaseException]:
        resolved_action_name = self.resolve_action_name(action_name)
        registration = self._actions.get(resolved_action_name) if resolved_action_name is not None else None
        if registration is None:
            return Result.failure(ValueError(f"No handlers registered for action: {action_name}"))

        allowed_roles = registration.policy.allowed_roles
        if not allowed_roles:
            return Result.failure(
                PermissionError(
                    f"Action '{resolved_action_name}' has no allowed roles configured and is denied by default"
                )
            )

        user_roles = set(self.get_user_roles(user_id))
        if any(role in user_roles for role in allowed_roles):
            return Result.success(None)

        return Result.failure(
            PermissionError(
                f"User {user_id} is not authorized to execute '{resolved_action_name}'. "
                f"Required roles: {', '.join(allowed_roles)}"
            )
        )

    def clear_action(self, action_name: str) -> None:
        resolved_action_name = self.resolve_action_name(action_name)
        if resolved_action_name is None:
            return

        for alias_name in self._action_aliases.get(resolved_action_name, ()):
            self._alias_to_action.pop(alias_name, None)

        self._action_aliases[resolved_action_name] = ()
        self._actions[resolved_action_name] = ActionRegistration()

    def clear_all_actions(self) -> None:
        self._actions.clear()
        self._action_aliases.clear()
        self._alias_to_action.clear()

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
        resolved_action_name = self.resolve_action_name(action_name)
        if resolved_action_name is None:
            self.register_action(action_name)
            resolved_action_name = action_name

        registration = self._actions[resolved_action_name]

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
        resolved_action_name = self.resolve_action_name(action_name)
        registration = self._actions.get(resolved_action_name) if resolved_action_name is not None else None
        if registration is None:
            return

        for stage in registration.stages:
            stage[:] = [h for h in stage if h.handler_id != handler_id]

    def list_handlers(self, action_name: str) -> list[str]:
        resolved_action_name = self.resolve_action_name(action_name)
        registration = self._actions.get(resolved_action_name) if resolved_action_name is not None else None
        if registration is None:
            return []

        return [handler.handler_id for stage in registration.stages for handler in stage]

    def describe_action(self, action_name: str) -> dict[str, object] | None:
        resolved_action_name = self.resolve_action_name(action_name)
        registration = self._actions.get(resolved_action_name) if resolved_action_name is not None else None
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
            "canonical_name": resolved_action_name,
            "aliases": list(self._action_aliases.get(resolved_action_name, ())),
            "policy": {
                "stop_on_failure": registration.policy.stop_on_failure,
                "default_timeout_seconds": registration.policy.default_timeout_seconds,
                "allowed_roles": list(registration.policy.allowed_roles),
            },
            "stages": stages,
        }

    async def dispatch(self, event_args: EventArgs) -> Result[str, BaseException]:
        resolved_action_name = self.resolve_action_name(event_args.action_name)
        registration = self._actions.get(resolved_action_name) if resolved_action_name is not None else None
        if registration is None or not registration.stages:
            return Result.failure(ValueError(f"No handlers registered for action: {event_args.action_name}"))

        authorization_result = self.can_user_execute_action(event_args.user_id, resolved_action_name)
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