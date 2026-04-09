# Control Plane Architecture

## Purpose

The control-plane receives selected alerts, evaluates policy, creates decisions, queues work, executes actions, and records outcomes.

It sits downstream from observability and acts as the orchestration layer between alerts and operational workflows.

---

## High-level role

The monitoring layer answers:

- what is happening

The control-plane answers:

- what should happen next

---

## System overview

```
monitoring-stack
    -> Prometheus
    -> Alertmanager
    -> control-plane
    -> decisions / tasks / runs / remediation
```

---

## Main architecture

```
Alertmanager
    │
    │ webhook
    ▼
action-runner
    │
    ├── normalize event
    ├── evaluate rule
    ├── create decision
    ├── queue task
    └── expose API + metrics
             │
             ▼
         task workers
             │
             ├── execute local action
             ├── execute chain
             ├── queue notify task
             └── create remote mac_action task
                        │
                        ▼
               mac_memory_guard agent
                        │
                        ├── poll next task
                        ├── perform guarded remediation
                        └── report task completion
```

---

## Core pipeline

```
alert
  -> decision
  -> task
  -> run
```

Expanded flow:

```
Alertmanager alert
    -> normalize event
    -> evaluate rule
    -> decision
    -> task creation
    -> worker execution
    -> action run result
    -> persisted state
```

---

## Main components

### 1. action-runner

The central orchestration service.

Responsibilities:

- receives Alertmanager webhooks
- normalizes incoming alerts
- loads and validates rules
- decides whether to ignore, execute, or execute a chain
- creates decisions, tasks, and runs
- persists state in SQLite
- exposes read-only inspection endpoints
- exports Prometheus metrics

### 2. Rule layer

Rules define:

- alert match criteria
- action type
- action steps
- cooldown behavior

Supported decision outcomes:

- ignore
- execute
- execute_chain
- cooldown

### 3. Task layer

Tasks separate decision-making from execution.

Task types currently include:

- action
- chain
- notify
- mac_action

This keeps orchestration structured and inspectable.

### 4. Execution layer

Workers poll pending tasks and execute them.

Execution can produce:

- a direct action run
- a chain result
- a queued notification task
- a remote remediation task

### 5. State layer

SQLite stores the operational audit trail.

Main state objects:

- decisions
- tasks
- runs
- action locks
- cooldown timestamps

### 6. Remote mac agent

The mac agent provides a remote execution target for memory-pressure remediation.

Responsibilities:

- report mac health context
- poll for mac_action tasks
- execute guarded local actions
- report completion back to control-plane

### 7. Backup workflow

Backup automation is also integrated into the control-plane.

A backup alert can become a multi-step chain such as:

- run_backup
- verify_backup
- notify_tg

---

## Decision model

### Ignore

```
alert -> decision stored -> no task -> no run
```

Used for policy exclusions and known-noise alerts.

### Execute

```
alert -> decision -> action task -> run
```

Used for single-step actions.

### Execute chain

```
alert -> decision -> chain task -> step execution -> multiple runs / queued tasks
```

Used for multi-step orchestration.

---

## Example flows

### Host reboot ignore path

```
HostRebootDetected
    -> decision: ignore
    -> decision stored
    -> no task
    -> no run
```

### Mac remediation distributed path

```
MacMemoryPressure critical
    -> decision: execute_chain
    -> chain task
    -> notify_tg
    -> enqueue_mac_action
    -> mac_action task
    -> remote mac worker executes remediation
```

### Backup orchestration path

```
BackupMissing critical
    -> decision: execute_chain
    -> chain task
    -> run_backup
    -> verify_backup
    -> notify_tg
```

---

## Safety controls

### Cooldowns

Successful execution can suppress repeated alert-triggered actions for a configured time window.

### Action locking

Certain actions are protected from concurrent execution.

This is especially important for:
	•	backup jobs
	•	stateful workflows
	•	non-overlapping operational tasks

### Guarded remote remediation

Remote mac execution is constrained through task-based remediation rather than unrestricted arbitrary command execution.

### Read-only visibility

The main HTTP surface is designed to support inspection and operational visibility.

---

## Visibility surfaces

The control-plane exposes:

- health endpoint
- Prometheus metrics
- read-only decisions view
- read-only tasks view
- read-only runs view

This allows the orchestration layer itself to be monitored by the separate monitoring stack.

---

## Summary

The control-plane is intentionally split into distinct layers:

- alert ingestion
- rule evaluation
- decision persistence
- task queueing
- execution
- run tracking
- remote remediation

This separation makes the system easier to reason about, test, and monitor.
