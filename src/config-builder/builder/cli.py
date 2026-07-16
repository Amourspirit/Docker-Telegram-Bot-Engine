from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
from click.core import ParameterSource

from builder.io import collect_input_files
from builder.io import enforce_string_keys
from builder.io import load_payload
from builder.io import serialize_payload
from builder.io import write_json_file
from builder.io import write_text_file
from builder.merge import DuplicateRecord
from builder.merge import merge_sections
from builder.project_root import find_project_root

DEFAULT_FILE_NAMES = {
    "users": "users.yaml",
    "actions": "actions.yaml",
    "host-actions": "host-actions.yaml",
}

TOP_LEVEL_KEY = {
    "users": "users",
    "actions": "actions",
    "host-actions": "operations",
}


def _normalize_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "yml":
        return "yaml"
    if normalized in {"json", "yaml"}:
        return normalized
    raise click.ClickException(f"Unsupported output format: {value}")


def _format_from_extension(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return None


def _with_extension(path: Path, output_format: str) -> Path:
    if path.suffix:
        return path
    suffix = ".json" if output_format == "json" else ".yaml"
    return path.with_suffix(suffix)


def _default_output_dir(project_root: Path, input_type: str) -> Path:
    env_name = "DEFAULT_HOST_ACTIONS_OUT_DIR" if input_type == "host-actions" else "DEFAULT_ACTIONS_OUT_DIR"
    value = os.environ.get(env_name)
    if value:
        configured = Path(value).expanduser()
        return configured if configured.is_absolute() else (project_root / configured).resolve()
    return project_root / "tmp"


def _resolve_output_path(
    project_root: Path,
    input_type: str,
    output: str | None,
    output_format: str,
) -> Path:
    if output:
        raw = Path(output).expanduser()
        # resolved = raw if raw.is_absolute() else (Path.cwd() / raw)
        resolved = raw if raw.is_absolute() else (project_root / raw)
    else:
        resolved = _default_output_dir(project_root, input_type) / DEFAULT_FILE_NAMES[input_type]

    return _with_extension(resolved.resolve(), output_format)


def _read_section(file_path: Path, input_type: str, strict_key_type: bool) -> dict[str, Any]:
    try:
        payload = load_payload(file_path)
        if strict_key_type:
            enforce_string_keys(payload, str(file_path))
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc

    top_level_key = TOP_LEVEL_KEY[input_type]
    if top_level_key not in payload:
        raise click.ClickException(
            f"Input file is missing required key '{top_level_key}': {file_path}"
        )

    section = payload[top_level_key]
    if not isinstance(section, dict):
        raise click.ClickException(
            f"Key '{top_level_key}' must map to an object in {file_path}"
        )

    return section


def _duplicates_as_dicts(duplicates: list[DuplicateRecord]) -> list[dict[str, str]]:
    return [
        {
            "key": item.key,
            "kept_from": item.kept_from,
            "skipped_from": item.skipped_from,
        }
        for item in duplicates
    ]


@click.command()
@click.option("--input-type", type=click.Choice(["users", "actions", "host-actions"]), required=True)
@click.option("--input", "input_values", multiple=True, help="Input file path or glob (repeatable)")
@click.option("--stdin-manifest", default=None, help="Text file with one input path/glob per line")
@click.option("--base-dir", default=".", show_default=True, help="Base directory for relative input globs")
@click.option("--output", default=None, help="Output file path")
@click.option(
    "--output-format",
    type=click.Choice(["json", "yaml", "yml"]),
    default="yaml",
    show_default=True,
)
@click.option("--summary-json", default=None, help="Optional path for run summary JSON")
@click.option("--report-duplicates", default=None, help="Optional path for duplicate report JSON")
@click.option("--dry-run", is_flag=True, help="Resolve and validate inputs without writing output")
@click.option("--fail-on-duplicate", is_flag=True, help="Fail if duplicate keys are found")
@click.option("--check", is_flag=True, help="Exit non-zero when generated output differs from existing file")
@click.option("--strict-key-type", is_flag=True, help="Reject non-string keys in parsed input mappings")
@click.option("--verbose", is_flag=True, help="Print resolved input file list")
def main(
    input_type: str,
    input_values: tuple[str, ...],
    stdin_manifest: str | None,
    base_dir: str,
    output: str | None,
    output_format: str,
    summary_json: str | None,
    report_duplicates: str | None,
    dry_run: bool,
    fail_on_duplicate: bool,
    check: bool,
    strict_key_type: bool,
    verbose: bool,
) -> None:
    base_dir_path = Path(base_dir).expanduser().resolve()
    project_root = find_project_root(base_dir_path)

    resolved_inputs = collect_input_files(
        base_dir=base_dir_path,
        input_values=input_values,
        stdin_manifest=stdin_manifest,
    )

    chosen_format = _normalize_format(output_format)
    ctx = click.get_current_context()
    output_format_source = ctx.get_parameter_source("output_format")

    # If output format was not provided explicitly and output extension is known, follow that extension.
    if output and output_format_source == ParameterSource.DEFAULT:
        from_extension = _format_from_extension(Path(output))
        if from_extension:
            chosen_format = from_extension

    output_path = _resolve_output_path(
        project_root=project_root,
        input_type=input_type,
        output=output,
        output_format=chosen_format,
    )

    click.echo(f"Project root: {project_root}")
    click.echo(f"Base dir: {base_dir_path}")
    click.echo(f"Input type: {input_type}")
    click.echo(f"Output format: {chosen_format}")
    click.echo(f"Output path: {output_path}")
    click.echo(f"Resolved input files: {len(resolved_inputs)}")

    if verbose:
        for item in resolved_inputs:
            click.echo(f" - {item}")

    sections: list[tuple[Path, dict[str, Any]]] = []
    for file_path in resolved_inputs:
        section = _read_section(file_path, input_type=input_type, strict_key_type=strict_key_type)
        sections.append((file_path, section))

    merged_section, duplicates = merge_sections(sections)
    top_level_key = TOP_LEVEL_KEY[input_type]
    final_payload: dict[str, Any] = {top_level_key: merged_section}

    duplicate_items = _duplicates_as_dicts(duplicates)
    click.echo(f"Merged keys: {len(merged_section)}")
    click.echo(f"Duplicate keys skipped: {len(duplicates)}")

    if fail_on_duplicate and duplicates:
        raise click.ClickException("Duplicate keys detected and --fail-on-duplicate is enabled")

    rendered = serialize_payload(final_payload, chosen_format)

    if report_duplicates:
        report_path = Path(report_duplicates).expanduser()
        if not report_path.is_absolute():
            report_path = (project_root / report_path).resolve()
        write_json_file(report_path, {"duplicates": duplicate_items})
        click.echo(f"Duplicate report: {report_path}")

    drift_detected: bool | None = None
    if check:
        existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        drift_detected = existing != rendered
        if drift_detected:
            raise click.ClickException("Output drift detected in --check mode")
        click.echo("Check mode: output is up to date")

    wrote_output = False
    if not dry_run and not check:
        write_text_file(output_path, rendered)
        wrote_output = True
        click.echo(f"Wrote output file: {output_path}")
    elif dry_run:
        click.echo("Dry-run enabled: output file was not written")

    if summary_json:
        summary_path = Path(summary_json).expanduser()
        if not summary_path.is_absolute():
            summary_path = (project_root / summary_path).resolve()
        summary_payload: dict[str, Any] = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "project_root": str(project_root),
            "base_dir": str(base_dir_path),
            "input_type": input_type,
            "input_files": [str(item) for item in resolved_inputs],
            "output_path": str(output_path),
            "output_format": chosen_format,
            "merged_key_count": len(merged_section),
            "duplicate_count": len(duplicates),
            "duplicates": duplicate_items,
            "mode": {
                "dry_run": dry_run,
                "fail_on_duplicate": fail_on_duplicate,
                "check": check,
                "strict_key_type": strict_key_type,
            },
            "check_result": {
                "drift_detected": drift_detected,
            },
            "wrote_output": wrote_output,
        }
        write_json_file(summary_path, summary_payload)
        click.echo(f"Summary JSON: {summary_path}")
