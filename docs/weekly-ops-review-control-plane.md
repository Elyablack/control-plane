# Weekly ops review flow

## Purpose

The weekly ops review is the higher-level AI review layer for the control-plane.

It does not replace deterministic audits.

Instead it aggregates one week of operational state and produces a bounded operator-facing summary that answers:

- what mattered this week
- which issues repeated
- what was probably noise
- what should be fixed first

This is the strategic review layer above the day-to-day audit flows.

---

## What it does

The weekly ops review flow performs three steps in sequence:

1. generate a weekly review snapshot on the VPS
2. copy the generated markdown file to Mac
3. send a short Telegram notification

The generated review now also includes references to recent AI audit briefs when they exist.

---

## Flow

```
WeeklyOpsReview
    -> generate_weekly_ops_review
    -> copy_file_to_mac
    -> notify_tg
````

---

## **Inputs used by the weekly review**

generate_weekly_ops_review summarizes the last 7 days of control-plane state from SQLite.

It currently includes:

- decisions    
- tasks
- runs
- top alerts
- backup runs
- admin host audit analyzer results
- VPS host audit analyzer results
- mac memory pressure decisions
- mac remediation tasks
- latest operational failures
- recent AI ops briefs by source

This gives the weekly review both deterministic signal history and short AI brief context.

---

## **Artifact locations**

### **On VPS**

```
/srv/control-plane/state/reviews/weekly/
```

Examples:

- weekly-YYYY-MM-DD_HH-MM-SS.md
- weekly-YYYY-MM-DD_HH-MM-SS.json
- weekly-latest.md
- weekly-latest.json

### **On Mac**

```
~/Documents/control-plane-reviews/weekly
```

---

## **Recent AI briefs in weekly review**

The weekly review now includes a Recent AI briefs section.

This section references the latest successful generate_ai_ops_brief results per source within the review window.

Current intended sources:

- vps_host_audit    
- admin_host_audit

For each source the weekly review stores:

- brief status
- executive summary
- markdown path
- json path

This creates a simple bridge between daily tactical AI output and the weekly strategic review.

---

## **Action layout**

### **Weekly review action**

```
action_runner/actions/weekly_review.py
```
  
Responsibilities:

- query SQLite state  
- build weekly summary JSON
- call OpenAI Responses API
- write markdown/json artifacts
- maintain weekly-latest.* symlinks
- prune old weekly snapshots by retention count

### **Copy action**

```
action_runner/actions/mac_file.py
```
  
Responsibilities:

- validate source file  
- ensure remote directory exists
- copy file to Mac over SSH/SCP
- normalize result into ActionResult

This action is reused by both weekly review and AI brief flows.

---

## **Config**

```
action_runner/config.py
```
  
Relevant config:

- OPENAI_API_KEY  
- OPENAI_BASE_URL
- OPENAI_WEEKLY_REVIEW_MODEL
- MAC_REVIEW_SSH_TARGET
- MAC_REVIEW_DOCS_DIR
- MAC_REVIEW_COPY_TIMEOUT_SECONDS

Typical values:

- OPENAI_WEEKLY_REVIEW_MODEL=gpt-5.4-nano
- MAC_REVIEW_SSH_TARGET=mac
- MAC_REVIEW_DOCS_DIR=~/Documents/control-plane-reviews
- MAC_REVIEW_COPY_TIMEOUT_SECONDS=30

The weekly chain itself overrides the Mac target directory to:

```
~/Documents/control-plane-reviews/weekly
```

---

## **SSH requirement**

The action-runner service runs as user admin1.

That means:

- admin1 on the VPS must have a working ~/.ssh/config    
- alias mac must resolve correctly
- SSH and SCP to mac must work without password
- the target directory on Mac must be writable for the target user

Validated manually with:

```
ssh mac 'mkdir -p ~/Documents/control-plane-reviews/weekly && ls -ld ~/Documents/control-plane-reviews/weekly'
scp /srv/control-plane/state/reviews/weekly/weekly-latest.md mac:~/Documents/control-plane-reviews/weekly/
```

---

## **Scheduler**

This flow is triggered by the built-in action-runner scheduler through schedules.yaml.

No cron is used.

The scheduler emits an internal signal with:

- alertname=WeeklyOpsReview    
- status=firing
- severity=info
    
The rule maps that signal to the weekly review chain.

---

## **Retention**

Weekly review snapshots are timestamped.

Examples:

- weekly-2026-04-12_03-22-39.md    
- weekly-2026-04-12_03-22-39.json

weekly-latest.md and weekly-latest.json are symlinks to the newest snapshot.

Retention is controlled by:

- retention_count
    
Current default:

- keep last 10 weekly snapshots per file type
    

---

## **Manual tests**

### **Generate weekly review directly**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"generate_weekly_ops_review",
    "payload":{
      "days":7
    }
  }' | jq
```

### **Copy generated weekly file directly**

```
curl -s http://127.0.0.1:8088/actions/run \
  --json '{
    "action":"copy_file_to_mac",
    "payload":{
      "source_path":"/srv/control-plane/state/reviews/weekly/weekly-latest.md",
      "target_dir":"~/Documents/control-plane-reviews/weekly"
    }
  }' | jq
```

### **Trigger full weekly chain through signal ingestion**

```
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
          "summary": "manual weekly ops review full chain test",
          "description": "manual trigger for weekly ops review chain"
        }
      }
    ]
  }' | jq
```

---

## **Verification commands**

Check runner state:

```
ar-decision
ar-task
ar-run
ar-chain
```

Check generated files on VPS:

```
ls -lt /srv/control-plane/state/reviews/weekly | head
cat /srv/control-plane/state/reviews/weekly/weekly-latest.md
```

Check copied files on Mac:

```
ssh mac 'ls -lt ~/Documents/control-plane-reviews/weekly | head'
```

---

## **Expected output shape**

A successful weekly review produces:

- one markdown artifact
- one JSON artifact
- updated weekly-latest symlinks
- one short Telegram message
- copied markdown file on Mac

The markdown review includes at minimum:

- executive summary
- top issues
- recurring patterns
- noise or expected
- recommended actions
- recent AI briefs
- raw counters

---

## **Current status**

The weekly ops review flow is considered working when:

- weekly snapshot is generated on the VPS
- markdown review is copied to Mac
- Telegram notification is sent
- scheduler can trigger the same chain without manual input
- recent AI brief references appear in the weekly summary when present
