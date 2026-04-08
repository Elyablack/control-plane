SHELL := /usr/bin/env bash

PYTHON := python3
MAC_HOST ?= mac

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make check                 - compile-check runner and mac agent"
	@echo "  make check-runner          - compile-check runner only"
	@echo "  make check-mac             - compile-check mac agent only"
	@echo "  make restart-runner        - restart action-runner systemd service"
	@echo "  make status-runner         - show action-runner status"
	@echo "  make logs-runner           - show action-runner logs"
	@echo "  make deploy-mac            - deploy mac agent and launchd jobs"
	@echo "  make mac-status            - show mac launchd status and key logs"
	@echo "  make mac-logs              - show mac_memory_guard.log"
	@echo "  make mac-remediation-logs  - show remediation and worker events from mac log"
	@echo "  make mac-smoke             - dry-run test for mac agents"
	@echo "  make mac-stats             - show current mac memory, swap and top process info"
	@echo "  make full-check            - runner and mac health check"

.PHONY: check
check: check-runner check-mac

.PHONY: check-runner
check-runner:
	$(PYTHON) -m py_compile action_runner/*.py action_runner/actions/*.py

.PHONY: check-mac
check-mac:
	$(PYTHON) -m py_compile agents/mac_memory_guard/*.py

.PHONY: restart-runner
restart-runner:
	sudo systemctl restart action-runner

.PHONY: status-runner
status-runner:
	systemctl status action-runner.service --no-pager -l

.PHONY: logs-runner
logs-runner:
	journalctl -u action-runner.service -b --no-pager -n 80

.PHONY: deploy-mac
deploy-mac:
	chmod +x deploy/mac/install.sh
	MAC_HOST=$(MAC_HOST) ./deploy/mac/install.sh

.PHONY: mac-status
mac-status:
	ssh $(MAC_HOST) "\
	echo '--- report ---' && \
	launchctl print gui/\$$(id -u)/com.elvira.mac-memory-report | grep -E 'state|last exit code|runs' && \
	echo '' && \
	echo '--- worker ---' && \
	launchctl print gui/\$$(id -u)/com.elvira.mac-memory-worker | grep -E 'state|last exit code|runs' && \
	echo '' && \
	echo '--- mac_memory_guard.log ---' && \
	tail -n 20 /Users/elvira/logs/mac_memory_guard.log 2>/dev/null || true && \
	echo '' && \
	echo '--- mac_report.err.log ---' && \
	tail -n 20 /Users/elvira/logs/mac_report.err.log 2>/dev/null || true && \
	echo '' && \
	echo '--- mac_worker.err.log ---' && \
	tail -n 20 /Users/elvira/logs/mac_worker.err.log 2>/dev/null || true \
	"

.PHONY: mac-logs
mac-logs:
	ssh $(MAC_HOST) "tail -n 80 /Users/elvira/logs/mac_memory_guard.log"

.PHONY: mac-remediation-logs
mac-remediation-logs:
	ssh $(MAC_HOST) "grep -E 'event=remediation_|event=candidate_|event=worker_' /Users/elvira/logs/mac_memory_guard.log | tail -n 80"

.PHONY: mac-smoke
mac-smoke:
	ssh $(MAC_HOST) "cd /Users/elvira/scripts && python3 -m mac_memory_guard.report_agent --dry-run"
	ssh $(MAC_HOST) "cd /Users/elvira/scripts && python3 -m mac_memory_guard.worker_agent --dry-run"

.PHONY: mac-stats
mac-stats:
	ssh $(MAC_HOST) "cd /Users/elvira/scripts && python3 -m mac_memory_guard.mac_agent --print-stats"

.PHONY: full-check
full-check: check mac-smoke
	@echo ""
	@echo "=== runner health ==="
	curl -fsS http://127.0.0.1:8088/healthz | jq
	@echo ""
	@echo "=== runner service ==="
	systemctl is-active action-runner.service
	@echo ""
	@echo "=== mac status ==="
	$(MAKE) mac-status
