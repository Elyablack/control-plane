# Weekly ops review flow

## What it does

The weekly ops review flow now does three things in sequence:

1. generates a weekly review snapshot on `vps`
2. copies the generated markdown review to `Mac`
3. sends a Telegram notification

## Current artifact locations

On `vps`:

- `state/reviews/weekly-YYYY-MM-DD_HH-MM-SS.md`
- `state/reviews/weekly-YYYY-MM-DD_HH-MM-SS.json`
- `state/reviews/weekly-latest.md`
- `state/reviews/weekly-latest.json`

On `Mac`:

- `~/Documents/control-plane-reviews/`

## Action layout

### Low-level transport

`action_runner/tools.py`

Contains:
- `ssh_run(...)`
- `scp_copy_to_remote(...)`

These are transport primitives only.

### Domain action

`action_runner/actions/mac_file.py`

Contains:
- `copy_file_to_mac(payload)`

This is a workflow action, not a low-level tool.

It:
- validates `source_path`
- ensures the remote directory exists on Mac
- copies the file over SSH/SCP
- returns normalized `ActionResult`

## Config

`action_runner/config.py`

Relevant config:

- `MAC_REVIEW_SSH_TARGET`
- `MAC_REVIEW_DOCS_DIR`
- `MAC_REVIEW_COPY_TIMEOUT_SECONDS`

Current expected values:

- `MAC_REVIEW_SSH_TARGET=mac`
- `MAC_REVIEW_DOCS_DIR=~/Documents/control-plane-reviews`
- `MAC_REVIEW_COPY_TIMEOUT_SECONDS=30`

## SSH requirement

The `action-runner` service runs as user `admin1`.

Therefore:
- `admin1` on `vps` must have a working `~/.ssh/config`
- alias `mac` must resolve correctly
- SSH and SCP to `mac` must work without password

Validated manually with:

```text
ssh mac 'mkdir -p ~/Documents/control-plane-reviews && ls -ld ~/Documents/control-plane-reviews'
scp /srv/control-plane/state/reviews/weekly-latest.md mac:~/Documents/control-plane-reviews/
```

## Weekly chain

The weekly chain order is:

1. `generate_weekly_ops_review`
2. `copy_file_to_mac`
3. `notify_tg`

## Manual tests

### Test review generation directly

```text
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"generate_weekly_ops_review",
    "payload":{
      "days":7
    }
  }' | jq
```

### Test file copy directly

```text
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"copy_file_to_mac",
    "payload":{
      "source_path":"/srv/control-plane/state/reviews/weekly-latest.md"
    }
  }' | jq
```

### Test full chain through signal ingestion

```text
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "WeeklyOpsReview",
          "severity": "info",
          "instance": "vps",
          "job": "manual"
        },
        "annotations": {
          "summary": "manual weekly ops review test",
          "description": "manual trigger for weekly ops review chain"
        }
      }
    ]
  }' | jq
```

## Verification commands

Check runner state:

```text
ar-decision
ar-task
ar-run
```

Check generated files on `vps`:

```text
ls -lt /srv/control-plane/state/reviews | head
cat /srv/control-plane/state/reviews/weekly-latest.md
```

Check copied files on `Mac`:

```text
ssh mac 'ls -lt ~/Documents/control-plane-reviews | head'
```

## Scheduler

This flow is triggered by the built-in action-runner scheduler through `schedules.yaml`.

No cron is used.

Current weekly schedule is expected to emit signal:

- `alertname=WeeklyOpsReview`
- `status=firing`
- `severity=info`

The rule then maps that signal to the weekly chain.

## Retention

Review snapshots are timestamped.

Examples:

- `weekly-2026-04-12_03-22-39.md`
- `weekly-2026-04-12_03-22-39.json`

`weekly-latest.md` and `weekly-latest.json` are symlinks to the newest snapshot.

Retention is controlled by:

- `retention_count`

Current default:
- keep last `10` snapshots per file type

## Current status

Current weekly ops review flow is considered working when:

- review snapshot is generated on `vps`
- markdown review is copied to `Mac`
- Telegram notification is sent
- scheduler can trigger the same chain without manual input
