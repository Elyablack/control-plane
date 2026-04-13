# Admin host audit in control-plane

This document captures the current admin-host audit design, why the logic was moved into `control-plane`, what was removed as legacy, and how to operate the workflow.

## Why this moved into control-plane

The original setup mixed together:

- local cron on `admin`
- local audit execution
- legacy config-copy paths
- ad hoc backup checks
- notification behavior

That became hard to reason about.

The current design keeps responsibilities separate:

- `admin` host:
  - exposes state
  - runs the audit script
  - stores Time Machine data
  - stores offsite VPS backup artifacts
  - exports node metrics

- `control-plane`:
  - schedules workflows
  - triggers remote audit execution
  - verifies results
  - analyzes audit output
  - emits notifications
  - writes derived metrics for Grafana/Prometheus
  - generates AI briefs only for meaningful non-OK outcomes

This keeps business logic out of the scheduler and out of the raw audit script.

---

## Current model

### Scheduler

Scheduler is intentionally simple.

It only decides that it is time to run a workflow, for example:

> run workflow `admin_host_audit_daily`

Scheduler does **not** know audit business logic.

### Workflow

The audit workflow lives in `control-plane` rules/chains.

Current chain shape:

1. `run_admin_host_audit`
2. `verify_admin_host_audit`
3. `analyze_admin_host_audit`
4. `generate_ai_ops_brief` only when analysis level is `warning` or `critical`
5. `copy_file_to_mac` only when analysis level is `warning` or `critical`
6. `notify_tg` only when analysis level is `warning` or `critical`

### Audit script on `admin`

`/usr/local/bin/admin_host_audit.sh` is an observation script.

It does **not** decide notifications.  
It does **not** decide scheduling.  
It does **not** perform remediation.

It only reports host state.

It supports three modes:

- `full`
- `host`
- `backup`

The control-plane workflow uses the full audit mode.

---

## Implemented remote actions

The admin-host audit flow is executed through `control-plane` actions.

### `run_admin_host_audit`

Runs the remote audit script on `admin`.

Default command:

```text
sudo /usr/local/bin/admin_host_audit.sh full
````

Expected result:

- audit log created in /var/log/admin-host-audit
- action returns success/failure and log path summary

### **verify_admin_host_audit**

Checks that the newest audit log exists, is non-empty, and is fresh enough.

Expected result:

- audit_verify=ok    
- log path
- log age

### **analyze_admin_host_audit**

Fetches the latest audit log, parses it, classifies findings, and writes derived metrics to the node exporter textfile collector.

Expected result:

- analysis_level    
- analysis_findings_count
- analysis_summary
- analysis_log_path
- metrics file updated on admin

### **generate_ai_ops_brief**

Runs only when the admin audit ends in a meaningful non-OK state.  

Expected result:

- markdown brief saved on VPS
- JSON brief saved on VPS
- brief status such as watch or risky
- markdown path injected into chain context

### **copy_file_to_mac**

Copies the generated markdown brief to Mac only for non-OK admin audit outcomes.

Expected target:

```
~/Documents/control-plane-reviews/briefs
```

### **notify_tg**

Sends a short Telegram message only for meaningful non-OK outcomes.

Current pattern:

- short title    
- brief status
- markdown file path
- short analyzer summary

---

## **Current audit sections**

The admin audit currently reports:

- NETWORK CHECK    
- MEMORY + SWAP
- BOOT STATE
- NETWORK + TAILSCALE
- SSH LISTEN
- UFW SUMMARY
- GETTY (active only)
- BACKLIGHT (brightness)
- TEMP (CPU/SSD)
- WIFI WATCHDOG
- FAIL2BAN (status only)
- DISK ROOT
- INODES
- SYSSTAT (summary)
- JOURNAL P3+ (current boot)
- DMESG TAIL (last 10 lines)
- REBOOT REQUIRED
- UPGRADES
- SMB SERVICES
- TIME MACHINE PATH
- TIME MACHINE FRESHNESS
- INFRA BACKUPS PATH
- INFRA BACKUPS FRESHNESS
- AUDIT LOG FRESHNESS
- SMART HEALTH

This script is intentionally operational and host-specific.

---

## **Findings currently derived by analysis**

The analyzer currently derives structured findings such as:

- external ping failure    
- DNS resolution failure
- SSH unhealthy
- Tailscale/network service unhealthy
- SMB unhealthy
- Time Machine path missing
- Time Machine path not writable
- infra-backups path missing
- infra-backups path not writable
- infra-backups archive/checksum mismatch
- stale infra-backups archive
- root filesystem usage elevated/high
- root inode usage elevated/high
- reboot required
- upgradable packages present
- fail2ban inactive
- sysstat unhealthy
- journald instability
- Broadcom Wi-Fi watchdog events
- elevated swap usage
- unclear SMART health

Overall analysis level is one of:

- ok    
- warning
- critical

---

## **Noise filtering**

The admin audit now filters some persistent low-value findings out of the final automation result.

Current noise policy:

- Broadcom Wi-Fi watchdog findings are treated as noise    
- small numbers of upgradable packages are treated as noise
- if only noise remains, final analysis_level becomes ok

This matters because otherwise the daily chain would always produce:

- AI brief    
- Mac file copy
- Telegram notification

for conditions that are already known and not actionable.

The raw audit still collects this information.
The difference is that these items no longer automatically trigger the non-OK automation path.

---

## **Notifications**

Notifications are sent from control-plane, not from the audit script.  

Current behavior:

- audit chain runs every day
- AI brief, Mac copy, and Telegram notification happen only when:
    - analysis_level == warning
    - or analysis_level == critical

If analysis is ok, those steps are skipped.

This keeps signal quality high and avoids treating persistent background noise as incidents.

---

## **Prometheus / Grafana integration**

analyze_admin_host_audit writes derived metrics to the node exporter textfile collector on admin.

Textfile path:

```
/var/lib/node_exporter/textfile_collector/admin_host_audit.prom
```

These metrics are then scraped through node exporter and visualized in Grafana.

### **Exported metric families**

Core audit metrics include:

- admin_host_audit_last_run_unixtime
- admin_host_audit_status{level=...}
- admin_host_audit_findings_count
- admin_host_audit_findings_count_by_severity{severity=...}
- admin_host_audit_upgradable_packages
- admin_host_audit_wifi_watchdog_events
- admin_host_audit_reboot_required
- admin_host_reboot_detected_recently
- admin_host_boot_time_unixtime
- admin_host_uptime_seconds
- admin_host_audit_timemachine_path_exists
- admin_host_audit_timemachine_path_writable
- admin_host_audit_infra_backups_path_exists
- admin_host_audit_infra_backups_path_writable
- admin_host_audit_smb_healthy
- admin_host_audit_ssh_healthy
- admin_host_audit_tailscale_healthy
- admin_host_audit_fail2ban_healthy
- admin_host_audit_root_disk_used_percent
- admin_host_audit_root_inode_used_percent
- admin_host_timemachine_age_seconds
- admin_host_audit_log_age_seconds
- admin_host_infra_backups_tar_age_seconds
- admin_host_infra_backups_sha_age_seconds
- admin_host_infra_backups_tar_count
- admin_host_infra_backups_sha_count
- admin_host_infra_backups_pairs_match
- admin_host_audit_finding_present{kind=...,severity=...}

---

## **Legacy pieces removed or deprecated**

### **Removed from active model**

#### **Local root cron audit**

Old root cron job:

```
0 4 * * 0 /usr/local/bin/mac_audit.sh >/dev/null 2>&1
```

This is no longer needed because audit scheduling is now handled by control-plane.

#### **Legacy/backup/configs flow**

Old root cron job:

```
0 3 * * 0 rsync -a --delete /etc /backup/configs/
```

This created /backup/configs/etc and represented an old config-copy flow.
This path is no longer treated as a current source of truth for admin-host backup health.

It was removed from:

- audit sections    
- analyzer findings
- exported metrics
- Grafana dashboard

### **Deprecated Mac rsync flow**

The old Mac-side launchd + rsync workflow was moved out of the active design.

Reasons:

- macOS privacy/TCC issues on Documents and Desktop    
- broken or nonexistent path usage
- unreliable SSH reachability to admin
- duplicated intent with Time Machine

Current primary Mac backup model is Time Machine over SMB.

---

## **Backup model: current truth**

### **Primary Mac backup**

Primary Mac backup is:

- Time Machine over SMB    
- stored on admin
- monitored via:
    - SMB health
    - Time Machine path existence/writability
    - Time Machine freshness

### **VPS offsite backup receiving side**

admin also acts as the offsite receiving side for daily VPS backup artifacts.

Current flow:

1. VPS systemd timer runs control-plane-backup.service    
2. /srv/control-plane/backup/run_backup.sh creates a backup archive on VPS
3. a sha256 checksum is generated
4. /srv/control-plane/backup/offsite_copy.sh copies both files to:

```
/home/admin1/infra-backups
```

5. old files are pruned on both VPS and admin, keeping 7
    
The admin-host audit monitors this receiving side via:

- infra-backups path existence
- infra-backups path writability
- latest archive age
- latest checksum age
- archive count
- checksum count
- pair consistency

### **What is not considered primary anymore**

These are not part of the current primary backup path:

- old launchd rsync from Mac    
- old /backup/configs config-copy snapshot

---

## **Why reboot remediation was not automated**

A reboot/backlight-remediation path was considered, but intentionally not automated.

Reasoning:

- the actual action is trivial    
- manual reboots on admin are acceptable
- the cost of adding intent markers, reboot classification, and remediation chains was not justified
- current visibility is already sufficient through:
    - audit metrics
    - Grafana
    - Telegram notifications after analysis

Current policy:

- reboot of admin is handled manually when needed
- audit reports reboot-related state
- no automatic reboot remediation is applied

---

## **Operational commands**

### **Run audit directly on admin**

```
sudo /usr/local/bin/admin_host_audit.sh full
sudo /usr/local/bin/admin_host_audit.sh host
sudo /usr/local/bin/admin_host_audit.sh backup
```

### **Inspect latest audit log on admin**

```
sudo ls -1t /var/log/admin-host-audit/audit_*.log | head -n1
sudo tail -n 120 "$(ls -1t /var/log/admin-host-audit/audit_*.log | head -n1)"
```

### **Trigger full analysis from control-plane**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"analyze_admin_host_audit",
    "payload":{
      "host":"admin",
      "log_dir":"/var/log/admin-host-audit"
    }
  }' | jq
```

### **Trigger full daily chain manually**

```
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "AdminHostAuditDaily",
          "severity": "info",
          "instance": "admin",
          "job": "manual"
        },
        "annotations": {
          "summary": "manual admin host audit full chain test",
          "description": "manual trigger for admin host audit workflow"
        }
      }
    ]
  }' | jq
```

### **Inspect latest run / task / decision**

```
curl -s http://127.0.0.1:8088/runs | jq
curl -s http://127.0.0.1:8088/tasks | jq
curl -s http://127.0.0.1:8088/decisions | jq
```

### **Check generated audit metrics on admin**

```
sudo cat /var/lib/node_exporter/textfile_collector/admin_host_audit.prom
```

### **Check metrics through node exporter**

```
curl -s http://127.0.0.1:9100/metrics | grep admin_host_
```

### **Check metrics remotely from control-plane**

```
curl -s http://100.103.137.9:9100/metrics | grep admin_host_
```

---

## **Design rules to keep Scheduler stays simple**

Scheduler only triggers workflows.
It should not embed audit-specific logic.

### **Audit script stays observational**

`admin_host_audit.sh` reports state.
It should not own notification logic.
It should not own scheduling.
It should not silently remediate.

### **Analyzer owns interpretation**

`admin_audit.py` converts raw audit text into structured findings and metrics.
It also owns noise filtering for persistent low-value findings.

### **Control-plane owns orchestration**

Workflow chaining, conditional brief generation, file copy, and notify behavior belong in control-plane.

---

## **Current status summary**

The admin-host audit is now a control-plane-managed workflow with:

- daily scheduled execution    
- remote audit invocation
- freshness verification
- structured analysis
- noise filtering for persistent Wi-Fi/package background findings
- AI brief generation only on meaningful non-OK outcomes
- Mac copy only on meaningful non-OK outcomes
- Telegram notifications only on meaningful non-OK outcomes
- Prometheus/Grafana integration
- legacy /backup/configs path removed from active monitoring
- Time Machine retained as the primary Mac backup signal
- infra-backups monitored as the offsite VPS backup receiving path
  

This is the current intended architecture.
