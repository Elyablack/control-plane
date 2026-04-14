# Mac host audit

## Purpose

`mac_host_audit` is a lightweight audit domain for the Mac host.

It collects operational state from the existing `mac_memory_guard` agent and sends a JSON snapshot to `control-plane`.

It is not an SSH-based audit. The Mac agent is the source of truth.

## Flow

```text
mac_memory_guard report agent
    -> POST /events/mac-host-audit
    -> save latest JSON snapshot on VPS
    -> MacHostAuditDaily scheduler signal
    -> verify_mac_host_audit
    -> analyze_mac_host_audit
    -> generate_ai_ops_brief on warning/critical
    -> copy_file_to_mac on warning/critical
    -> notify_tg on warning/critical
    -> weekly ops review includes mac_host_audit as a domain
```

## Snapshot ingestion

Endpoint:

```text
POST /events/mac-host-audit
```

Snapshot storage on VPS:

```text
/srv/control-plane/state/mac-host-audit/
```

Current files:

```text
audit_YYYYMMDD_HHMMSS.json
latest.json -> audit_YYYYMMDD_HHMMSS.json
```

## Collected facts

The Mac agent currently reports:

- host label
- timestamp
- memory free percent
- swap used MB
- uptime days
- root disk used percent
- battery percent
- power source
- latest Time Machine backup path
- brew outdated package count
- launchd loaded/running state for Mac memory guard jobs
- top memory processes

## Actions

### `verify_mac_host_audit`

Checks that a recent Mac audit snapshot exists.

Default audit dir:

```text
/srv/control-plane/state/mac-host-audit
```

Typical max age:

```text
1800 seconds
```

### `analyze_mac_host_audit`

Loads the latest snapshot, derives findings, writes metrics, and returns:

- `analysis_level`
- `analysis_findings_count`
- `analysis_summary`
- `analysis_log_path`
- `metrics_path`

Metrics path:

```text
/var/lib/node_exporter/textfile_collector/mac_host_audit.prom
```

## Analysis levels

Possible levels:

```text
ok
warning
critical
```

Current examples:

```text
ok:no findings
warning:memory free 8%
warning:swap used 5000MB
warning:mac memory guard launchd jobs not loaded
```

For launchd interval jobs, `loaded=true` is enough.

`running=false` is not treated as a warning because periodic jobs are normally idle between runs.

## Scheduler

The daily schedule emits:

```text
alertname=MacHostAuditDaily
status=firing
severity=info
instance=mba
job=scheduler
```

Expected schedule:

```text
04:45 UTC daily
```

## Rule chain

Current chain:

```text
MacHostAuditDaily
    -> verify_mac_host_audit
    -> analyze_mac_host_audit
    -> generate_ai_ops_brief      only on warning/critical
    -> copy_file_to_mac           only on warning/critical
    -> notify_tg                  only on warning/critical
```

Healthy snapshots stop after analysis.

Warning or critical snapshots produce:

- AI brief markdown/json
- copied brief on Mac
- Telegram notification

## Mac agent launchd

Report agent plist:

```text
~/Library/LaunchAgents/com.elvira.mac-memory-report.plist
```

Worker agent plist:

```text
~/Library/LaunchAgents/com.elvira.mac-memory-worker.plist
```

The report agent must run with:

```text
-m mac_memory_guard.report_agent --publish-audit
```

Working directory:

```text
/Users/elvira/scripts
```

Required environment variable:

```text
ACTION_RUNNER_URL=http://100.126.22.101:8088
```

`100.126.22.101` is the VPS Tailscale IP.

## Manual tests

### Publish real snapshot from Mac

Run on Mac:

```bash
cd ~/scripts

ACTION_RUNNER_URL=http://100.126.22.101:8088 \
python3 -m mac_memory_guard.report_agent --publish-audit --no-publish
```

### Check snapshot on VPS

```bash
ls -lt /srv/control-plane/state/mac-host-audit | head
cat /srv/control-plane/state/mac-host-audit/latest.json | jq
```

### Verify snapshot

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"verify_mac_host_audit",
    "payload":{
      "audit_dir":"/srv/control-plane/state/mac-host-audit",
      "max_age_seconds":1800
    }
  }' | jq
```

### Analyze snapshot

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"analyze_mac_host_audit",
    "payload":{
      "audit_dir":"/srv/control-plane/state/mac-host-audit",
      "metrics_path":"/var/lib/node_exporter/textfile_collector/mac_host_audit.prom"
    }
  }' | jq
```

### Trigger full chain

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

ar-chain
```

Expected healthy result:

```text
verify_mac_host_audit      success
analyze_mac_host_audit     success
generate_ai_ops_brief      skipped
copy_file_to_mac           skipped
notify_tg                  skipped
```

## Weekly review integration

`mac_host_audit` is included as the fourth audit domain in weekly review.

Weekly domains:

```text
admin_host_audit
vps_host_audit
monitoring_stack_audit
mac_host_audit
```

The weekly review uses latest domain posture as the primary signal.

Historical warnings remain visible under recurring findings, but if latest posture is `ok`, the current domain posture is treated as recovered.

## Design notes

The Mac audit intentionally uses agent-published snapshots instead of SSH.

Reasons:

- the Mac already has a local agent
- macOS state is easier to collect locally
- no additional remote shell path is needed
- the same control-plane workflow model can still verify, analyze, brief, copy, notify, and summarize the result

## Current status

The Mac host audit is considered working when:

- Mac report agent publishes snapshots to VPS
- `/events/mac-host-audit` stores `latest.json`
- `verify_mac_host_audit` succeeds
- `analyze_mac_host_audit` succeeds
- `mac_host_audit.prom` is written
- `MacHostAuditDaily` chain succeeds
- warning/critical snapshots generate AI briefs and Telegram notifications
- weekly ops review includes Mac host audit
