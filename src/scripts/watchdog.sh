#!/usr/bin/env zsh
# scripts/watchdog.sh
# See docs/watchdog.md for details on how this script works and how to use it.

PROJECT_ROOT_TOKEN="${PROJECT_ROOT_TOKEN:-.project_root}"
CONTAINER_NAME="telegram-c2-bot"
CHECK_INTERVAL=10

# Absolute directory containing this script (works when called from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${(%):-%N}")" && pwd)"

PROJECT_ROOT="${PROJECT_ROOT:-"${SCRIPT_DIR}"}"

if [[ ! -f "$PROJECT_ROOT/${PROJECT_ROOT_TOKEN}" ]]; then
    # echo "Warning: ${PROJECT_ROOT_TOKEN} not found in ${PROJECT_ROOT}. Attempting to locate project root..."

    # Traverse upwards until we find .project-root or hit the file system root
    while [[ "$PROJECT_ROOT" != "/" && ! -f "$PROJECT_ROOT/${PROJECT_ROOT_TOKEN}" ]]; do
        PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
    done
fi


if [[ ! -f "$PROJECT_ROOT/${PROJECT_ROOT_TOKEN}" ]]; then
    echo "Error: Could not find ${PROJECT_ROOT_TOKEN} in any parent directory." >&2
    exit 1
fi

PID_FILE="${PROJECT_ROOT}/storage/runner/host-runner.pid"

# Ensure PATH includes common locations for docker, uv, and homebrew
# export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

mkdir -p "${PROJECT_ROOT}/storage/runner"

echo "[$(date)] Watchdog service initialized for ${PROJECT_ROOT}"

if [[ -x "/usr/local/bin/docker" ]]; then
    # user may have a custom docker function in their shell, so we explicitly use the binary path if it exists
    DOCKER='/usr/local/bin/docker'
else
    DOCKER=$(which docker)
fi

if [[ -z "${DOCKER}" ]]; then
    echo "[$(date)] Docker command not found. Please ensure Docker is installed and in your PATH."
    exit 1
fi

while true; do
    # 1. Query Docker to see if telegram-c2-bot is actively running
    IS_CONTAINER_RUNNING=$("${DOCKER}" inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || echo "false")
    # echo "[$(date)] Checked container '${CONTAINER_NAME}': Running status = ${IS_CONTAINER_RUNNING}"

    if [[ "${IS_CONTAINER_RUNNING}" == "true" ]]; then
        HOST_RUNNER_ALIVE=false

        # 2. Check if host-runner process is alive via PID file
        if [[ -f "${PID_FILE}" ]]; then
            PID=$(cat "${PID_FILE}")
            if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
                HOST_RUNNER_ALIVE=true
            fi
        # else
        #     echo "[$(date)] Host-runner PID file not found. Assuming host-runner is offline."
        fi

        # 3. If container is running but host-runner is dead, launch it
        if [[ "${HOST_RUNNER_ALIVE}" == "false" ]]; then
            echo "[$(date)] Container '${CONTAINER_NAME}' is active, but host-runner is offline. Starting host-runner..."
            make -C "${PROJECT_ROOT}" start-host-runner
        # else
        #     echo "[$(date)] Container '${CONTAINER_NAME}' and host-runner are both active. No action needed."
        fi
    # else
    #     echo "[$(date)] Container '${CONTAINER_NAME}' is not running. No action taken."
    fi

    sleep ${CHECK_INTERVAL}
done