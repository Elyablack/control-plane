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

Alert-driven orchestration engine for operational workflows.

It receives monitoring and scheduler signals, evaluates rules, creates decisions, queues tasks, executes actions/chains, tracks outcomes, exports metrics, and generates bounded AI-assisted operational artifacts.

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
````

## What it includes

- Alertmanager ingestion
- internal scheduler
- rule-based decision engine
- queued task execution
- chained workflows
- cooldowns and action locking
- SQLite state tracking
- Telegram notifications
- remote Mac remediation
- backup workflow
- deterministic audit domains:
    
    - admin host audit
    - VPS host audit
    - monitoring stack audit
    - Mac host audit
    
- AI ops briefs for warning/critical audit results
- AI weekly ops review
- artifact copy to Mac
- Prometheus metrics

## Main workflows

```text
AdminHostAuditDaily
    -> run_admin_host_audit
    -> verify_admin_host_audit
    -> analyze_admin_host_audit
    -> optional AI brief / copy / notify
```

```text
VpsHostAuditDaily
    -> run_vps_host_audit
    -> verify_vps_host_audit
    -> analyze_vps_host_audit
    -> optional AI brief / copy / notify
```

```text
MonitoringStackAuditDaily
    -> run_monitoring_stack_audit
    -> verify_monitoring_stack_audit
    -> analyze_monitoring_stack_audit
    -> optional AI brief / copy / notify
```

```text
MacHostAuditDaily
    -> verify_mac_host_audit
    -> analyze_mac_host_audit
    -> optional AI brief / copy / notify
```

```text
WeeklyOpsReview
    -> generate_weekly_ops_review
    -> copy_file_to_mac
    -> notify_tg
```

## Important paths

```text
action_runner/rules.yaml
action_runner/schedules.yaml
state/action_runner.db
state/reviews/briefs/
state/reviews/weekly/
state/mac-host-audit/
```

## API

```text
GET  /healthz
GET  /metrics
GET  /runs
GET  /tasks
GET  /decisions

POST /events/alertmanager
POST /events/mac-host-audit
POST /actions/run

GET  /tasks/mac/next
POST /tasks/mac/complete
```

## Quick check

```text
python3 -m py_compile action_runner/*.py action_runner/actions/*.py
python3 -m py_compile agents/mac_memory_guard/*.py

sudo systemctl restart action-runner
curl -fsS http://127.0.0.1:8088/healthz | jq
```

## Documentation

- `docs/control-plane.md` — full project overview
- `docs/api.md` — API examples
- `docs/architecture.md` — architecture notes 
- `docs/admin-host-audit.md`
- `docs/vps-host-audit.md` 
- `docs/monitoring-stack-audit.md`
- `docs/mac-host-audit.md` 
- `docs/ai-ops-briefs.md` 
- `docs/weekly-ops-review-control-plane.md`

## License

MIT

