# Control Plane

![Linux](https://img.shields.io/badge/-Linux-464646?style=flat&logo=linux&logoColor=56C0C0&color=008080)
![Python](https://img.shields.io/badge/-Python-464646?style=flat&logo=python&logoColor=56C0C0&color=008080)
![SQLite](https://img.shields.io/badge/-SQLite-464646?style=flat&logo=sqlite&logoColor=56C0C0&color=008080)
![Prometheus](https://img.shields.io/badge/-Prometheus-464646?style=flat&logo=prometheus&logoColor=56C0C0&color=008080)
![Alertmanager](https://img.shields.io/badge/-Alertmanager-464646?style=flat&logo=prometheus&logoColor=56C0C0&color=008080)
![Telegram](https://img.shields.io/badge/-Telegram-464646?style=flat&logo=telegram&logoColor=56C0C0&color=008080)
![OpenAI](https://img.shields.io/badge/-OpenAI-464646?style=flat&logo=openai&logoColor=56C0C0&color=008080)
![Ansible](https://img.shields.io/badge/-Ansible-464646?style=flat&logo=ansible&logoColor=56C0C0&color=008080)
![macOS](https://img.shields.io/badge/-macOS-464646?style=flat&logo=apple&logoColor=56C0C0&color=008080)
![Orchestration](https://img.shields.io/badge/-Orchestration-464646?style=flat&logo=apacheairflow&logoColor=56C0C0&color=008080)

Alert-driven orchestration engine that receives signals, evaluates policy, creates decisions, queues tasks, executes actions, tracks outcomes, and now also generates AI-assisted weekly operational reviews.

This repository turns monitoring and internal scheduler signals into controlled operational workflows.

## Core pipeline

    signal
        -> normalize event
        -> evaluate rule
        -> create decision
        -> queue task
        -> execute action or chain
        -> persist state
        -> expose read-only API and metrics

The project currently includes:

- Alertmanager alert ingestion
- internal scheduler signal generation
- rule-based decision engine
- queued task execution
- action chaining with retries
- action locking and cooldowns
- SQLite-backed state tracking
- admin host audit workflow
- backup workflow integration
- remote mac remediation integration
- AI-assisted weekly ops review generation via OpenAI API
- review artifact delivery to Mac Documents
- read-only pipeline API
- Prometheus metrics for pipeline visibility

---

## What this project does

`control-plane` sits downstream from observability and internal automation.

It is designed to answer:

- what should happen when a signal arrives
- should the signal be ignored, executed, chained, or cooled down
- which action should run
- should multiple actions run as a workflow chain
- how to record the operational outcome
- how to expose the full pipeline safely for inspection
- how to generate a structured weekly operational review from accumulated state

Typical workflow:

    Alertmanager or scheduler
       │
       ▼
    action-runner
       │
       ├── decision: ignore
       ├── decision: execute
       ├── decision: cooldown
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
                ├── remote mac_action task
                └── weekly review artifact generation

---

## Main components

## 1. `action_runner/`

The core orchestration service.

Responsibilities:

- receive Alertmanager webhooks
- receive internal scheduler signals
- normalize incoming events
- load and validate rules
- decide what action to take
- persist decisions, tasks, runs, locks, and cooldown state
- execute actions and chains
- expose read-only API endpoints
- expose Prometheus metrics
- generate AI-assisted weekly review artifacts

Important modules:

- `app.py` — service entrypoint, worker startup, HTTP server
- `http_handler.py` — HTTP transport layer
- `events.py` — Alertmanager payload normalization
- `signal_service.py` — signal-to-decision-to-task pipeline
- `rules.py` — decision logic
- `rule_loader.py` — rule file validation and loading
- `schedule_loader.py` — schedule file validation and loading
- `scheduler.py` — internal scheduler loop
- `executor.py` — action execution and chaining
- `worker.py` — task polling and worker loops
- `state.py` — SQLite state model
- `metrics.py` — Prometheus metrics export
- `rules.yaml` — orchestration rules
- `schedules.yaml` — internal scheduled signals

## 2. `action_runner/actions/`

Registered action handlers.

Current action model includes:

- `run_backup`
- `verify_backup`
- `notify_tg`
- `notify_email`
- `enqueue_mac_action`
- `run_admin_host_audit`
- `verify_admin_host_audit`
- `analyze_admin_host_audit`
- `generate_weekly_ops_review`
- `copy_file_to_mac`

These handlers are executed through the action runner and normalized into structured results.

## 3. `agents/mac_memory_guard/`

Remote mac agent for memory-pressure reporting and remediation.

Responsibilities:

- collect mac host metrics
- evaluate local memory pressure
- publish telemetry
- poll for remote mac tasks
- perform guarded remediation actions
- report task completion back to control-plane

This gives the control-plane a real remote execution path rather than only local shell actions.

## 4. `backup/`

Backup workflow components used by orchestration.

Includes:

- VPS backup execution
- offsite copy
- backup scripts
- backup-related automation inputs

## 5. `deploy/mac/`

Mac deployment assets for the remote agent and launchd jobs.

## 6. `inventory/`

Host inventory used by backup and operational workflows.

## 7. `docs/`

Focused project documentation:

- API usage
- architecture
- admin host audit flow
- operational notes

---

## Action model

The system currently supports four main decision outcomes.

## Ignore

The signal is recorded, but no action is queued.

Typical use cases:

- intentionally ignored alerts
- known-noise conditions
- policy exclusions such as reboot detection

## Execute

A single action is queued and executed.

Typical use cases:

- direct notify
- single-step operational tasks

## Execute chain

A multi-step workflow is queued.

Typical use cases:

- backup remediation
- admin host audit flow
- weekly review generation
- multi-agent escalation

## Cooldown

The signal matches a rule, but execution is suppressed because the same action already ran recently.

Typical use cases:

- repeated memory-pressure alerts
- duplicate noisy alerts during an active incident window

---

## Example flows

## Example 1 — ignore

    HostRebootDetected
        -> decision: ignore
        -> decision stored
        -> no task
        -> no run

## Example 2 — distributed path

    MacMemoryPressure critical
        -> decision: execute_chain
        -> chain task
        -> notify step
        -> enqueue_mac_action step
        -> mac_action task created
        -> remote mac worker executes remediation

## Example 3 — backup orchestration

    BackupMissing critical
        -> decision: execute_chain
        -> run_backup
        -> verify_backup
        -> notify_tg

## Example 4 — admin host audit

    AdminHostAuditWeekly
        -> decision: execute_chain
        -> run_admin_host_audit
        -> verify_admin_host_audit
        -> analyze_admin_host_audit
        -> optional notify_tg on warning/critical

## Example 5 — weekly ops review

    WeeklyOpsReview
        -> decision: execute_chain
        -> generate_weekly_ops_review
        -> copy_file_to_mac
        -> notify_tg

---

## State model

State is persisted in SQLite.

Main tables:

- `decisions`
- `tasks`
- `runs`
- `action_locks`
- `alert_cooldowns`
- scheduled-run tracking

This allows the system to answer:

- what decision was taken for a signal
- what task was created
- which action ran
- whether an action is locked
- whether the signal is still in cooldown
- whether a chain succeeded or failed
- whether a scheduled slot was already triggered

Database location in the current project layout:

    state/action_runner.db

---

## API surface

The action runner exposes a read-only API for pipeline inspection, plus ingestion and execution endpoints.

## Health and metrics

- `GET /healthz`
- `GET /metrics`

## Read-only pipeline state

- `GET /runs`
- `GET /runs/{id}`
- `GET /decisions`
- `GET /decisions/{id}`
- `GET /tasks`
- `GET /tasks/{id}`

## Task endpoints for remote mac agent

- `GET /tasks/mac/next`
- `POST /tasks/mac/complete`

## Action and event ingestion

- `POST /actions/run`
- `POST /events/alertmanager`

Detailed examples:

- `docs/api.md`

---

## Metrics

The service exports Prometheus metrics for pipeline visibility.

Typical metric areas include:

- decisions by type
- tasks by type and status
- runs by action and status
- mac remediation result counts
- queue depth
- latest decision, task, and run timestamps
- admin host audit derived metrics
- weekly operational review artifacts through stored state

These metrics are used by the separate monitoring stack to build control-plane views and dashboards.

---

## Rules

Rules are defined in:

    action_runner/rules.yaml

A rule typically defines:

- `name`
- `enabled`
- `match`
- `action`
- `cooldown_seconds`

Supported action types:

- `ignore`
- `execute`
- `chain`

This gives the system a clear policy layer between incoming signals and operational execution.

More detail:

- `docs/architecture.md`

---

## Scheduler

The project includes a built-in scheduler.

Schedules are defined in:

    action_runner/schedules.yaml

A schedule defines:

- `name`
- `enabled`
- `weekday`
- `hour`
- `minute`
- `signal`

The scheduler emits internal signals into the same orchestration pipeline used by Alertmanager-driven events.

This means scheduled workflows and alert-driven workflows share the same:

- rule engine
- decision persistence
- task queue
- run tracking
- visibility model

No external cron is required for scheduled workflows.

---

## Weekly ops review

The project now includes AI-assisted weekly operational review generation via the OpenAI API.

The weekly review flow:

    scheduler signal
        -> WeeklyOpsReview
        -> generate_weekly_ops_review
        -> write JSON + Markdown snapshots on VPS
        -> copy markdown snapshot to Mac Documents
        -> notify Telegram

Artifacts are stored on VPS in:

    state/reviews/

Typical files:

    weekly-YYYY-MM-DD_HH-MM-SS.json
    weekly-YYYY-MM-DD_HH-MM-SS.md
    weekly-latest.json
    weekly-latest.md

The JSON artifact is intended for machine use and later automation.
The Markdown artifact is intended for human reading.

The current chain also copies the Markdown review to the Mac host, for example:

    ~/Documents/control-plane-reviews/

This gives the system a lightweight AI review layer over accumulated operational history without changing the core execution model.

---

## Admin host audit

The admin host audit is now part of the control-plane workflow model.

It is designed so that:

- the admin host reports state
- control-plane triggers audit execution
- control-plane verifies freshness
- control-plane analyzes findings
- derived metrics are exported for Grafana and Prometheus
- notifications are sent only on non-OK outcomes

This keeps interpretation and orchestration in control-plane rather than in the raw host script.

---

## Safety controls

The control-plane includes several important operational safety controls.

## Cooldowns

Repeated alerts can be suppressed for a configured period after successful execution.

## Action locking

Single actions can be protected from concurrent execution.

This is useful for:

- backup jobs
- destructive or stateful workflows
- actions that should never overlap

## Read-only visibility

The HTTP surface is intended primarily for inspection and orchestration visibility, not for broad ad hoc mutation.

## Guarded remote remediation

Remote mac remediation is intentionally constrained and implemented as a task-driven workflow rather than unrestricted shell access.

## AI review as bounded analysis

The weekly review flow generates operational summaries and recommendations, but it does not directly perform unsafe remediation. It produces artifacts and notifications inside a constrained workflow.

---

## Integration with other repositories

This repository is designed to work with separate observability and infrastructure layers.

Relationship:

    monitoring-stack
        -> Prometheus
        -> Alertmanager
        -> control-plane
        -> decisions / tasks / runs / remediation / weekly review

The monitoring layer answers:

- what is happening

The control-plane answers:

- what should we do about it

Related repositories:

- [Elyablack/monitoring-stack](https://github.com/Elyablack/monitoring-stack) — observability layer with Prometheus, Alertmanager, Loki, Grafana, demo surfaces, and runbooks
- [Elyablack/infra](https://github.com/Elyablack/infra) — supporting infrastructure automation for bootstrap, backup, restore, and recovery workflows

---

## Documentation

Additional project documentation:

- `docs/architecture.md` — system overview and pipeline architecture
- `docs/api.md` — practical API usage and curl examples
- `docs/admin-host-audit-control-plane.md` — admin host audit workflow and metrics

---

## Quick start

## 1. Review rules and schedules

    cd /srv/control-plane
    sed -n '1,260p' action_runner/rules.yaml
    sed -n '1,200p' action_runner/schedules.yaml

## 2. Compile-check the runner

    python3 -m py_compile action_runner/*.py action_runner/actions/*.py
    python3 -m py_compile agents/mac_memory_guard/*.py

## 3. Start or restart the service

If deployed with systemd:

    sudo systemctl restart action-runner
    systemctl status action-runner.service --no-pager -l

## 4. Verify health

    curl -fsS http://127.0.0.1:8088/healthz | jq
    curl -fsS http://127.0.0.1:8088/metrics | head

## 5. Inspect pipeline state

    curl -fsS http://127.0.0.1:8088/decisions | jq
    curl -fsS http://127.0.0.1:8088/tasks | jq
    curl -fsS http://127.0.0.1:8088/runs | jq

## 6. Generate a weekly review manually

    curl -s http://127.0.0.1:8088/actions/run \
      --json '{
        "action":"generate_weekly_ops_review",
        "payload":{
          "days":7
        }
      }' | jq

---

## Testing model

The system can be tested at several levels.

## 1. Rule evaluation

Send synthetic Alertmanager payloads to:

    POST /events/alertmanager

Validate that the correct decision is created:

- `ignore`
- `execute`
- `cooldown`
- `execute_chain`

## 2. Queue execution

Inspect queued tasks and resulting runs through:

- `/tasks`
- `/runs`

## 3. Backup chain validation

Validate:

- decision created
- chain task created
- `run_backup` run exists
- `verify_backup` run exists
- notify step completed or queued

## 4. Distributed mac remediation

Validate:

- critical memory alert creates chain decision
- notify step runs
- mac action is enqueued
- remote mac worker polls task
- task completion is reported back

## 5. Weekly ops review flow

Validate:

- scheduled or manual signal creates chain decision
- `generate_weekly_ops_review` succeeds
- review snapshot appears in `state/reviews/`
- `weekly-latest.md` updates
- Markdown review is copied to Mac
- Telegram notification is sent

See also:

- `docs/api.md`

---

## Repository structure

    .
    ├── Makefile
    ├── action_runner/
    │   ├── actions/
    │   ├── app.py
    │   ├── config.py
    │   ├── events.py
    │   ├── executor.py
    │   ├── http_handler.py
    │   ├── metrics.py
    │   ├── rule_loader.py
    │   ├── rules.py
    │   ├── rules.yaml
    │   ├── runtime.py
    │   ├── schedule_loader.py
    │   ├── scheduler.py
    │   ├── schedules.yaml
    │   ├── signal_service.py
    │   ├── state.py
    │   ├── task_service.py
    │   ├── tools.py
    │   └── worker.py
    ├── agents/
    │   └── mac_memory_guard/
    ├── backup/
    │   ├── backup_vps.yml
    │   ├── offsite_copy.sh
    │   └── run_backup.sh
    ├── deploy/
    │   └── mac/
    ├── docs/
    │   ├── admin-host-audit-control-plane.md
    │   ├── api.md
    │   └── architecture.md
    ├── inventory/
    │   └── hosts
    ├── logs/
    └── state/
        ├── action_runner.db
        └── reviews/

---

## Project status

The orchestration pipeline is already functional and includes:

- alert ingestion
- internal scheduler
- decision persistence
- queued task execution
- chained workflows
- backup automation
- admin host audit orchestration
- remote mac remediation
- AI-assisted weekly operational review generation
- review artifact delivery to Mac
- read-only pipeline visibility

Documentation is being added incrementally through focused docs rather than a single oversized README.

---

## License

MIT
