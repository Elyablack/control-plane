# Control Plane

![Linux](https://img.shields.io/badge/-Linux-464646?style=flat&logo=linux&logoColor=56C0C0&color=008080)
![Python](https://img.shields.io/badge/-Python-464646?style=flat&logo=python&logoColor=56C0C0&color=008080)
![FastAPI](https://img.shields.io/badge/-FastAPI-464646?style=flat&logo=fastapi&logoColor=56C0C0&color=008080)
![SQLite](https://img.shields.io/badge/-SQLite-464646?style=flat&logo=sqlite&logoColor=56C0C0&color=008080)
![Prometheus](https://img.shields.io/badge/-Prometheus-464646?style=flat&logo=prometheus&logoColor=56C0C0&color=008080)
![Alertmanager](https://img.shields.io/badge/-Alertmanager-464646?style=flat&logo=prometheus&logoColor=56C0C0&color=008080)
![Telegram](https://img.shields.io/badge/-Telegram-464646?style=flat&logo=telegram&logoColor=56C0C0&color=008080)
![Ansible](https://img.shields.io/badge/-Ansible-464646?style=flat&logo=ansible&logoColor=56C0C0&color=008080)
![macOS](https://img.shields.io/badge/-macOS-464646?style=flat&logo=apple&logoColor=56C0C0&color=008080)
![Orchestration](https://img.shields.io/badge/-Orchestration-464646?style=flat&logo=apacheairflow&logoColor=56C0C0&color=008080)

Alert-driven orchestration engine that receives alerts, evaluates rules, creates decisions, queues tasks, executes actions, and tracks remediation outcomes.

This repository turns monitoring signals into controlled operational workflows.

Core pipeline:

```
Alertmanager alert
    -> normalize event
    -> evaluate rule
    -> create decision
    -> queue task
    -> execute action or chain
    -> persist state
    -> expose read-only API and metrics
```

The project currently includes:

- alert ingestion from Alertmanager
- rule-based decision engine
- queued task execution
- action chaining with retries
- action locking and cooldowns
- SQLite-backed state tracking
- backup workflow integration
- remote mac remediation integration
- read-only pipeline API
- Prometheus metrics for pipeline visibility

---

## What this project does

control-plane sits downstream from observability.

It is designed to answer:

- what should happen when a specific alert arrives
- should the alert be ignored, executed, or cooled down
- which action should run
- should multiple actions run as a chain
- how to record the operational outcome
- how to expose the full pipeline safely for inspection

Typical workflow:

```
Alertmanager
   │
   ▼
action-runner
   │
   ├── decision: ignore
   ├── decision: execute
   └── decision: execute_chain
            │
            ▼
         task queue
            │
            ▼
       worker execution
            │
            ├── local action run
            ├── notify task
            └── remote mac_action task
```

---

## Main components

### 1. action_runner/

The core orchestration service.

Responsibilities:

- receive Alertmanager webhooks
- normalize incoming alerts
- load and validate rules
- decide what action to take
- persist decisions, tasks, runs, and cooldown state
- execute actions and chains
- expose read-only API endpoints
- expose Prometheus metrics

Important modules:

- app.py — HTTP API, worker startup, ingestion endpoints
- events.py — Alertmanager payload normalization
- rules.py — decision logic
- rule_loader.py — rule file validation and loading
- executor.py — action execution and chaining
- worker.py — task polling and worker loops
- state.py — SQLite state model
- metrics.py — Prometheus metrics export
- rules.yaml — orchestration rules

### 2. action_runner/actions/

Registered action handlers.

Current action model includes:

- run_backup
- verify_backup
- notify_tg
- enqueue_mac_action

These handlers are executed through the action runner and normalized into structured results.

### 3. agents/mac_memory_guard/

Remote mac agent for memory-pressure reporting and remediation.

Responsibilities:

- collect mac host metrics
- evaluate local memory pressure
- publish telemetry
- poll for remote mac tasks
- perform guarded remediation actions
- report task completion back to control-plane

This gives the control-plane a real remote execution path, rather than only local shell actions.

### 4. backup/

Backup workflow components used by orchestration.

Includes:

- VPS backup execution
- offsite copy
- backup scripts
- backup-related automation inputs

### 5. deploy/mac/

Mac deployment assets for the remote agent and launchd jobs.

### 6. inventory/

Host inventory used by backup and operational workflows.

---

## Action model

The system currently supports three main decision types:

### Ignore

The alert is recorded, but no action is queued.

Used for:

- intentionally ignored alerts
- known-noise conditions
- policy exclusions such as reboot detection

### Execute

A single action is queued and executed.

Used for:

- direct notify
- single-step operational tasks

### Execute chain

A multi-step workflow is queued.

Used for:

- backup remediation
- multi-agent escalation
- sequential action flows with optional retry behavior

---

## Current action flow examples

### Example 1 — ignore

```
HostRebootDetected
    -> decision: ignore
    -> decision stored
    -> no task
    -> no run
```

### Example 2 — distributed path

```
MacMemoryPressure critical
    -> decision: execute_chain
    -> chain task
    -> notify step
    -> enqueue_mac_action step
    -> mac_action task created
    -> remote mac worker executes remediation
```

### Example 3 — backup orchestration

```
BackupMissing critical
    -> decision: execute_chain
    -> chain task
    -> run_backup
    -> verify_backup
    -> notify step
```

---

## State model

State is persisted in SQLite.

Main tables:

- decisions
- tasks
- runs
- action_locks
- alert_cooldowns

This allows the system to answer:

- what decision was taken for an alert
- what task was created
- which action ran
- whether an action is locked
- whether the alert is still in cooldown
- whether a chain succeeded or failed

Database location in the current project layout:

```
state/action_runner.db
```

---

## API surface

The action runner exposes a read-only API for pipeline inspection, plus ingestion and execution endpoints.

### Health and metrics

- GET /healthz
- GET /metrics

### Read-only pipeline state

- GET /runs
- GET /runs/{id}
- GET /decisions
- GET /decisions/{id}
- GET /tasks
- GET /tasks/{id}

### Task endpoints for remote mac agent

- GET /tasks/mac/next
- POST /tasks/mac/complete

### Action and event ingestion

- POST /actions/run
- POST /events/alertmanager

---

## Metrics

The service exports Prometheus metrics for pipeline visibility.

These metrics are used by the separate monitoring stack to build:
	
- control-plane summary views
- task/run status panels
- decision mix panels
- queue depth views
- remediation result dashboards

Typical metric areas include:
	
- decisions by type
- tasks by type and status
- runs by action and status
- mac remediation result counts
- queue depth
- latest decision/task/run timestamps

---

## Rules

Rules are defined in:

```
action_runner/rules.yaml
```

A rule typically defines:

- name
- enabled
- match
- action
- cooldown_seconds

Supported action types:

- ignore
- execute
- chain

This gives the system a clear policy layer between incoming alerts and operational execution.

---

## Safety controls

The control-plane includes several important operational safety controls.

### Cooldowns

Repeated alerts can be suppressed for a configured period after successful execution.

### Action locking

Single actions can be protected from concurrent execution.

This is useful for:

- backup jobs
- destructive or stateful workflows
- actions that should never overlap

### Read-only visibility

The HTTP surface is intended primarily for inspection and orchestration visibility, not for broad ad hoc mutation.

### Guarded remote remediation

Remote mac remediation is intentionally constrained and implemented as a task-driven workflow rather than unrestricted shell access.

---

## Integration with monitoring-stack

This repository is designed to work with the separate monitoring-stack project.

Relationship:

```
monitoring-stack
    -> Prometheus
    -> Alertmanager
    -> control-plane
    -> decisions / tasks / runs / remediation
```

The monitoring layer answers:

- what is happening

The control-plane answers:

- what should we do about it

Related repository:

- [Elyablack/monitoring-stack](https://github.com/Elyablack/monitoring-stack) — observability layer with Prometheus, Alertmanager, Loki, Grafana, demo surfaces, and runbooks
- [Elyablack/infra](https://github.com/Elyablack/infra) — supporting infrastructure automation for bootstrap, backup, restore, and recovery workflows

---

## Quick start

1. Review rules

```
cd /srv/control-plane
sed -n '1,240p' action_runner/rules.yaml
```

2. Compile-check the runner

```
python3 -m py_compile action_runner/*.py action_runner/actions/*.py
```

3. Start or restart the service

If deployed with systemd:

```
sudo systemctl restart action-runner
systemctl status action-runner.service --no-pager -l
```

4. Verify health

```
curl -fsS http://127.0.0.1:8088/healthz | jq
curl -fsS http://127.0.0.1:8088/metrics | head
```

5. Inspect pipeline state

```
curl -fsS http://127.0.0.1:8088/decisions | jq
curl -fsS http://127.0.0.1:8088/tasks | jq
curl -fsS http://127.0.0.1:8088/runs | jq
```

---

## Testing model

The system can be tested at several levels.

1. Rule evaluation

Send synthetic Alertmanager payloads to:

```
POST /events/alertmanager
```

Validate that the correct decision is created:

- ignore
- execute
- cooldown
- execute_chain

2. Queue execution

Inspect queued tasks and resulting runs through:

- /tasks
- /runs

3. Backup chain validation

Validate:

- decision created
- chain task created
- run_backup run exists
- verify_backup run exists
- notify step completed or queued

4. Distributed mac remediation

Validate:

- critical memory alert creates chain decision
- notify step runs
- mac action is enqueued
- remote mac worker polls task
- task completion is reported back

---

## Repository structure

```
.
├── Makefile
├── action_runner/
│   ├── actions/
│   ├── app.py
│   ├── config.py
│   ├── events.py
│   ├── executor.py
│   ├── metrics.py
│   ├── rule_loader.py
│   ├── rules.py
│   ├── rules.yaml
│   ├── state.py
│   └── worker.py
├── agents/
│   └── mac_memory_guard/
├── backup/
│   ├── backup_vps.yml
│   ├── offsite_copy.sh
│   └── run_backup.sh
├── deploy/
│   └── mac/
├── inventory/
│   └── hosts
├── logs/
└── state/
    └── action_runner.db
```

---

## Project status

The orchestration pipeline is already functional and includes:

- alert ingestion
- decision persistence
- queued task execution
- chained workflows
- backup automation
- remote mac remediation
- read-only pipeline visibility

Documentation is being added incrementally.

---

License

MIT
