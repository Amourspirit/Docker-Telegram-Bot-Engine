from __future__ import annotations

import asyncio
import hashlib
import importlib

import pytest
from fastapi.testclient import TestClient

from bot_service.engine import ActionPolicy
from bot_service.result import Result


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("docker.from_env", lambda: object())
    import bot_service.bot as bot_module

    bot = importlib.reload(bot_module)
    import bot_service.api as api

    engine = bot.action_engine
    engine.set_user_roles({1: ("admin",), 2: ("viewer",)})

    async def echo(event_args):
        return Result.success(" ".join(event_args.raw_args) or "empty")

    async def slow(event_args):
        await asyncio.sleep(1)
        return Result.success("late")

    engine.register_action("echo", ActionPolicy(allowed_roles=("admin",), tags=("demo",)))
    engine.register_handler("echo", "echo", echo)
    engine.register_aliases("echo", ["e"])
    engine.register_action("slow", ActionPolicy(allowed_roles=("admin",), default_timeout_seconds=0.01))
    engine.register_handler("slow", "slow", slow)

    keys = tmp_path / "api-keys.yaml"
    keys.write_text(
        f'"{hashlib.sha256(b"admin-key").hexdigest()}": 1\n'
        f'"{hashlib.sha256(b"viewer-key").hexdigest()}": 2\n'
    )
    monkeypatch.setattr(api, "API_KEYS_PATH", keys)
    return TestClient(api.build_app())


ADMIN = {"Authorization": "Bearer admin-key"}


def test_action_endpoint_runs_action_with_args(client) -> None:
    response = client.post("/actions/echo", json={"args": ["a", "b"]}, headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["message"] == "a b" and body["format"] == "markdown"
    assert client.post("/actions/echo", headers=ADMIN).json()["message"] == "empty"


def test_auth_roles_and_validation(client) -> None:
    assert client.post("/actions/echo").status_code == 401
    assert client.post("/actions/echo", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/actions/echo", headers={"Authorization": "Bearer viewer-key"}).status_code == 403
    assert client.post("/actions/echo", json={"args": ["bad\x00"]}, headers=ADMIN).status_code == 422
    assert client.post("/actions/echo", json={"args": ["x"] * 11}, headers=ADMIN).status_code == 422


def test_timeout_maps_to_504(client) -> None:
    response = client.post("/actions/slow", headers=ADMIN)
    assert response.status_code == 504
    assert response.json()["ok"] is False


def test_routes_and_meta(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/actions/echo" in paths and "/actions/e" not in paths
    assert [a["name"] for a in client.get("/actions?tag=demo", headers=ADMIN).json()] == ["echo"]
    assert client.get("/actions/e", headers=ADMIN).json()["canonical_name"] == "echo"
    assert client.get("/actions/missing", headers=ADMIN).status_code == 404
