from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

import host_runner.config as config_module
from host_runner.config import HostOperationDefinition
from host_runner.config import ReplyFormatMatrix
from host_runner.config import ReplyFormatRule
from host_runner.config import load_operations_from_file
from host_runner.config import load_operations_from_text
from host_runner.server import HostActionRunner


def test_load_operations_from_yaml() -> None:
    operations = load_operations_from_text(
        """
operations:
  server.uptime:
    command:
      - /usr/bin/uptime
    timeout_seconds: 5
    allow_user_args: false
""".strip(),
        "yaml",
    )

    assert operations["server.uptime"].command == ["/usr/bin/uptime"]
    assert operations["server.uptime"].timeout_seconds == 5.0
    assert operations["server.uptime"].allow_user_args is False
    assert operations["server.uptime"].allowed_placeholders == ()
    assert operations["server.uptime"].allowed_optional_params == ()


def test_load_operations_from_yaml_parses_allowed_placeholders() -> None:
    operations = load_operations_from_text(
        """
operations:
  server.generic_url:
    command:
      - /bin/bash
      - -lc
            - printf '%s\\n' "https://{{domain_var}}"
    allowed_placeholders:
      - domain_var
""".strip(),
        "yaml",
    )

    assert operations["server.generic_url"].allowed_placeholders == ("domain_var",)


def test_load_operations_from_yaml_parses_allowed_optional_params() -> None:
        operations = load_operations_from_text(
                """
operations:
    server.lms_action:
        command:
            - /usr/bin/env
            - echo
        allow_user_args: true
        allowed_optional_params:
            - --json
            - --json
            - list
""".strip(),
                "yaml",
        )

        assert operations["server.lms_action"].allowed_optional_params == ("--json", "list")


def test_load_operations_from_yaml_rejects_invalid_allowed_optional_params_shape() -> None:
        with pytest.raises(ValueError, match="allowed_optional_params must be a list of strings"):
                load_operations_from_text(
                        """
operations:
    server.lms_action:
        command:
            - /usr/bin/env
            - echo
        allow_user_args: true
        allowed_optional_params: --json
""".strip(),
                        "yaml",
                )


def test_load_operations_from_yaml_rejects_invalid_allowed_optional_params_entry() -> None:
        with pytest.raises(
                ValueError,
                match="allowed_optional_params entries must be non-empty strings",
        ):
                load_operations_from_text(
                        """
operations:
    server.lms_action:
        command:
            - /usr/bin/env
            - echo
        allow_user_args: true
        allowed_optional_params:
            - ""
""".strip(),
                        "yaml",
                )


def test_load_operations_from_file_resolves_relative_project_root_path(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "telegram-bot"
    config_dir = project_root / "storage" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "host-actions.yaml"
    config_path.write_text(
        """
operations:
  server.uptime:
    command:
      - /usr/bin/uptime
""".strip(),
        encoding="utf-8",
    )

    fake_module_path = project_root / "src" / "host-runner" / "host_runner" / "config.py"
    monkeypatch.setattr(config_module, "__file__", str(fake_module_path))

    loaded = load_operations_from_file(str(config_path.relative_to(project_root)))

    assert loaded["server.uptime"].command == ["/usr/bin/uptime"]


@pytest.mark.asyncio
async def test_handle_request_executes_configured_operation() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    response = await runner.handle_request({"operation": "server.uptime", "raw_args": []})

    assert response == {"ok": True, "message": "up"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unknown_operation() -> None:
    runner = HostActionRunner({})

    response = await runner.handle_request({"operation": "missing", "raw_args": []})

    assert response == {"ok": False, "error": "Unknown operation: missing"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unapproved_user_args() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
                allow_user_args=False,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "server.uptime", "raw_args": ["unexpected"]}
    )

    assert response == {
        "ok": False,
        "error": "Operation 'server.uptime' does not allow user args",
    }


@pytest.mark.asyncio
async def test_handle_request_appends_allowed_user_args() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("alpha", "beta"),
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["alpha", "beta"]}
    )

    assert response == {"ok": True, "message": "alpha beta"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unapproved_optional_param() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("--json",),
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["--yaml"]}
    )

    assert response == {
        "ok": False,
        "error": (
            "Optional param '--yaml' is not allowed for operation 'echo.args'. "
            "Only the following optional params are allowed: --json"
        ),
    }


@pytest.mark.asyncio
async def test_handle_request_enforces_optional_params_per_operation() -> None:
    runner = HostActionRunner(
        {
            "echo.with_json": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("--json",),
            ),
            "echo.without_json": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("list",),
            ),
        }
    )

    allowed_response = await runner.handle_request(
        {"operation": "echo.with_json", "raw_args": ["--json"]}
    )
    denied_response = await runner.handle_request(
        {"operation": "echo.without_json", "raw_args": ["--json"]}
    )

    assert allowed_response == {"ok": True, "message": "--json"}
    assert denied_response == {
        "ok": False,
        "error": (
            "Optional param '--json' is not allowed for operation 'echo.without_json'. "
            "Only the following optional params are allowed: list"
        ),
    }


@pytest.mark.asyncio
async def test_handle_request_converts_leading_em_dash_before_optional_param_validation() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("--json",),
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["—json"]}
    )

    assert response == {"ok": True, "message": "--json"}


@pytest.mark.asyncio
async def test_handle_request_only_converts_em_dash_at_start_of_optional_param() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "import sys; print(' '.join(sys.argv[1:]))"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("--json",),
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["prefix—json"]}
    )

    assert response == {
        "ok": False,
        "error": (
            "Optional param 'prefix—json' is not allowed for operation 'echo.args'. "
            "Only the following optional params are allowed: --json"
        ),
    }


@pytest.mark.asyncio
async def test_handle_request_rejects_too_many_user_args() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "print('ok')"],
                timeout_seconds=1,
                allow_user_args=True,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]}
    )

    assert response == {"ok": False, "error": "Too many arguments (max 10)"}


@pytest.mark.asyncio
async def test_handle_request_rejects_overlong_user_args() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "print('ok')"],
                timeout_seconds=1,
                allow_user_args=True,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["x" * 257]}
    )

    assert response == {
        "ok": False,
        "error": "Argument 1 is too long (max 256 characters)",
    }


@pytest.mark.asyncio
async def test_handle_request_rejects_control_characters_in_user_args() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "print('ok')"],
                timeout_seconds=1,
                allow_user_args=True,
            )
        }
    )

    response = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["bad\narg"]}
    )

    assert response == {
        "ok": False,
        "error": "Argument 1 contains control characters",
    }


@pytest.mark.asyncio
async def test_handle_request_reports_timeouts() -> None:
    runner = HostActionRunner(
        {
            "slow": HostOperationDefinition(
                command=[sys.executable, "-c", "import time; time.sleep(0.2)"],
                timeout_seconds=0.01,
            )
        }
    )

    response = await runner.handle_request({"operation": "slow", "raw_args": []})

    assert response["ok"] is False
    assert "timed out" in response["error"]


@pytest.mark.asyncio
async def test_handle_request_rejects_params_when_operation_does_not_allow_them() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    response = await runner.handle_request(
        {
            "operation": "server.uptime",
            "raw_args": [],
            "params": {"domain_var": "CF_SPIRAL_UI_DOMAIN_NAME"},
        }
    )

    assert response == {
        "ok": False,
        "error": "Operation 'server.uptime' does not allow params",
    }


@pytest.mark.asyncio
async def test_handle_request_rejects_unexpected_params() -> None:
    runner = HostActionRunner(
        {
            "server.generic_url": HostOperationDefinition(
                command=[sys.executable, "-c", "print('ok')"],
                timeout_seconds=1,
                allowed_placeholders=("domain_var",),
            )
        }
    )

    response = await runner.handle_request(
        {
            "operation": "server.generic_url",
            "raw_args": [],
            "params": {"other_var": "value"},
        }
    )

    assert response == {
        "ok": False,
        "error": "Operation 'server.generic_url' received unexpected params: other_var",
    }


@pytest.mark.asyncio
async def test_handle_request_substitutes_placeholders() -> None:
    runner = HostActionRunner(
        {
            "server.generic_url": HostOperationDefinition(
                command=[
                    sys.executable,
                    "-c",
                    "import sys; print(sys.argv[1])",
                    "https://{{domain_var}}",
                ],
                timeout_seconds=1,
                allowed_placeholders=("domain_var",),
            )
        }
    )

    response = await runner.handle_request(
        {
            "operation": "server.generic_url",
            "raw_args": [],
            "params": {"domain_var": "example.com"},
        }
    )

    assert response == {"ok": True, "message": "https://example.com"}


@pytest.mark.asyncio
async def test_handle_request_expands_environment_variables_in_command_parts(monkeypatch) -> None:
    monkeypatch.setenv("HOST_TEST_PYTHON", sys.executable)
    runner = HostActionRunner(
        {
            "env.expanded": HostOperationDefinition(
                command=["$HOST_TEST_PYTHON", "-c", "print('ok')"],
                timeout_seconds=1,
            )
        }
    )

    response = await runner.handle_request({"operation": "env.expanded", "raw_args": []})

    assert response == {"ok": True, "message": "ok"}


@pytest.mark.asyncio
async def test_handle_request_rejects_unresolved_placeholders() -> None:
    runner = HostActionRunner(
        {
            "server.generic_url": HostOperationDefinition(
                command=[
                    sys.executable,
                    "-c",
                    "print('ok')",
                    "https://{{domain_var}}",
                ],
                timeout_seconds=1,
                allowed_placeholders=("domain_var",),
            )
        }
    )

    response = await runner.handle_request(
        {
            "operation": "server.generic_url",
            "raw_args": [],
            "params": {},
        }
    )

    assert response == {
        "ok": False,
        "error": "Operation 'server.generic_url' has unresolved placeholders: domain_var",
    }


@pytest.mark.asyncio
async def test_runner_serves_over_tcp() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    server = await asyncio.start_server(runner._handle_connection, host="127.0.0.1", port=0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(
            json.dumps({"operation": "server.uptime", "raw_args": []}).encode("utf-8") + b"\n"
        )
        await writer.drain()
        response = json.loads((await reader.readline()).decode("utf-8"))
        writer.close()
        await writer.wait_closed()

        assert response == {"ok": True, "message": "up"}
    finally:
        server.close()
        await server.wait_closed()


def test_load_operations_parses_reply_format_shorthand() -> None:
    operations = load_operations_from_text(
        """
operations:
  server.lms_action:
    command:
      - /usr/bin/env
      - echo
    reply_format: json
""".strip(),
        "yaml",
    )

    matrix = operations["server.lms_action"].reply_format
    assert matrix is not None
    assert matrix.default == "json"
    assert matrix.rules == ()


def test_load_operations_parses_reply_format_matrix() -> None:
    operations = load_operations_from_text(
        """
operations:
  server.my_action:
    command:
      - /bin/mybin
    allow_user_args: true
    allowed_optional_params:
      - -a
      - -b
      - -c
      - -d
      - -e
    reply_format:
      - default: markdown
        json:
          - single:
              - -a
              - -d
          - ands:
              - and:
                  - -a
                  - -b
              - and:
                  - -a
                  - -e
        text:
          - single:
              - -e
          - ands:
              - and:
                  - -a
                  - -c
""".strip(),
        "yaml",
    )

    matrix = operations["server.my_action"].reply_format
    assert matrix is not None
    assert matrix.default == "markdown"
    assert len(matrix.rules) == 2

    json_rule = matrix.rules[0]
    assert json_rule.format_name == "json"
    assert json_rule.singles == ("-a", "-d")
    assert json_rule.and_groups == (("-a", "-b"), ("-a", "-e"))

    text_rule = matrix.rules[1]
    assert text_rule.format_name == "text"
    assert text_rule.singles == ("-e",)
    assert text_rule.and_groups == (("-a", "-c"),)


def test_load_operations_rejects_empty_reply_format_string() -> None:
    with pytest.raises(ValueError, match="reply_format string cannot be empty"):
        load_operations_from_text(
            """
operations:
  server.my_action:
    command:
      - /bin/mybin
    reply_format: "   "
""".strip(),
            "yaml",
        )


def test_reply_format_matrix_resolves_single_or() -> None:
    matrix = ReplyFormatMatrix(
        default="markdown",
        rules=(
            ReplyFormatRule(format_name="json", singles=("-a", "-d")),
            ReplyFormatRule(format_name="text", singles=("-e",)),
        ),
    )

    assert matrix.resolve({"-a"}) == "json"
    assert matrix.resolve({"-d"}) == "json"
    assert matrix.resolve({"-e"}) == "text"
    assert matrix.resolve(set()) == "markdown"


def test_reply_format_matrix_resolves_and_groups() -> None:
    matrix = ReplyFormatMatrix(
        default="markdown",
        rules=(
            ReplyFormatRule(format_name="json", and_groups=(("-a", "-b"),)),
        ),
    )

    assert matrix.resolve({"-a", "-b"}) == "json"
    assert matrix.resolve({"-a"}) == "markdown"


def test_reply_format_matrix_first_matching_rule_wins() -> None:
    matrix = ReplyFormatMatrix(
        default="markdown",
        rules=(
            ReplyFormatRule(format_name="json", singles=("-a",)),
            ReplyFormatRule(format_name="text", singles=("-a",)),
        ),
    )

    assert matrix.resolve({"-a"}) == "json"


@pytest.mark.asyncio
async def test_handle_request_returns_resolved_reply_format() -> None:
    runner = HostActionRunner(
        {
            "echo.args": HostOperationDefinition(
                command=[sys.executable, "-c", "print('ok')"],
                timeout_seconds=1,
                allow_user_args=True,
                allowed_optional_params=("--json",),
                reply_format=ReplyFormatMatrix(
                    default="markdown",
                    rules=(ReplyFormatRule(format_name="json", singles=("--json",)),),
                ),
            )
        }
    )

    with_json = await runner.handle_request(
        {"operation": "echo.args", "raw_args": ["--json"]}
    )
    assert with_json == {"ok": True, "message": "ok", "reply_format": "json"}

    without_json = await runner.handle_request(
        {"operation": "echo.args", "raw_args": []}
    )
    assert without_json == {"ok": True, "message": "ok", "reply_format": "markdown"}


@pytest.mark.asyncio
async def test_handle_request_omits_reply_format_when_unset() -> None:
    runner = HostActionRunner(
        {
            "server.uptime": HostOperationDefinition(
                command=[sys.executable, "-c", "print('up')"],
                timeout_seconds=1,
            )
        }
    )

    response = await runner.handle_request({"operation": "server.uptime", "raw_args": []})

    assert response == {"ok": True, "message": "up"}

