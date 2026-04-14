# Weekly ops review flow

## Purpose

The weekly ops review is the higher-level AI review layer for the control-plane.

It does not replace deterministic audits.

Instead, it aggregates one week of operational state and produces a bounded operator-facing summary that answers:

- what mattered this week
- which issues repeated
- what recovered
- what was probably noise
- what should be fixed first

This is the strategic review layer above the day-to-day audit flows.

## Flow

```text
WeeklyOpsReview
    -> generate_weekly_ops_review
    -> copy_file_to_mac
    -> notify_tg
```

## Direct action vs full chain

Running the action directly only generates files:

```text
POST /actions/run
action=generate_weekly_ops_review
```

Running the signal goes through rules and executes the full chain:

```text
POST /events/alertmanager
alertname=WeeklyOpsReview
```

The full chain generates the review, copies it to Mac, and sends Telegram notification.

## Inputs

`generate_weekly_ops_review` summarizes the last 7 days of control-plane state from SQLite.

It currently includes:

- decisions
- tasks
- runs
- top alerts
- backup runs
- latest operational failures
- Mac memory pressure decisions
- Mac remediation tasks
- recent successful AI ops briefs
- audit domain rollups

Current audit domains:

```text
admin_host_audit
vps_host_audit
monitoring_stack_audit
mac_host_audit
```

This gives the weekly review both deterministic signal history and bounded AI brief context.

## Audit domain model

Each audit domain contributes:

- total runs
- OK count
- warning count
- critical count
- latest level
- latest summary
- latest run timestamp
- recurring findings

The weekly review treats latest domain posture as the primary current signal.

Historical warning and critical findings remain visible under recurring findings, but if the latest posture is `ok`, the domain is considered recovered for current posture.

## Current posture policy

The weekly status is one of:

```text
quiet
stable
watch
risky
```

The model can classify the week as risky if the historical incident density is high.

Post-processing can downgrade `risky` to `watch` when all audit domains have recovered to latest `ok`, while still preserving historical issues in the report.

This keeps the weekly report useful:

- current state reflects recovery
- historical risk remains visible
- recommendations still include recurrence prevention

## Artifact locations

### On VPS

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

### On Mac

```text
~/Documents/control-plane-reviews/weekly
```

## JSON artifact

The JSON artifact stores:

- generation timestamp
- weekly summary input
- model review output

It is intended for machine use and later automation.

## Markdown artifact

The Markdown artifact is the operator-facing output.

It includes:

- executive summary
- top issues
- recurring patterns
- noise or expected
- recommended actions
- audit domain rollups
- recent AI briefs when relevant
- raw counters

## Recent AI briefs

The weekly review can include a `Recent AI briefs` section.

This section references the latest successful `generate_ai_ops_brief` result per source within the review window.

Current intended sources:

```text
admin_host_audit
vps_host_audit
monitoring_stack_audit
mac_host_audit
```

For each source, the weekly review can include:

- brief status
- executive summary
- markdown path
- JSON path

Stale brief references are filtered when the corresponding audit domain has a newer `ok` run.

This prevents old warning briefs from appearing as current risk after the domain has recovered.

## Action layout

### Weekly review action

```text
action_runner/actions/weekly_review.py
```

Responsibilities:

- query SQLite state
- build weekly summary JSON
- aggregate audit domain rollups
- call OpenAI Responses API
- post-process model output
- write Markdown and JSON artifacts
- maintain `weekly-latest.*` symlinks
- prune old weekly snapshots by retention count

### Copy action

```text
action_runner/actions/mac_file.py
```

Responsibilities:

- validate source file
- ensure remote directory exists
- copy file to Mac over SSH/SCP
- normalize result into `ActionResult`

This action is reused by weekly review and AI brief flows.

## Config

```text
action_runner/config.py
```

Relevant config:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_WEEKLY_REVIEW_MODEL
MAC_REVIEW_SSH_TARGET
MAC_REVIEW_DOCS_DIR
MAC_REVIEW_COPY_TIMEOUT_SECONDS
```

Typical values:

```text
OPENAI_WEEKLY_REVIEW_MODEL=gpt-5.4-nano
MAC_REVIEW_SSH_TARGET=mac
MAC_REVIEW_DOCS_DIR=~/Documents/control-plane-reviews
MAC_REVIEW_COPY_TIMEOUT_SECONDS=30
```

The weekly chain overrides the Mac target directory to:

```text
~/Documents/control-plane-reviews/weekly
```

## SSH requirement

The action-runner service runs as user `admin1`.

That means:

- `admin1` on VPS must have a working `~/.ssh/config`
- alias `mac` must resolve correctly
- SSH and SCP to `mac` must work without password
- target directory on Mac must be writable

Validated manually with:

```bash
ssh mac 'mkdir -p ~/Documents/control-plane-reviews/weekly && ls -ld ~/Documents/control-plane-reviews/weekly'

scp /srv/control-plane/state/reviews/weekly/weekly-latest.md \
  mac:~/Documents/control-plane-reviews/weekly/
```

## Scheduler

This flow is triggered by the built-in action-runner scheduler through:

```text
action_runner/schedules.yaml
```

No cron is used.

Expected weekly signal:

```text
alertname=WeeklyOpsReview
status=firing
severity=info
instance=vps
job=scheduler
```

Current schedule:

```text
Sunday 05:00 UTC
```

The rule maps this signal to the weekly review chain.

## Retention

Weekly review snapshots are timestamped.

Examples:

```text
weekly-2026-04-12_03-22-39.md
weekly-2026-04-12_03-22-39.json
```

`weekly-latest.md` and `weekly-latest.json` are symlinks to the newest snapshot.

Retention is controlled by:

```text
retention_count
```

Current default:

```text
10 snapshots per file type
```

## Manual tests

### Generate weekly review directly

This only generates weekly artifacts.

It does not copy to Mac and does not notify Telegram.

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"generate_weekly_ops_review",
    "payload":{
      "days":7
    }
  }' | jq
```

### Copy generated weekly file directly

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"copy_file_to_mac",
    "payload":{
      "source_path":"/srv/control-plane/state/reviews/weekly/weekly-latest.md",
      "target_dir":"~/Documents/control-plane-reviews/weekly"
    }
  }' | jq
```

### Notify directly

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"notify_tg",
    "payload":{
      "format":"message",
      "title":"[TEST] weekly notify",
      "facts":[
        {"key":"source","value":"manual"}
      ],
      "body":"Direct notify_tg test from action-runner",
      "source":"action-runner",
      "event":"manual_weekly_notify_test",
      "severity":"info",
      "status":"firing"
    }
  }' | jq
```

### Trigger full weekly chain

This runs the complete rule chain:

```text
generate_weekly_ops_review
copy_file_to_mac
notify_tg
```

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
        "summary":"manual weekly ops review full chain test",
        "description":"manual trigger for weekly ops review chain"
      }
    }]
  }' | jq
```

## Verification commands

Check runner state:

```bash
ar-decision
ar-task
ar-run
ar-chain
```

Check generated files on VPS:

```bash
ls -lt /srv/control-plane/state/reviews/weekly | head
cat /srv/control-plane/state/reviews/weekly/weekly-latest.md
```

Check copied files on Mac:

```bash
ssh mac 'ls -lt ~/Documents/control-plane-reviews/weekly | head'
```

Check notify task:

```bash
curl -s http://127.0.0.1:8088/tasks | jq '.tasks[] | select(.task_type=="notify")'
```

Check Telegram run:

```bash
curl -s http://127.0.0.1:8088/runs | jq '.runs[] | select(.action=="notify_tg") | {id,status,started_at,error}'
```

## Expected successful chain

A successful weekly chain should show:

```text
generate_weekly_ops_review  success
copy_file_to_mac            success
notify_tg                   queued/success
```

The notify step may appear as a queued notify task in the chain summary, because `notify` is a task type that then runs `notify_tg`.

## Expected output shape

A successful weekly review produces:

- one Markdown artifact
- one JSON artifact
- updated `weekly-latest.*` symlinks
- copied Markdown file on Mac
- one short Telegram message

The Markdown review includes:

- week status
- executive summary
- top issues
- recurring patterns
- noise or expected
- recommended actions
- audit domains
- raw counters

## Common confusion

### Direct action does not send Telegram

This command:

```bash
curl -s http://127.0.0.1:8088/actions/run \
  --json '{"action":"generate_weekly_ops_review","payload":{"days":7}}' | jq
```

only runs:

```text
generate_weekly_ops_review
```

It does not run:

```text
copy_file_to_mac
notify_tg
```

To test the full weekly path, trigger the `WeeklyOpsReview` signal through `/events/alertmanager`.

### `queued_task_id` is not a run id

In chain output, this:

```json
"queued_task_id": 158
```

means task id, not run id.

Inspect it with:

```bash
ar-task 158
```

not:

```bash
ar-run 158
```

## Current status

The weekly ops review flow is considered working when:

- weekly snapshot is generated on VPS
- Markdown review is copied to Mac
- Telegram notification is sent
- scheduler can trigger the same chain without manual input
- all four audit domains appear in the weekly summary
- stale AI brief references are filtered after recovered `ok` audit runs
