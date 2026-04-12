# VPS host audit

## Purpose

`vps_host_audit` is a daily operational snapshot of the VPS that runs `monitoring-stack` and `control-plane`.

It is not a replacement for Prometheus metrics.

It exists to produce:

- a log snapshot
- derived findings
- a summarized level: `ok | warning | critical`
- derived metrics for Grafana and Prometheus
- optional notification on non-OK outcomes

## Flow

    VpsHostAuditDaily
        -> run_vps_host_audit
        -> verify_vps_host_audit
        -> analyze_vps_host_audit
        -> notify_tg on warning/critical

## What it checks

- core systemd services
- Docker daemon and key containers
- local HTTP health probes
- root disk and inode usage
- memory and swap
- reboot-required signal
- fail2ban
- recent journal priority<=3 signal volume
- docker disk usage summary
- UFW posture
- Tailscale serve exposure

## Log path

    /var/log/vps-host-audit/

## Metrics path

    /var/lib/node_exporter/textfile_collector/vps_host_audit.prom

## Manual test

    curl -s http://127.0.0.1:8088/actions/run \
      --json '{
        "action":"run_vps_host_audit",
        "payload":{
          "log_dir":"/var/log/vps-host-audit"
        }
      }' | jq

    curl -s http://127.0.0.1:8088/actions/run \
      --json '{
        "action":"verify_vps_host_audit",
        "payload":{
          "log_dir":"/var/log/vps-host-audit",
          "max_age_seconds":1800
        }
      }' | jq

    curl -s http://127.0.0.1:8088/actions/run \
      --json '{
        "action":"analyze_vps_host_audit",
        "payload":{
          "log_dir":"/var/log/vps-host-audit",
          "metrics_path":"/var/lib/node_exporter/textfile_collector/vps_host_audit.prom"
        }
      }' | jq
