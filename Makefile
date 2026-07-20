ifneq (,$(wildcard .env))
include .env
endif

SHELL := /bin/zsh

PROJECT_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
HOST_RUNNER_DIR := $(PROJECT_ROOT)src/host-runner
HOST_ACTIONS_CONFIG ?= $(PROJECT_ROOT)config/host-actions.example.yaml
HOST_ACTIONS_HOST ?= 0.0.0.0
HOST_ACTIONS_PORT ?= 8787
HOST_RUNNER_PID_FILE := $(PROJECT_ROOT)storage/runner/host-runner.pid
HOST_RUNNER_LOG := $(PROJECT_ROOT)storage/runner/host-runner.log
ACTIONS_BASE_DIR ?= $(PROJECT_ROOT)
BOT_ACTIONS_INPUT_DIR ?= storage/templates/actions
BOT_ACTIONS_INPUT_GLOB ?= $(BOT_ACTIONS_INPUT_DIR)/*.{json,yaml,yml}
BOT_ACTIONS_OUTPUT_PATH ?= storage/config/bot/actions.yaml
BOT_ACTIONS_DUPLICATES_REPORT ?= tmp/build/action-duplicates.json
BOT_ACTIONS_SUMMARY_JSON ?= tmp/build/action-summary.json
HOST_ACTIONS_INPUT_DIR ?= storage/templates/host-actions
HOST_ACTIONS_INPUT_GLOB ?= $(HOST_ACTIONS_INPUT_DIR)/*.{json,yaml,yml}
HOST_ACTIONS_OUTPUT_PATH ?= storage/config/host/host-actions.yaml
HOST_ACTIONS_DUPLICATES_REPORT ?= tmp/build/host-action-duplicates.json
HOST_ACTIONS_SUMMARY_JSON ?= tmp/build/host-action-summary.json

.PHONY: help up down restart start-host-runner stop-host-runner logs host-runner-logs status

help:
	@echo "Targets:"
	@echo "  make up                   Start host runner and bot container"
	@echo "  make down                 Stop bot container and host runner"
	@echo "  make restart              Restart both services"
	@echo "  make logs                 Tail bot container logs"
	@echo "  make host-runner-logs     Tail host runner log"
	@echo "  make status               Show bot container and host runner status"
	@echo "  make build-bot-actions    Build bot actions"
	@echo "  make build-host-actions   Build host actions"
	@echo "  make build-actions        Build both bot and host actions"

build-bot-actions:
	@if [ -d "$(BOT_ACTIONS_INPUT_DIR)" ]; then \
		cd "$(PROJECT_ROOT)src/config-builder" \
		&& uv run python main.py \
		--input-type actions \
		--base-dir "$(ACTIONS_BASE_DIR)" \
		--input "$(BOT_ACTIONS_INPUT_GLOB)" \
		--output "$(BOT_ACTIONS_OUTPUT_PATH)" \
		--report-duplicates "$(BOT_ACTIONS_DUPLICATES_REPORT)" \
		--summary-json "$(BOT_ACTIONS_SUMMARY_JSON)" \
		&& echo "Actions built successfully. Output: $(BOT_ACTIONS_OUTPUT_PATH)" \
		&& echo "Reports: $(BOT_ACTIONS_DUPLICATES_REPORT)" \
		&& echo "Summary: $(BOT_ACTIONS_SUMMARY_JSON)" ; \
	else \
		echo "Error: $(BOT_ACTIONS_INPUT_DIR) directory does not exist"; \
	fi

build-host-actions:
	@if [ -d "$(HOST_ACTIONS_INPUT_DIR)" ]; then \
		cd "$(PROJECT_ROOT)src/config-builder" \
		&& uv run python main.py \
		--input-type host-actions \
		--base-dir "$(ACTIONS_BASE_DIR)" \
		--input "$(HOST_ACTIONS_INPUT_GLOB)" \
		--output "$(HOST_ACTIONS_OUTPUT_PATH)" \
		--report-duplicates "$(HOST_ACTIONS_DUPLICATES_REPORT)" \
		--summary-json "$(HOST_ACTIONS_SUMMARY_JSON)" \
		&& echo "Host actions built successfully. Output: $(HOST_ACTIONS_OUTPUT_PATH)" \
		&& echo "Reports: $(HOST_ACTIONS_DUPLICATES_REPORT)" \
		&& echo "Summary: $(HOST_ACTIONS_SUMMARY_JSON)" ; \
	else \
		echo "Error: $(HOST_ACTIONS_INPUT_DIR) directory does not exist"; \
	fi

up: start-host-runner
	@mkdir -p "$(PROJECT_ROOT)storage/runner"
	@cd "$(PROJECT_ROOT)" && \
		if [[ -f .env ]]; then set -a; source .env; set +a; fi; \
		docker compose up -d --build
	@echo "Bot started. Use 'make logs' to view container logs."

start-host-runner:
	@mkdir -p "$(PROJECT_ROOT)storage/runner"
	@if [[ -f "$(HOST_RUNNER_PID_FILE)" ]] && kill -0 "$$(cat "$(HOST_RUNNER_PID_FILE)")" >/dev/null 2>&1; then \
		echo "Host runner already running (PID $$(cat "$(HOST_RUNNER_PID_FILE)"))"; \
	else \
		cd "$(PROJECT_ROOT)" && \
		if [[ -f .env ]]; then set -a; source .env; set +a; echo "Loaded .env"; fi; \
		cd "$(HOST_RUNNER_DIR)" && \
		HOST_ACTIONS_CONFIG="$(HOST_ACTIONS_CONFIG)" \
		HOST_ACTIONS_HOST="$(HOST_ACTIONS_HOST)" \
		HOST_ACTIONS_PORT="$(HOST_ACTIONS_PORT)" \
		nohup uv run python main.py > "$(HOST_RUNNER_LOG)" 2>&1 & \
		echo $$! > "$(HOST_RUNNER_PID_FILE)"; \
		echo "Host runner started (PID $$(cat "$(HOST_RUNNER_PID_FILE)"))"; \
	fi

stop-host-runner:
	@if [[ -f "$(HOST_RUNNER_PID_FILE)" ]]; then \
		pid="$$(cat "$(HOST_RUNNER_PID_FILE)")"; \
		if kill -0 "$$pid" >/dev/null 2>&1; then \
			kill "$$pid"; \
			echo "Stopped host runner (PID $$pid)"; \
		else \
			echo "Host runner PID file exists, but process is not running"; \
		fi; \
		rm -f "$(HOST_RUNNER_PID_FILE)"; \
	else \
		echo "Host runner is not running"; \
	fi

down:
	@cd "$(PROJECT_ROOT)" && \
		if [[ -f .env ]]; then set -a; source .env; set +a; fi; \
		docker compose down
	@$(MAKE) stop-host-runner

restart: down up

reload: down up

logs:
	@cd "$(PROJECT_ROOT)" && \
		if [[ -f .env ]]; then set -a; source .env; set +a; fi; \
		docker compose logs -f telegram-c2-bot

host-runner-logs:
	@mkdir -p "$(PROJECT_ROOT)storage/runner"
	@touch "$(HOST_RUNNER_LOG)"
	@tail -f "$(HOST_RUNNER_LOG)"

status:
	@cd "$(PROJECT_ROOT)" && \
		if [[ -f .env ]]; then set -a; source .env; set +a; fi; \
		docker compose ps
	@if [[ -f "$(HOST_RUNNER_PID_FILE)" ]] && kill -0 "$$(cat "$(HOST_RUNNER_PID_FILE)")" >/dev/null 2>&1; then \
		echo "Host runner: running (PID $$(cat "$(HOST_RUNNER_PID_FILE)"))"; \
		echo "Host runner Config: $(HOST_ACTIONS_CONFIG)"; \
		echo "Host runner Host: $(HOST_ACTIONS_HOST)"; \
		echo "Host runner Port: $(HOST_ACTIONS_PORT)"; \
	else \
		echo "Host runner: not running"; \
	fi

build-actions: build-bot-actions build-host-actions
	@echo "All actions built successfully."