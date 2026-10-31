"""HTTP API exposing every configured Action as an Endpoint (see docs/adr/0001)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from bot_service import bot
from bot_service.event_args import EventArgs
from bot_service.reply_format import DEFAULT_REPLY_FORMAT
from bot_service.result import Result

API_KEYS_PATH = Path(os.environ.get("API_KEYS_PATH", "/app/config/api-keys.yaml"))
API_PORT = int(os.environ.get("API_PORT", "8080"))


class ActionRequest(BaseModel):
    args: list[str] = Field(default_factory=list, description="Positional arguments, same as after /command")


class ActionResponse(BaseModel):
    ok: bool
    message: str
    format: str
    correlation_id: str


def _load_api_keys() -> dict[str, int]:
    # Read per request so adding/revoking a key needs no restart.
    if not API_KEYS_PATH.exists():
        return {}
    data = yaml.safe_load(API_KEYS_PATH.read_text(encoding="utf-8")) or {}
    return {str(key_hash).lower(): int(user_id) for key_hash, user_id in data.items()}


_bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> int:
    if credentials is not None:
        key_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
        user_id = _load_api_keys().get(key_hash)
        if user_id is not None and bot.action_engine.is_known_user(user_id):
            return user_id
    raise HTTPException(status_code=401, detail="Invalid or missing API key", headers={"WWW-Authenticate": "Bearer"})


def _failure_status(event_args: EventArgs) -> int:
    errors = [result.error for result in event_args.results.values() if Result.is_failure(result)]
    return 504 if any(isinstance(error, TimeoutError) for error in errors) else 502


async def run_action(action_name: str, raw_args: tuple[str, ...], user_id: int) -> JSONResponse:
    validation_error = bot._validate_user_command_args(raw_args)
    if validation_error is not None:
        raise HTTPException(status_code=422, detail=validation_error)

    event_args = EventArgs(
        action_name=action_name,
        user_id=user_id,
        raw_args=raw_args,
        correlation_id=uuid.uuid4().hex,
        shared_state={
            "docker_client": bot.docker_client,
            "host_action_client": bot.host_action_client,
        },
    )
    result = await bot.action_engine.dispatch(event_args)

    if Result.is_failure(result):
        if isinstance(result.error, PermissionError):
            raise HTTPException(status_code=403, detail=str(result.error))
        if isinstance(result.error, ValueError):
            raise HTTPException(status_code=404, detail=str(result.error))
        status, ok, message = _failure_status(event_args), False, str(result.error)
    elif event_args.cancelled:
        # A stop_on_failure handler failed; keep the partial output like Telegram does.
        status, ok, message = _failure_status(event_args), False, result.data
    else:
        status, ok, message = 200, True, result.data

    body = ActionResponse(
        ok=ok,
        message=message,
        format=(event_args.reply_format or DEFAULT_REPLY_FORMAT).name,
        correlation_id=event_args.correlation_id,
    )
    return JSONResponse(status_code=status, content=body.model_dump())


def _summary(action_name: str) -> dict[str, object]:
    engine = bot.action_engine
    return {
        "name": action_name,
        "aliases": list(engine.get_action_aliases(action_name)),
        "tags": list(engine.get_action_tags(action_name)),
        "handlers": len(engine.list_handlers(action_name)),
    }


def _add_action_endpoint(app: FastAPI, action_name: str) -> None:
    async def endpoint(body: ActionRequest | None = None, user_id: int = Depends(current_user)) -> JSONResponse:
        return await run_action(action_name, tuple(body.args) if body else (), user_id)

    details = bot.action_engine.describe_action(action_name) or {}
    policy = details.get("policy", {})
    aliases = details.get("aliases") or []
    description = f"Equivalent to Telegram `/{action_name}`."
    if aliases:
        description += " Aliases: " + ", ".join(f"`/{alias}`" for alias in aliases) + "."
    if policy.get("allowed_roles"):
        description += " Roles: " + ", ".join(policy["allowed_roles"]) + "."

    app.add_api_route(
        f"/actions/{action_name}",
        endpoint,
        methods=["POST"],
        response_model=ActionResponse,
        summary=f"/{action_name}",
        description=description,
        operation_id=f"run_{action_name}",
        tags=list(policy.get("tags") or ["untagged"]),
    )


def build_app() -> FastAPI:
    """Build the app from the Actions currently loaded in the engine."""
    app = FastAPI(title="Telegram C2 API", description="One Endpoint per configured Action.")

    @app.get("/actions", tags=["meta"], summary="/help, /actions_by_tag")
    def list_actions(tag: list[str] = Query(default=[]), _: int = Depends(current_user)) -> list[dict[str, object]]:
        tags = bot._normalize_requested_tags(tag)
        if not tags:
            names = bot.action_engine.list_actions()
        elif bot.RESERVED_UNTAGGED_FILTERS.intersection(tags):
            names = bot.action_engine.list_untagged_actions()
        else:
            names = bot.action_engine.list_actions_by_tags(tags)
        return [_summary(name) for name in names]

    @app.get("/actions/{action_name}", tags=["meta"], summary="/action_info")
    def action_info(action_name: str, _: int = Depends(current_user)) -> dict[str, object]:
        details = bot.action_engine.describe_action(action_name)
        if details is None:
            raise HTTPException(status_code=404, detail=f"Action '{action_name}' is not registered.")
        return details

    for action_name in bot.action_engine.list_actions():
        _add_action_endpoint(app, action_name)

    return app


def load_app() -> FastAPI:
    """Load users/actions config the same way the bot does, then build the app."""
    result, _restored = bot._reload_bot_configs_with_rollback()
    if Result.is_failure(result):
        raise RuntimeError(bot._format_config_error(result.error))
    if not _load_api_keys():
        logging.warning("No API keys in %s; every request will get 401. Run `make api-key`.", API_KEYS_PATH)
    return build_app()


def export_openapi() -> None:
    print(json.dumps(load_app().openapi(), indent=2))


def main() -> None:
    import uvicorn

    uvicorn.run(load_app(), host="0.0.0.0", port=API_PORT)


if __name__ == "__main__":
    main()
