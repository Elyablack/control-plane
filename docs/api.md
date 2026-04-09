# Control Plane API

## Purpose

This document provides a practical overview of the main control-plane API endpoints.

Use it to:

- verify service health
- inspect decisions, tasks, and runs
- send synthetic alerts for testing
- inspect remote mac task flow

---

## Base URL

Typical local runner address:

```
http://127.0.0.1:8088
```

If the control-plane is exposed through the demo app, read-only views may also be available via the public UI.

---

## Endpoint groups

### Health and metrics

- GET /healthz
- GET /metrics

### Read-only pipeline state

- GET /decisions
- GET /decisions/{id}
- GET /tasks
- GET /tasks/{id}
- GET /runs
- GET /runs/{id}

### Alert and action ingestion

- POST /events/alertmanager
- POST /actions/run

### Remote mac task flow

- GET /tasks/mac/next
- POST /tasks/mac/complete

---

## Health

### GET /healthz

Checks whether the action-runner service is up.

Example:

```
curl -fsS http://127.0.0.1:8088/healthz | jq
```

Typical response:

```
{
  "status": "ok",
  "service": "action-runner",
  "rules_loaded": 4
}
```

--- 

## Metrics

### GET /metrics

Exports Prometheus metrics for the control-plane.

Example:

```
curl -fsS http://127.0.0.1:8088/metrics | head -n 40
```

Typical metric areas include:

- decisions by type
- tasks by type and status
- runs by action and status
- mac remediation result counts
- queue depth
- latest decision, task, and run timestamps

---

## Decisions

### GET /decisions

Returns recent decisions.

Example:

```
curl -fsS http://127.0.0.1:8088/decisions | jq
```

Typical response shape:

```
{
  "decisions": [
    {
      "id": 46,
      "source": "alertmanager",
      "alertname": "BackupMissing",
      "fingerprint": "…",
      "severity": "critical",
      "instance": "vps",
      "job": "node",
      "status": "firing",
      "summary": "Backup missing or stale",
      "decision": "execute_chain",
      "reason": "matched chain rule: backup_missing_chain",
      "action": "chain",
      "run_id": null,
      "created_at": "2026-04-08 03:05:47 UTC"
    }
  ]
}
```

### GET /decisions/{id}

Returns a single decision by ID.

Example:

```
curl -fsS http://127.0.0.1:8088/decisions/46 | jq
```

Use this to inspect:

- why the alert matched
- which decision type was selected
- whether an action or chain was associated

---

## Tasks

### GET /tasks

Returns recent tasks.

Example:

```
curl -fsS http://127.0.0.1:8088/tasks | jq
```

Typical response shape:

```
{
  "tasks": [
    {
      "id": 49,
      "decision_id": 46,
      "task_type": "chain",
      "payload": "{\"steps\": [...]}",
      "priority": 200,
      "status": "success",
      "created_at": "2026-04-08 03:05:47 UTC",
      "started_at": "2026-04-08 03:05:47 UTC",
      "finished_at": "2026-04-08 03:08:55 UTC",
      "result_json": "{\"status\": \"success\"}",
      "error": null
    }
  ]
}
```

### GET /tasks/{id}

Returns a single task by ID.

Example:

```
curl -fsS http://127.0.0.1:8088/tasks/49 | jq
```

Use this to inspect:

- task type
- original payload
- current status
- final result
- execution error if present

---

## Runs

### GET /runs

Returns recent action runs.

Example:

```
curl -fsS http://127.0.0.1:8088/runs | jq
```

Typical response shape:

```
{
  "runs": [
    {
      "id": 78,
      "action": "run_backup",
      "trigger_type": "task",
      "trigger_payload": "{\"...\": \"...\"}",
      "status": "success",
      "started_at": "2026-04-08 03:05:47 UTC",
      "finished_at": "2026-04-08 03:08:55 UTC",
      "exit_code": 0,
      "error": null
    }
  ]
}
```

### GET /runs/{id}

Returns a single run by ID.

Example:

```
curl -fsS http://127.0.0.1:8088/runs/78 | jq
```

Use this to inspect:

- action name
- trigger type
- trigger payload
- stdout
- stderr
- exit code
error details

---

## Manual action execution

### POST /actions/run

Executes a single allowed action manually.

Example:

```
curl -fsS http://127.0.0.1:8088/actions/run \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "notify_tg",
    "payload": {
      "message": "manual test",
      "description": "manual control-plane action test",
      "source": "manual",
      "event": "manual_test",
      "severity": "info",
      "status": "firing"
    }
  }' | jq
```

Typical response shape:

```
{
  "run_id": 90,
  "action": "notify_tg",
  "status": "success",
  "started_at": "2026-04-09 06:30:00 UTC",
  "finished_at": "2026-04-09 06:30:00 UTC",
  "exit_code": 0,
  "detail_url": "/runs/90"
}
```

Notes:

- only allowed actions can be executed
- action locking may return blocked
- the action result is persisted as a run

---

## Alert ingestion

### POST /events/alertmanager

Receives Alertmanager-style webhook payloads.

This is the main way to test alert-to-decision behavior.

Example:

```
curl -fsS http://127.0.0.1:8088/events/alertmanager \
  -H 'Content-Type: application/json' \
  -d '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "BackupMissing",
          "severity": "critical",
          "instance": "vps",
          "job": "node"
        },
        "annotations": {
          "summary": "Backup missing or stale",
          "description": "Last successful backup is older than 26 hours."
        }
      }
    ]
  }' | jq
```

Typical response shape:

```
{
  "status": "accepted",
  "alerts_received": 1,
  "decisions": [
    {
      "alertname": "BackupMissing",
      "status": "firing",
      "severity": "critical",
      "instance": "vps",
      "job": "node",
      "summary": "Backup missing or stale",
      "fingerprint": "…",
      "decision": "execute_chain",
      "reason": "matched chain rule: backup_missing_chain",
      "rule_name": "backup_missing_chain",
      "decision_id": 46,
      "task_id": 49,
      "steps": [
        { "name": "run_backup", "payload": {} },
        { "name": "verify_backup", "payload": {} },
        { "name": "notify_tg", "payload": { "...": "..." } }
      ]
    }
  ]
}
```

Use this endpoint to validate:

- ignore rules
- execute rules
- chain rules
- cooldown behavior
- task creation

---

## Remote mac task flow

### GET /tasks/mac/next

Used by the remote mac agent to poll the next mac_action task.

Example:

```
curl -fsS http://127.0.0.1:8088/tasks/mac/next | jq
```

Typical response shape when work exists:

```
{
  "task": {
    "id": 53,
    "decision_id": null,
    "task_type": "mac_action",
    "payload": "{\"action\": \"soft_quit_allowlisted_candidate\", \"instance\": \"mac-mini-test\"}",
    "priority": 200,
    "status": "pending",
    "created_at": "2026-04-08 04:05:14 UTC"
  }
}
```

Typical response shape when no work exists:

```
{
  "task": null
}
```

### POST /tasks/mac/complete

Used by the remote mac agent to report completion.

Example:

```
curl -fsS http://127.0.0.1:8088/tasks/mac/complete \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": 53,
    "status": "success",
    "result": {
      "status": "success",
      "task_id": 53,
      "action": "soft_quit_allowlisted_candidate",
      "target": "Safari",
      "instance": "mac-mini-test"
    }
  }' | jq
```

Typical response:

```
{
  "status": "ok"
}
```

Notes:

- if remediation fails, the control-plane may queue a follow-up notify task
- mac task completion updates the existing task state in SQLite

---

## Testing patterns

### Ignore path

Send an alert that matches an ignore rule and verify:

- decision exists
- no task created
- no run created

### Execute path

Send an alert that matches an execute rule and verify:

- decision exists
- action task created
- run created

### Chain path

Send an alert that matches a chain rule and verify:

- decision exists
- chain task created
- multiple runs or queued notify tasks created

### Distributed path

Send an alert that enqueues remote mac remediation and verify:

- chain decision exists
- mac_action task created
- remote agent polls task
- task completion is reported back

---

## Common response states

### Decision states

Typical values include:

- ignore
- execute
- execute_chain
- cooldown

### Task states

Typical values include:

- pending
- running
- success
- failed

### Run states

Typical values include:

- success
- failed
- blocked
- skipped

---

## Notes

The API is intentionally small and operational.

Use it to inspect the control-plane pipeline and validate alert-driven behavior end to end.
