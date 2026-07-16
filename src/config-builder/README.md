# Config Builder

Build merged config files for three input types used by this repository:

- users
- actions
- host-actions

## Features

- Input type aware merge for JSON/YAML fragments.
- Input expansion from repeated `--input` values and glob patterns.
- Optional `--stdin-manifest` file for line-based input lists.
- Deterministic ordering (lexicographic by resolved file path).
- First-file-wins duplicate behavior by default.
- Optional strict duplicate failure via `--fail-on-duplicate`.
- Optional duplicate audit output via `--report-duplicates`.
- Optional strict key enforcement via `--strict-key-type`.
- Optional dry-run mode via `--dry-run`.
- Optional check mode via `--check`.
- Optional machine-readable run summary via `--summary-json`.

## Root Detection

The CLI walks parent directories looking for a `.project_root` marker file.
That directory is treated as the top-level project root.

## Defaults

- users: default output filename `users.yaml`
- actions: default output filename `actions.yaml`
- host-actions: default output filename `host-actions.yaml`

Default output directory:

- users/actions: `$DEFAULT_ACTIONS_OUT_DIR` when set, else `<project-root>/tmp`
- host-actions: `$DEFAULT_HOST_ACTIONS_OUT_DIR` when set, else `<project-root>/tmp`

## Usage

```sh
cd src/config-builder/builder
uv run python main.py \
  --input-type users \
  --input "../../storage/templates/users/*.yaml"
```

```sh
uv run python main.py \
  --input-type actions \
  --base-dir ../.. \
  --input "storage/templates/actions/*.yaml" \
  --output storage/config/bot/actions.yaml \
  --report-duplicates tmp/action-duplicates.json \
  --summary-json tmp/action-summary.json
```

```sh
uv run python main.py \
  --input-type host-actions \
  --stdin-manifest tmp/host-action-inputs.txt \
  --check \
  --strict-key-type
```

## Manifest Format

`--stdin-manifest` accepts a plain text file with one path or glob per line.
Blank lines and lines starting with `#` are ignored.
