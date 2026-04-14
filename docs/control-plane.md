# Control Plane

`control-plane` is an alert-driven orchestration engine for small self-hosted infrastructure.

It receives monitoring signals and internal scheduler signals, evaluates rules, creates decisions, queues tasks, executes actions or chains, tracks outcomes, exposes state through an API, exports Prometheus metrics, and produces bounded AI-assisted operational artifacts.

## Core pipeline

```text
signal
    -> normalize event
    -> evaluate rule
    -> create decision
    -> queue task
    -> execute action or chain
    -> persist state
    -> expose API and metrics
```

## What this project does

`control-plane` sits downstream from observability.

The monitoring stack answers:

```text
what is happening?
```

The control-plane answers:

```text
what should happen next?
```

It is designed to handle:

- Alertmanager events
- scheduled internal signals
- rule-based decisions
- chained workflows
- backup checks
- host audits
- monitoring stack audits
- Mac agent snapshots
- Telegram notifications
- guarded Mac remediation
- AI-generated brief artifacts
- weekly AI operational summaries

## Main components

### `action_runner/`

The core service.

Responsibilities:

- receive Alertmanager webhooks
- receive Mac audit snapshots
- run internal scheduler
- load rules and schedules
- create decisions
- queue tasks
- execute actions and chains
- persist decisions, tasks, and runs
- expose API and metrics
- generate AI briefs and weekly reviews

Important files:

```text
action_runner/app.py
action_runner/http_handler.py
action_runner/events.py
action_runner/signal_service.py
action_runner/rules.py
action_runner/rule_loader.py
action_runner/schedule_loader.py
action_runner/scheduler.py
action_runner/executor.py
action_runner/worker.py
action_runner/state.py
action_runner/metrics.py
action_runner/rules.yaml
action_runner/schedules.yaml
```

### `action_runner/actions/`

Registered action handlers.

Current action families:

- backup
- notify
- admin host audit
- VPS host audit
- monitoring stack audit
- Mac host audit
- Mac file copy
- Mac remediation task enqueue
- AI ops brief
- weekly ops review

### `agents/mac_memory_guard/`

Mac-side agent.

Responsibilities:

- collect Mac memory and host facts
- publish memory metrics
- publish Mac host audit snapshots
- poll for remote remediation tasks
- execute guarded remediation
- report task completion

### `backup/`

Backup scripts and automation inputs.

### `docs/`

Focused documentation for each subsystem.

## Decision model

The system supports four main decision outcomes.

### `ignore`

Signal is recorded, but no task is queued.

Typical use:

- known noise
- intentionally ignored alerts
- policy exclusions

### `execute`

A single action is queued.

Typical use:

- direct notification
- one-step action

### `execute_chain`

A multi-step workflow is queued.

Typical use:

- audit flows
- backup flow
- remediation flow
- weekly review flow

### `cooldown`

A rule matched, but recent execution suppresses another run.

Typical use:

- repeated alerts
- noisy pressure conditions
- duplicate signals during the same incident window

## Scheduled workflows

Schedules are defined in:

```text
action_runner/schedules.yaml
```

Current schedule shape:

```text
04:00 admin_host_audit_daily
04:15 vps_host_audit_daily
04:30 monitoring_stack_audit_daily
04:45 mac_host_audit_daily
05:00 weekly_ops_review
```

No external cron is used for these workflows.

## Audit domains

The project currently has four deterministic audit domains.

### Admin host audit

Signal:

```text
AdminHostAuditDaily
```

Flow:

```text
run_admin_host_audit
    -> verify_admin_host_audit
    -> analyze_admin_host_audit
    -> generate_ai_ops_brief on meaningful warning/critical
    -> copy_file_to_mac on meaningful warning/critical
    -> notify_tg on meaningful warning/critical
```

Purpose:

- inspect admin host state
- verify Time Machine / infra-backups signals
- analyze host health
- export derived metrics
- suppress low-value persistent noise where appropriate

Docs:

```text
docs/admin-host-audit.md
```

### VPS host audit

Signal:

```text
VpsHostAuditDaily
```

Flow:

```text
run_vps_host_audit
    -> verify_vps_host_audit
    -> analyze_vps_host_audit
    -> generate_ai_ops_brief on warning/critical
    -> copy_file_to_mac on warning/critical
    -> notify_tg on warning/critical
```

Purpose:

- inspect the VPS that runs control-plane and monitoring-stack
- check services
- check Docker state
- check disk/inodes/swap
- check UFW posture
- check Tailscale serve exposure
- write derived metrics

Docs:

```text
docs/vps-host-audit.md
```

### Monitoring stack audit

Signal:

```text
MonitoringStackAuditDaily
```

Flow:

```text
run_monitoring_stack_audit
    -> verify_monitoring_stack_audit
    -> analyze_monitoring_stack_audit
    -> generate_ai_ops_brief on warning/critical
    -> copy_file_to_mac on warning/critical
    -> notify_tg on warning/critical
```

Purpose:

- inspect observability runtime itself
- verify Prometheus, Alertmanager, Grafana, Loki, Promtail
- verify custom demo and relay containers
- check readiness endpoints
- check Prometheus API
- check scrape targets
- use demo-app as canary workload

Docs:

```text
docs/monitoring-stack-audit.md
```

### Mac host audit

Signal:

```text
MacHostAuditDaily
```

Flow:

```text
mac_memory_guard report agent
    -> POST /events/mac-host-audit
    -> save latest snapshot on VPS

MacHostAuditDaily
    -> verify_mac_host_audit
    -> analyze_mac_host_audit
    -> generate_ai_ops_brief on warning/critical
    -> copy_file_to_mac on warning/critical
    -> notify_tg on warning/critical
```

Purpose:

- use the existing Mac agent as source of truth
- avoid SSH-based Mac audit
- collect Mac operational state locally
- analyze snapshot on VPS
- include Mac in weekly review as a first-class audit domain

Docs:

```text
docs/mac-host-audit.md
```

## AI ops briefs

AI ops briefs are short tactical summaries generated from deterministic analyzer output.

They do not replace the analyzer.

They run only after warning or critical audit outcomes.

Current sources:

```text
admin_host_audit
vps_host_audit
monitoring_stack_audit
mac_host_audit
```

Artifacts:

```text
/srv/control-plane/state/reviews/briefs/
```

Examples:

```text
brief-admin_host_audit-YYYY-MM-DD_HH-MM-SS.md
brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.md
brief-monitoring_stack_audit-YYYY-MM-DD_HH-MM-SS.md
brief-mac_host_audit-YYYY-MM-DD_HH-MM-SS.md
brief-*-latest.md
brief-*-latest.json
```

Briefs may be copied to Mac:

```text
~/Documents/control-plane-reviews/briefs
```

Docs:

```text
docs/ai-ops-briefs.md
```

## Weekly ops review

The weekly ops review is the strategic AI review layer.

It aggregates one week of control-plane state and produces:

- executive summary
- top issues
- recurring patterns
- noise or expected events
- recommended actions
- audit domain rollups
- raw counters

Signal:

```text
WeeklyOpsReview
```

Flow:

```text
generate_weekly_ops_review
    -> copy_file_to_mac
    -> notify_tg
```

Artifacts on VPS:

```text
/srv/control-plane/state/reviews/weekly/
```

Examples:

```text
weekly-YYYY-MM-DD_HH-MM-SS.md
weekly-YYYY-MM-DD_HH-MM-SS.json
weekly-latest.md
weekly-latest.json
```

Copied to Mac:

```text
~/Documents/control-plane-reviews/weekly
```

Weekly currently includes these audit domains:

```text
admin_host_audit
vps_host_audit
monitoring_stack_audit
mac_host_audit
```

Latest domain posture is treated as the primary current signal. Historical warnings and criticals remain visible as recurring findings.

Docs:

```text
docs/weekly-ops-review-control-plane.md
```

## Remote Mac remediation

The Mac agent also supports guarded remediation tasks.

Flow:

```text
MacMemoryPressure
    -> execute_chain
    -> notify_tg
    -> enqueue_mac_action
    -> mac_action task
    -> Mac worker polls /tasks/mac/next
    -> Mac worker executes bounded remediation
    -> Mac worker posts /tasks/mac/complete
```

Task endpoints:

```text
GET  /tasks/mac/next
POST /tasks/mac/complete
```

This keeps Mac remediation constrained and task-driven.

## API surface

### Health and metrics

```text
GET /healthz
GET /metrics
```

### State inspection

```text
GET /runs
GET /runs/{id}
GET /tasks
GET /tasks/{id}
GET /decisions
GET /decisions/{id}
```

### Event ingestion

```text
POST /events/alertmanager
POST /events/mac-host-audit
```

### Manual action execution

```text
POST /actions/run
```

### Mac worker

```text
GET  /tasks/mac/next
POST /tasks/mac/complete
```

Docs:

```text
docs/api.md
```

## State model

SQLite database:

```text
state/action_runner.db
```

Main stored objects:

- decisions
- tasks
- runs
- locks
- cooldowns
- scheduled run tracking

This allows inspection of:

- what signal arrived
- what rule matched
- what decision was made
- what task was queued
- what action ran
- whether a chain succeeded or failed
- whether cooldown suppressed execution

## Artifacts

### AI briefs

```text
/srv/control-plane/state/reviews/briefs/
```

### Weekly reviews

```text
/srv/control-plane/state/reviews/weekly/
```

### Mac audit snapshots

```text
/srv/control-plane/state/mac-host-audit/
```

### Node exporter textfile metrics

```text
/var/lib/node_exporter/textfile_collector/
```

## Prometheus metrics

The service exports pipeline metrics through:

```text
GET /metrics
```

Metric areas include:

- decision counts
- task status counts
- run status counts
- queue depth
- latest timestamps
- Mac remediation results
- audit-derived metrics
- generated artifact state through stored runs/tasks

Audit-specific metrics are written to node exporter textfile collector files.

## Rules

Rules live in:

```text
action_runner/rules.yaml
```

A rule defines:

- name
- enabled state
- match criteria
- action type
- action payload
- chain steps
- cooldown

Supported action types:

```text
ignore
execute
chain
```

## Schedules

Schedules live in:

```text
action_runner/schedules.yaml
```

A schedule defines:

- name
- enabled state
- daily/weekday timing
- signal fields

The scheduler emits internal signals into the same pipeline as Alertmanager.

## Manual testing

### Compile check

```bash
python3 -m py_compile action_runner/*.py action_runner/actions/*.py
python3 -m py_compile agents/mac_memory_guard/*.py
```

### Restart service

```bash
sudo systemctl restart action-runner
systemctl status action-runner.service --no-pager -l
```

### Health check

```bash
curl -fsS http://127.0.0.1:8088/healthz | jq
```

### Generate weekly review directly

This only runs one action. It does not copy to Mac or notify Telegram.

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"generate_weekly_ops_review",
    "payload":{
      "days":7
    }
  }' | jq
```

### Trigger full weekly chain

This runs the full rule chain.

```bash
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver":"action-runner",
    "status":"firing",
    "alerts":[{
      "status":"firing",
      "labels":{
        "alertname":"WeeklyOpsReview",
        "severity":"info",
        "instance":"vps",
        "job":"manual"
      },
      "annotations":{
        "summary":"manual weekly ops review",
        "description":"manual trigger for weekly ops review chain"
      }
    }]
  }' | jq
```

### Publish Mac host audit snapshot from Mac

Run on Mac:

```bash
cd ~/scripts

ACTION_RUNNER_URL=http://100.126.22.101:8088 \
python3 -m mac_memory_guard.report_agent --publish-audit --no-publish
```

### Trigger Mac host audit chain

Run on VPS:

```bash
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver":"action-runner",
    "status":"firing",
    "alerts":[{
      "status":"firing",
      "labels":{
        "alertname":"MacHostAuditDaily",
        "severity":"info",
        "instance":"mba",
        "job":"manual"
      },
      "annotations":{
        "summary":"manual mac host audit refresh",
        "description":"manual trigger for mac host audit workflow"
      }
    }]
  }' | jq
```

Expected healthy result:

```text
verify_mac_host_audit      success
analyze_mac_host_audit     success
generate_ai_ops_brief      skipped
copy_file_to_mac           skipped
notify_tg                  skipped
```

## Important distinction

Direct action execution and full chain execution are different.

Direct action:

```text
POST /actions/run
```

Runs only one action.

Signal ingestion:

```text
POST /events/alertmanager
```

Runs rule evaluation and may queue a full chain.

For example:

```text
/actions/run generate_weekly_ops_review
```

only creates the weekly files.

But:

```text
/events/alertmanager with alertname=WeeklyOpsReview
```

runs:

```text
generate_weekly_ops_review
copy_file_to_mac
notify_tg
```

## Safety controls

### Cooldowns

Prevent repeated execution from noisy signals.

### Action locks

Prevent unsafe overlapping actions.

### Guarded Mac remediation

Mac remediation is task-based and bounded.

### AI as analysis only

AI-generated briefs and weekly reviews create artifacts and recommendations. They do not perform remediation directly.

## Integration with other repositories

Relationship:

```text
monitoring-stack
    -> Prometheus
    -> Alertmanager
    -> control-plane
        -> decisions / tasks / runs / remediation / briefs / weekly review
```

Related repositories:

- `monitoring-stack` — Prometheus, Alertmanager, Loki, Grafana, demo app, runbooks
- `infra` — bootstrap, backup, restore, and recovery automation

## Documentation index

```text
docs/api.md
docs/architecture.md
docs/admin-host-audit.md
docs/vps-host-audit.md
docs/monitoring-stack-audit.md
docs/mac-host-audit.md
docs/ai-ops-briefs.md
docs/weekly-ops-review-control-plane.md
```

## Current status

The project currently supports:

- alert ingestion
- scheduled workflows
- decision persistence
- queued task execution
- chained operational flows
- backup automation
- admin host audit
- VPS host audit
- monitoring stack audit
- Mac host audit
- remote Mac remediation
- AI ops briefs
- AI weekly review
- artifact delivery to Mac
- Prometheus metrics
- read-only API inspection
