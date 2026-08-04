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
CONFIG_BACKUP_SOURCE_DIR ?= $(PROJECT_ROOT)storage/config
CONFIG_BACKUP_ROOT_DIR ?= $(PROJECT_ROOT)storage/backup
CONFIG_BACKUP_KEEP ?= 5

UNAME_S := $(shell uname -s)
WATCHDOG_SCRIPT := $(PROJECT_ROOT)src/scripts/watchdog.sh

.PHONY: help up down restart start-host-runner stop-host-runner logs host-runner-logs status watchdog-logs watchdog-install watchdog-uninstall watchdog-load watchdog-unload config-backup config-backup-list config-backup-cleanup

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
	@echo "  make config-backup        Backup storage/config into storage/backup with timestamp"
	@echo "  make config-backup-list   List existing config backups (newest first)"
	@echo "  make config-backup-cleanup Remove old backups, keep latest N (CONFIG_BACKUP_KEEP)"
	@echo "  make watchdog-install     Install watchdog service (macOS or Linux)"
	@echo "  make watchdog-uninstall   Uninstall watchdog service (macOS or Linux)"
	@echo "  make watchdog-logs        Tail watchdog log"
	@echo "  make watchdog-load        Load watchdog service (macOS or Linux)"
	@echo "  make watchdog-unload      Unload watchdog service (macOS or Linux)"

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

build-actions: config-backup build-bot-actions build-host-actions
	@echo "All actions built successfully."

config-backup:
	@if [ -d "$(CONFIG_BACKUP_SOURCE_DIR)" ]; then \
		mkdir -p "$(CONFIG_BACKUP_ROOT_DIR)"; \
		timestamp="$$(date +%y-%m-%d_%H-%M-%S)"; \
		destination="$(CONFIG_BACKUP_ROOT_DIR)/config_$${timestamp}"; \
		cp -R "$(CONFIG_BACKUP_SOURCE_DIR)" "$$destination"; \
		echo "Config backup created: $$destination"; \
	else \
		echo "Error: $(CONFIG_BACKUP_SOURCE_DIR) directory does not exist"; \
	fi

config-backup-list:
	@if [ -d "$(CONFIG_BACKUP_ROOT_DIR)" ] && ls -1d "$(CONFIG_BACKUP_ROOT_DIR)"/config_* >/dev/null 2>&1; then \
		ls -1dt "$(CONFIG_BACKUP_ROOT_DIR)"/config_*; \
	else \
		echo "No config backups found in $(CONFIG_BACKUP_ROOT_DIR)"; \
	fi

config-backup-cleanup:
	@if [ -d "$(CONFIG_BACKUP_ROOT_DIR)" ] && ls -1d "$(CONFIG_BACKUP_ROOT_DIR)"/config_* >/dev/null 2>&1; then \
		keep="$(CONFIG_BACKUP_KEEP)"; \
		if ! [[ "$$keep" =~ ^[0-9]+$$ ]] || [ "$$keep" -lt 1 ]; then \
			echo "Error: CONFIG_BACKUP_KEEP must be an integer >= 1"; \
			exit 1; \
		fi; \
		to_remove="$$(ls -1dt "$(CONFIG_BACKUP_ROOT_DIR)"/config_* | awk "NR>$$keep")"; \
		if [ -n "$$to_remove" ]; then \
			echo "$$to_remove" | while IFS= read -r backup_path; do \
				rm -rf "$$backup_path"; \
				echo "Removed $$backup_path"; \
			done; \
		else \
			echo "No old config backups to remove (keeping latest $$keep)."; \
		fi; \
	else \
		echo "No config backups found in $(CONFIG_BACKUP_ROOT_DIR)"; \
	fi

watchdog-logs:
	@mkdir -p "$(PROJECT_ROOT)storage/runner"
	@touch "$(PROJECT_ROOT)storage/runner/watchdog.log"
	@tail -f "$(PROJECT_ROOT)storage/runner/watchdog.log"

watchdog-install:
	@chmod +x "$(WATCHDOG_SCRIPT)"
	@if [ "$(UNAME_S)" = "Darwin" ]; then \
		PLIST_PATH="$(HOME)/Library/LaunchAgents/com.telegram-c2-bot.host-runner-watchdog.plist"; \
		mkdir -p "$(HOME)/Library/LaunchAgents"; \
		echo '<?xml version="1.0" encoding="UTF-8"?>' > $$PLIST_PATH; \
		echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' >> $$PLIST_PATH; \
		echo '<plist version="1.0">' >> $$PLIST_PATH; \
		echo '  <dict>' >> $$PLIST_PATH; \
		echo '    <key>Label</key>' >> $$PLIST_PATH; \
		echo '    <string>com.telegram-c2-bot.host-runner-watchdog</string>' >> $$PLIST_PATH; \
		echo '    <key>ProgramArguments</key>' >> $$PLIST_PATH; \
		echo '      <array>' >> $$PLIST_PATH; \
		echo '        <string>/bin/zsh</string>' >> $$PLIST_PATH; \
		echo '        <string>$(WATCHDOG_SCRIPT)</string>' >> $$PLIST_PATH; \
		echo '      </array>' >> $$PLIST_PATH; \
		echo '    <key>RunAtLoad</key><true/>' >> $$PLIST_PATH; \
		echo '    <key>KeepAlive</key><true/>' >> $$PLIST_PATH; \
		echo '    <key>StandardOutPath</key>' >> $$PLIST_PATH; \
		echo '    <string>$(PROJECT_ROOT)storage/runner/watchdog.log</string>' >> $$PLIST_PATH; \
		echo '    <key>StandardErrorPath</key>' >> $$PLIST_PATH; \
		echo '    <string>$(PROJECT_ROOT)storage/runner/watchdog.log</string>' >> $$PLIST_PATH; \
		echo '  </dict>' >> $$PLIST_PATH; \
		echo '</plist>' >> $$PLIST_PATH; \
		chmod 644 $$PLIST_PATH; \
		launchctl unload $$PLIST_PATH 2>/dev/null || true; \
		launchctl load -w $$PLIST_PATH; \
		echo "macOS launchd watchdog service installed & loaded."; \
	elif [ "$(UNAME_S)" = "Linux" ]; then \
		SERVICE_DIR="$(HOME)/.config/systemd/user"; \
		SERVICE_PATH="$$SERVICE_DIR/host-runner-watchdog.service"; \
		mkdir -p "$$SERVICE_DIR"; \
		echo '[Unit]' > $$SERVICE_PATH; \
		echo 'Description=Host Runner Watchdog' >> $$SERVICE_PATH; \
		echo 'After=network.target docker.service' >> $$SERVICE_PATH; \
		echo '[Service]' >> $$SERVICE_PATH; \
		echo 'Type=simple' >> $$SERVICE_PATH; \
		echo 'ExecStart=/bin/zsh $(WATCHDOG_SCRIPT)' >> $$SERVICE_PATH; \
		echo 'Restart=always' >> $$SERVICE_PATH; \
		echo 'Environment="PATH=/usr/local/bin:/usr/bin:/bin:$(HOME)/.local/bin"' >> $$SERVICE_PATH; \
		echo '[Install]' >> $$SERVICE_PATH; \
		echo 'WantedBy=default.target' >> $$SERVICE_PATH; \
		systemctl --user daemon-reload; \
		systemctl --user enable --now host-runner-watchdog.service; \
		echo "Linux systemd user watchdog service installed & started."; \
	fi

watchdog-uninstall:
	@if [ "$(UNAME_S)" = "Darwin" ]; then \
		PLIST_PATH="$(HOME)/Library/LaunchAgents/com.telegram-c2-bot.host-runner-watchdog.plist"; \
		launchctl unload -w $$PLIST_PATH 2>/dev/null || true; \
		rm -f $$PLIST_PATH; \
		echo "macOS launchd watchdog service uninstalled."; \
	elif [ "$(UNAME_S)" = "Linux" ]; then \
		systemctl --user stop host-runner-watchdog.service 2>/dev/null || true; \
		systemctl --user disable host-runner-watchdog.service 2>/dev/null || true; \
		rm -f "$(HOME)/.config/systemd/user/host-runner-watchdog.service"; \
		systemctl --user daemon-reload; \
		echo "Linux systemd user watchdog service uninstalled."; \
	fi

watchdog-load:
	@if [ "$(UNAME_S)" = "Darwin" ]; then \
		PLIST_PATH="$(HOME)/Library/LaunchAgents/com.telegram-c2-bot.host-runner-watchdog.plist"; \
		launchctl load -w $$PLIST_PATH; \
		echo "macOS launchd watchdog service loaded."; \
	elif [ "$(UNAME_S)" = "Linux" ]; then \
		systemctl --user enable --now host-runner-watchdog.service; \
		echo "Linux systemd user watchdog service enabled & started."; \
	fi

watchdog-unload:
	@if [ "$(UNAME_S)" = "Darwin" ]; then \
		PLIST_PATH="$(HOME)/Library/LaunchAgents/com.telegram-c2-bot.host-runner-watchdog.plist"; \
		launchctl unload -w $$PLIST_PATH; \
		echo "macOS launchd watchdog service unloaded."; \
	elif [ "$(UNAME_S)" = "Linux" ]; then \
		systemctl --user stop host-runner-watchdog.service; \
		systemctl --user disable host-runner-watchdog.service; \
		echo "Linux systemd user watchdog service stopped & disabled."; \
	fi
