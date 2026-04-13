# Monitoring stack audit

## Purpose

`monitoring_stack_audit` is a deterministic daily audit of the observability and notification stack running on the VPS.

It does not replace Prometheus alerting.

Its purpose is different:

- collect a bounded operational snapshot of the monitoring stack
- verify that the snapshot was produced correctly
- analyze the snapshot into derived findings
- classify the result as `ok | warning | critical`
- export derived metrics through node_exporter textfile collector
- trigger AI brief generation only on non-OK outcomes

This gives the control-plane a separate audit layer for the monitoring runtime itself.

---

## Flow

```
MonitoringStackAuditDaily
    -> run_monitoring_stack_audit
    -> verify_monitoring_stack_audit
    -> analyze_monitoring_stack_audit
    -> generate_ai_ops_brief           (only on warning/critical)
    -> copy_file_to_mac                (only on warning/critical)
    -> notify_tg                       (only on warning/critical)
````

No cron is used.

The flow is triggered by the built-in action-runner scheduler and rule engine.

---

## **What it audits**

The audit is focused on the monitoring-stack as a working system, not just as a set of containers.

Current scope includes:

### **Core stack components**

- prometheus    
- alertmanager
- grafana
- loki
- promtail
- tg-relay

### **Canary workload**

- demo-app
    
demo-app is intentionally treated as a canary workload, not as a core observability dependency.
If demo-app is unhealthy, that is a useful warning signal for end-to-end behavior, but it should not automatically mean the observability stack itself is down.

---

## **Checks performed**

### **Container runtime checks**

For each relevant container the audit records:

- existence    
- runtime state
- health status if present
- image
- status text

### **Local HTTP probes**

Current local probes:

```
prometheus    -> http://127.0.0.1:9090/-/ready
alertmanager  -> http://127.0.0.1:9093/-/ready
grafana       -> http://127.0.0.1:3000/api/health
loki          -> http://127.0.0.1:3100/ready
promtail      -> http://127.0.0.1:9080/ready
tg-relay      -> http://127.0.0.1:8082/readyz
demo-app      -> http://127.0.0.1:8081/healthz
```

### **Prometheus semantic checks**

The audit also queries Prometheus directly and verifies key targets:

- nodes{node="vps"}
- nodes{node="admin"}
- action-runner
- demo-app

It also records:

- required targets down count
- total targets down count
- demo-app 5xx rate
- demo-app p95 latency

This is the main difference between monitoring_stack_audit and vps_host_audit.

vps_host_audit checks the host.

monitoring_stack_audit checks whether observability is functioning as a system.

---

## **Artifact locations**

### **Logs**

```
/var/log/monitoring-stack-audit/
```

### **Derived metrics**

```
/var/lib/node_exporter/textfile_collector/monitoring_stack_audit.prom
```

### **AI briefs on VPS**

```
/srv/control-plane/state/reviews/briefs/
```

Examples:

- brief-monitoring_stack_audit-YYYY-MM-DD_HH-MM-SS.md
- brief-monitoring_stack_audit-YYYY-MM-DD_HH-MM-SS.json

### **Copied brief location on Mac**

```
~/Documents/control-plane-reviews/briefs
```

---

## **Status model**

analyze_monitoring_stack_audit emits one of:

- ok    
- warning
- critical

### **ok**

When core components are healthy, required targets are up, and the stack shows no meaningful degradation.

In this case:

- metrics are exported    
- no AI brief is generated
- no file is copied to Mac
- no Telegram message is sent

### **warning**

Used for partial degradation or canary issues, for example:

- promtail unavailable    
- demo-app unhealthy
- demo-app elevated 5xx
- demo-app p95 latency elevated
- non-core target down
- container restarting
    
### **critical**

Used when the monitoring runtime itself is at risk, for example:

- prometheus unavailable    
- alertmanager unavailable
- grafana unavailable
- loki unavailable
- tg-relay unavailable
- Prometheus query API failed
- required scrape targets down

---

## **Why alerts and audits both exist**

This flow does not replace Prometheus alerting.

The two layers serve different roles:

### **Alerts**

Alerts are the fast realtime layer.

They answer:

- what symptom is firing right now    
- what threshold was crossed
- should the operator be paged or notified now

Examples:

- NodeExporterDown
- DemoAppDown
- DemoAppHigh5xxRate

### **Audits**

Audits are the synthesized scheduled layer.

They answer:

- is the stack healthy overall    
- are multiple symptoms connected
- what is the current system-level posture
- what should be interpreted as noise vs risk

### **Practical model**

The intended architecture is:

```
Prometheus alert
    -> fast detection

Scheduled audit
    -> system snapshot
    -> derived findings
    -> optional AI brief
```

This means the same domain can be observed from both angles:

- alerts for fast change detection
- audits for bounded summary and context

---

## **AI brief behavior**  

On warning or critical, the audit reuses the shared action:

- generate_ai_ops_brief
  
That action receives structured analyzer output such as:

- analysis_level  
- analysis_summary
- analysis_findings_count
- analysis_log_path

and produces:

- markdown brief    
- JSON artifact
- concise executive summary
- brief status such as stable | watch | risky

The markdown brief is the durable artifact.

Telegram stays short.

---

## **Telegram behavior**  

The Telegram message is intentionally compact.

Current pattern:

- short title    
- brief status
- markdown file path
- short analyzer summary

Example:

```
[STACK][WARNING] audit brief

brief: watch
file: /srv/control-plane/state/reviews/briefs/brief-monitoring_stack_audit-...
warning:demo-app 5xx rate 0.0231/s
```

This avoids long AI text in Telegram while preserving the full markdown artifact.

---

## **Metrics exported**

The analyzer exports derived metrics such as:

- monitoring_stack_audit_status
- monitoring_stack_audit_findings_count
- monitoring_stack_audit_findings_count_by_severity
- monitoring_stack_prometheus_healthy
- monitoring_stack_alertmanager_healthy
- monitoring_stack_grafana_healthy
- monitoring_stack_loki_healthy
- monitoring_stack_promtail_healthy
- monitoring_stack_tg_relay_healthy
- monitoring_stack_demo_app_healthy
- monitoring_stack_core_targets_down
- monitoring_stack_noncore_targets_down
- monitoring_stack_demo_app_5xx_rate
- monitoring_stack_demo_app_p95_latency_seconds
- monitoring_stack_audit_finding_present{kind=...,severity=...}

This makes the audit visible in Prometheus and Grafana as a first-class synthesized signal.

---

## **Manual tests**

### **Run the snapshot step**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"run_monitoring_stack_audit",
    "payload":{
      "log_dir":"/var/log/monitoring-stack-audit"
    }
  }' | jq
```

### **Verify latest snapshot**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"verify_monitoring_stack_audit",
    "payload":{
      "log_dir":"/var/log/monitoring-stack-audit",
      "max_age_seconds":1800
    }
  }' | jq
```

### **Analyze and export metrics**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"analyze_monitoring_stack_audit",
    "payload":{
      "log_dir":"/var/log/monitoring-stack-audit",
      "metrics_path":"/var/lib/node_exporter/textfile_collector/monitoring_stack_audit.prom"
    }
  }' | jq
```

### **Trigger full chain manually**

```
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "MonitoringStackAuditDaily",
          "severity": "info",
          "instance": "vps",
          "job": "manual"
        },
        "annotations": {
          "summary": "manual monitoring stack audit full chain test",
          "description": "manual trigger for monitoring stack audit workflow"
        }
      }
    ]
  }' | jq
```

---

## **Verification commands**

Check latest chain state:

```
ar-chain
ar-run
ar-task
ar-runs 10
```

Check latest audit logs:

```
ls -lt /var/log/monitoring-stack-audit | head
latest=$(ls -t /var/log/monitoring-stack-audit/audit_*.log | head -1)
sed -n '1,240p' "$latest"
```

Check exported metrics:

```
cat /var/lib/node_exporter/textfile_collector/monitoring_stack_audit.prom
```

Check copied briefs on Mac:

```
ssh mac 'ls -lt ~/Documents/control-plane-reviews/briefs | head'
```

---

## **Scheduler**

This flow is triggered through schedules.yaml.

No cron is used.

Current intended signal:

- alertname=MonitoringStackAuditDaily    
- status=firing
- severity=info

The rule maps that signal to the monitoring stack audit chain.

---

## **Current status**

The monitoring stack audit is considered working when:

- the snapshot log is generated successfully    
- verify succeeds
- analyzer exports metrics successfully
- ok outcomes stay quiet
- warning or critical outcomes generate AI brief, Mac copy, and short Telegram notification
