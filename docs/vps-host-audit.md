# VPS host audit

## Purpose

`vps_host_audit` is a daily operational snapshot of the VPS that runs both `monitoring-stack` and `control-plane`.

It is not a replacement for Prometheus metrics and does not try to duplicate raw metric collection.

Its role is different:

- collect a bounded host snapshot
- analyze that snapshot into derived findings
- classify the result as `ok | warning | critical`
- export derived metrics through node_exporter textfile collector
- optionally trigger AI brief generation and operator notification on non-OK outcomes

This gives the control-plane a deterministic audit layer on top of raw infrastructure signals.

---

## Flow

```
VpsHostAuditDaily
    -> run_vps_host_audit
    -> verify_vps_host_audit
    -> analyze_vps_host_audit
    -> generate_ai_ops_brief           (only on warning/critical)
    -> copy_file_to_mac                (only on warning/critical)
    -> notify_tg                       (only on warning/critical)
````

The audit flow is event-driven through the action-runner rule engine and scheduler.

No cron is used.

---

## **What it checks**

The VPS audit is focused on the host as an execution environment for monitoring-stack and control-plane.

Current scope includes:

- core systemd unit health    
- Docker daemon reachability
- key monitoring/control-plane containers
- local HTTP service probes
- root filesystem usage
- inode usage
- swap usage
- reboot-required signal
- fail2ban status
- recent journal priority <=3 volume
- UFW posture
- Tailscale serve exposure
- docker runtime state summary

This is intentionally an operational audit, not a full security benchmark.

---

## **Artifacts**

### **Audit logs**

```
/var/log/vps-host-audit/
```

### **Derived metrics**

```
/var/lib/node_exporter/textfile_collector/vps_host_audit.prom
```

### **AI briefs**

```
/srv/control-plane/state/reviews/briefs/
```

Examples:

- brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.md
- brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.json
- brief-vps_host_audit-latest.md
- brief-vps_host_audit-latest.json

### **Copied brief location on Mac**

```
~/Documents/control-plane-reviews/briefs
```

---

## **Status model**

analyze_vps_host_audit emits a summarized level:

- ok
- warning
- critical

Behavior by level:

- ok
    - metrics are updated    
    - no AI brief
    - no file copy
    - no Telegram notification
    
- warning or critical
    - metrics are updated
    - AI brief is generated
    - markdown brief is copied to Mac
    - short Telegram notification is sent

This keeps the normal daily path quiet while preserving operator visibility for non-OK outcomes.

---

## **AI brief layer**

The VPS audit does not contain domain-specific LLM logic inside the analyzer.

Instead it reuses the shared action:

- generate_ai_ops_brief
    

This action receives structured analyzer output such as:

- analysis_level    
- analysis_summary
- analysis_findings_count
- analysis_log_path
    
and produces:

- short markdown brief
- JSON artifact
- concise operator summary for downstream notification

This keeps the audit deterministic and moves interpretation into a shared AI layer.

---

## **Rule chain**

Current VPS rule shape:

```
run_vps_host_audit
-> verify_vps_host_audit
-> analyze_vps_host_audit
-> generate_ai_ops_brief        when analysis_level in [warning, critical]
-> copy_file_to_mac             when analysis_level in [warning, critical]
-> notify_tg                    when analysis_level in [warning, critical]
```

---

## **Scheduler**  

This flow is scheduled through action_runner/schedules.yaml.

Current intent:

- run daily    
- emit internal signal VpsHostAuditDaily
- let the rule engine decide and execute the chain
    
The scheduler supports:

- weekday
- weekdays
- daily: true

The VPS audit uses daily: true.

---

## **Manual tests**  

### **Run audit step directly**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"run_vps_host_audit",
    "payload":{
      "log_dir":"/var/log/vps-host-audit"
    }
  }' | jq
```

### **Verify latest audit log**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"verify_vps_host_audit",
    "payload":{
      "log_dir":"/var/log/vps-host-audit",
      "max_age_seconds":1800
    }
  }' | jq
```

### **Analyze audit and export metrics**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"analyze_vps_host_audit",
    "payload":{
      "log_dir":"/var/log/vps-host-audit",
      "metrics_path":"/var/lib/node_exporter/textfile_collector/vps_host_audit.prom"
    }
  }' | jq
```

### **Generate AI brief directly**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"generate_ai_ops_brief",
    "payload":{
      "source":"vps_host_audit",
      "analysis_level":"warning",
      "analysis_summary":"warning:journal priority<=3 count 50",
      "analysis_findings_count":1,
      "analysis_log_path":"/var/log/vps-host-audit/audit_example.log",
      "facts":{
        "host":"vps",
        "metrics_path":"/var/lib/node_exporter/textfile_collector/vps_host_audit.prom"
      }
    }
  }' | jq
```

### **Trigger full chain through signal ingestion**

```
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "VpsHostAuditDaily",
          "severity": "info",
          "instance": "vps",
          "job": "manual"
        },
        "annotations": {
          "summary": "manual vps host audit full chain test",
          "description": "manual trigger for vps host audit workflow"
        }
      }
    ]
  }' | jq
```

---

## **Verification commands**

Inspect the latest chain:

```
ar-chain
ar-run
ar-task
```

Check recent audit logs:

```
ls -lt /var/log/vps-host-audit | head
```

Check exported metrics:

```
cat /var/lib/node_exporter/textfile_collector/vps_host_audit.prom
```

Check generated AI briefs on VPS:

```
ls -lt /srv/control-plane/state/reviews/briefs | head
readlink -f /srv/control-plane/state/reviews/briefs/brief-vps_host_audit-latest.md
```

Check copied briefs on Mac:

```
ssh mac 'ls -lt ~/Documents/control-plane-reviews/briefs | head'
```

---

## **Operational notes**

### **Permissions**

This flow depends on a few local permission assumptions:

- action-runner must be able to execute the audit script    
- action-runner must be able to write the node_exporter textfile output
- if UFW status is collected through sudo -n, the required sudoers rule must exist
    
### **Expected quiet state**

The audit is considered healthy when:

- run_vps_host_audit succeeds    
- verify_vps_host_audit succeeds
- analyze_vps_host_audit emits ok
- metrics update successfully
- no brief/notification path is triggered

### **Expected non-OK state**

On warning or critical, the flow is considered working when:

- analyzer emits non-OK result    
- AI brief is generated
- brief is copied to Mac
- short Telegram message is delivered

---

## **Current status**

The VPS host audit flow is currently considered implemented when:

- daily scheduling works    
- deterministic audit works
- derived metrics are exported
- non-OK outcomes produce AI brief artifacts
- briefs are copied to Mac
- Telegram notifications stay short and bounded
