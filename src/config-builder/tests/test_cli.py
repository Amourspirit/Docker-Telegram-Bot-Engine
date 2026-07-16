from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from builder.cli import main


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".project_root").write_text("\n", encoding="utf-8")
    return repo


def test_users_default_output_to_project_tmp(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(
        repo / "inputs" / "users.yaml",
        """
users:
  "1":
    roles:
      - admin
""".strip(),
    )

    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input-type",
            "users",
            "--input",
            "inputs/users.yaml",
        ],
    )

    assert result.exit_code == 0
    output = repo / "tmp" / "users.yaml"
    assert output.exists()
    payload = output.read_text(encoding="utf-8")
    assert "users:" in payload


def test_actions_env_default_output_dir(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "actions.yaml", "actions:\n  ping:\n    handlers: []\n")

    out_dir = repo / "custom-out"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("DEFAULT_ACTIONS_OUT_DIR", str(out_dir))

    runner = CliRunner()
    result = runner.invoke(main, ["--input-type", "actions", "--input", "inputs/actions.yaml"])

    assert result.exit_code == 0
    assert (out_dir / "actions.yaml").exists()


def test_host_actions_env_default_output_dir(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "host-actions.yaml", "operations:\n  uptime:\n    command: [/usr/bin/uptime]\n")

    out_dir = repo / "host-out"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("DEFAULT_HOST_ACTIONS_OUT_DIR", str(out_dir))

    runner = CliRunner()
    result = runner.invoke(main, ["--input-type", "host-actions", "--input", "inputs/host-actions.yaml"])

    assert result.exit_code == 0
    assert (out_dir / "host-actions.yaml").exists()


def test_fail_on_duplicate_exits_non_zero(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "a.yaml", "actions:\n  ping:\n    handlers: []\n")
    _write(repo / "inputs" / "b.yaml", "actions:\n  ping:\n    handlers: []\n")

    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input-type",
            "actions",
            "--input",
            "inputs/*.yaml",
            "--fail-on-duplicate",
        ],
    )

    assert result.exit_code != 0
    assert "Duplicate keys detected" in result.output


def test_report_duplicates_and_summary_json_written(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "a.yaml", "actions:\n  ping:\n    handlers: []\n")
    _write(repo / "inputs" / "b.yaml", "actions:\n  ping:\n    handlers: []\n")

    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input-type",
            "actions",
            "--input",
            "inputs/*.yaml",
            "--report-duplicates",
            "tmp/dups.json",
            "--summary-json",
            "tmp/summary.json",
        ],
    )

    assert result.exit_code == 0

    dup_payload = json.loads((repo / "tmp" / "dups.json").read_text(encoding="utf-8"))
    assert len(dup_payload["duplicates"]) == 1

    summary = json.loads((repo / "tmp" / "summary.json").read_text(encoding="utf-8"))
    assert summary["duplicate_count"] == 1
    assert summary["wrote_output"] is True


def test_strict_key_type_rejects_numeric_yaml_key(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(
        repo / "inputs" / "users.yaml",
        """
users:
  123:
    roles:
      - admin
""".strip(),
    )

    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--input-type", "users", "--input", "inputs/users.yaml", "--strict-key-type"],
    )

    assert result.exit_code != 0
    assert "Non-string key found" in result.output


def test_check_mode_detects_drift(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "actions.yaml", "actions:\n  ping:\n    handlers: []\n")
    _write(repo / "tmp" / "actions.yaml", "actions:\n  old:\n    handlers: []\n")

    monkeypatch.chdir(repo)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--input-type", "actions", "--input", "inputs/actions.yaml", "--check"],
    )

    assert result.exit_code != 0
    assert "Output drift detected" in result.output


def test_check_mode_passes_when_up_to_date(tmp_path: Path, monkeypatch) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "inputs" / "actions.yaml", "actions:\n  ping:\n    handlers: []\n")

    monkeypatch.chdir(repo)
    runner = CliRunner()

    # First run writes output.
    first = runner.invoke(main, ["--input-type", "actions", "--input", "inputs/actions.yaml"])
    assert first.exit_code == 0

    # Second run checks for drift.
    second = runner.invoke(
        main,
        ["--input-type", "actions", "--input", "inputs/actions.yaml", "--check"],
    )
    assert second.exit_code == 0
    assert "up to date" in second.output


def test_base_dir_and_stdin_manifest_and_auto_extension(tmp_path: Path) -> None:
    repo = _prepare_repo(tmp_path)
    _write(repo / "configs" / "users" / "a.json", '{"users": {"1": {"roles": ["admin"]}}}')
    _write(repo / "manifest.txt", "configs/users/*.json\n")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input-type",
            "users",
            "--base-dir",
            str(repo),
            "--stdin-manifest",
            str(repo / "manifest.txt"),
            "--output",
            str(repo / "tmp" / "users-output"),
            "--dry-run",
            "--summary-json",
            str(repo / "tmp" / "summary.json"),
        ],
    )

    assert result.exit_code == 0
    summary = json.loads((repo / "tmp" / "summary.json").read_text(encoding="utf-8"))
    assert summary["output_path"].endswith("users-output.yaml")
    assert summary["mode"]["dry_run"] is True
