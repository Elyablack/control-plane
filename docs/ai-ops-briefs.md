# AI ops briefs

## Purpose

`generate_ai_ops_brief` is a shared AI interpretation layer for deterministic audit results.

It is not an audit runner and it does not replace audit analyzers.

Its purpose is narrower:

- take one already-structured analyzer result
- produce a short operator-facing brief
- save markdown and JSON artifacts
- support downstream actions such as file copy and notification

This keeps the domain audit logic deterministic while reusing one common AI layer across multiple audit sources.

---

## Current sources

The brief action is intended to work across multiple domains.

Current sources in use:

- `vps_host_audit`
- `admin_host_audit`

Planned future sources may include:

- `monitoring_stack_audit`
- backup-related analysis flows
- other bounded analyzer outputs

---

## Design model

The architecture is intentionally layered.

```
domain audit
    -> run_*
    -> verify_*
    -> analyze_*
    -> generate_ai_ops_brief
````

This means:

- domain-specific collection and parsing stay local to the audit 
- AI is used only after deterministic analysis exists
- the brief layer can be reused without duplicating domain logic
    
The brief action is tactical, not strategic.

- generate_ai_ops_brief = one incident / one analyzer result
- generate_weekly_ops_review = cross-domain weekly summary
    

---

## **Input contract**

generate_ai_ops_brief expects structured input.

Typical payload shape:

```
{
  "source": "vps_host_audit",
  "analysis_level": "warning",
  "analysis_summary": "warning:journal priority<=3 count 50",
  "analysis_findings_count": 1,
  "analysis_log_path": "/var/log/vps-host-audit/audit_2026-04-13_04-54-22.log",
  "facts": {
    "host": "vps",
    "metrics_path": "/var/lib/node_exporter/textfile_collector/vps_host_audit.prom"
  },
  "context": {}
}
```

Required practical fields:

- source
- analysis_level
- analysis_summary

Useful optional fields:

- analysis_findings_count
- analysis_log_path
- facts
- context
- model
- brief_dir

---

## **Behavior by analysis level**

### ok

The action should not be called in the normal chain path.

Current rules gate the step with:

```
when:
  analysis_level_in: ["warning", "critical"]
```

So in normal flow:

- ok analyzer result    
- no brief generated
- no Mac copy
- no Telegram brief notification

### warning or critical

The action:

- calls OpenAI Responses API    
- generates a short brief
- writes markdown and JSON artifacts
- returns paths through RESULT_JSON

---

## **Output contract**

The action returns structured JSON through RESULT_JSON.

Typical result:

```
{
  "source": "vps_host_audit",
  "brief_status": "watch",
  "executive_summary": "Analyzer reports a warning condition...",
  "markdown_path": "/srv/control-plane/state/reviews/briefs/brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.md",
  "json_path": "/srv/control-plane/state/reviews/briefs/brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.json"
}
```

The output is designed specifically so that chain context can reuse:

- brief_status
- executive_summary
- markdown_path
- json_path

in later steps.

---

## **Artifact locations**

### **On VPS**

```
/srv/control-plane/state/reviews/briefs/
```

Examples:

- brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.md
- brief-vps_host_audit-YYYY-MM-DD_HH-MM-SS.json
- brief-admin_host_audit-YYYY-MM-DD_HH-MM-SS.md
- brief-admin_host_audit-YYYY-MM-DD_HH-MM-SS.json

Per-source latest symlinks are also maintained:

- brief-vps_host_audit-latest.md
- brief-vps_host_audit-latest.json
- brief-admin_host_audit-latest.md
- brief-admin_host_audit-latest.json

### **On Mac**

```
~/Documents/control-plane-reviews/briefs
```

Brief markdown files are copied there by copy_file_to_mac when the chain reaches the non-OK path.

---

## **Brief status model**

The AI brief currently emits one of:

- stable    
- watch
- risky

This status is intentionally compact. It is not used as a replacement for the deterministic analyzer result.

Instead:

- deterministic analyzer result = source of truth
- AI brief status = operator-facing interpretation layer
    

---

## **Markdown shape**

A generated brief markdown contains:

- source
- analysis level
- findings count
- log path
- brief status
- analyzer summary
- executive summary
- top risks
- recommended actions
- operator note
- facts
- context

This gives the operator a readable artifact while preserving deterministic source fields.

---

## **Example flow: VPS audit**

```
VpsHostAuditDaily
    -> run_vps_host_audit
    -> verify_vps_host_audit
    -> analyze_vps_host_audit
    -> generate_ai_ops_brief
    -> copy_file_to_mac
    -> notify_tg
```

The brief step runs only when analysis_level is warning or critical.

---

## **Example flow: admin audit**

```
AdminHostAuditWeekly
    -> run_admin_host_audit
    -> verify_admin_host_audit
    -> analyze_admin_host_audit
    -> generate_ai_ops_brief
    -> copy_file_to_mac
    -> notify_tg
```

Again, brief generation is gated to non-OK outcomes.

---

## **Telegram usage**

Telegram notifications are intentionally shorter than the markdown brief.  

The current pattern is:

- short title
- a few compact facts
- analysis_summary in the body

This keeps notification noise low while preserving the full markdown artifact for later reading.

Example shape:

```
[VPS][WARNING] audit brief

brief: watch
file: /srv/control-plane/state/reviews/briefs/brief-vps_host_audit-...
warning:journal priority<=3 count 50
```

The markdown file remains the detailed artifact.

---

## **Weekly review integration**

generate_weekly_ops_review now includes recent successful AI briefs per source.

This creates a bridge from:

- daily tactical AI summaries    
- to weekly strategic review
    
Current weekly review includes a Recent AI briefs section with:

- source
- brief status
- executive summary
- markdown path
- json path

This allows the weekly review to reference the latest non-OK bounded interpretations without replacing deterministic evidence.

---

## **OpenAI model usage**

The brief layer uses the OpenAI Responses API.

Relevant config:

- OPENAI_API_KEY    
- OPENAI_BASE_URL
- OPENAI_OPS_BRIEF_MODEL

Typical current model choice:

```
gpt-5.4-nano
```

This is intentionally a cheaper bounded model because the task is narrow and structured.

---

## **Manual tests**

### **Generate a brief directly**

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

### **Check generated files on VPS**

```
ls -lt /srv/control-plane/state/reviews/briefs | head
readlink -f /srv/control-plane/state/reviews/briefs/brief-vps_host_audit-latest.md
readlink -f /srv/control-plane/state/reviews/briefs/brief-admin_host_audit-latest.md
```

### **Check copied files on Mac**

```
ssh mac 'ls -lt ~/Documents/control-plane-reviews/briefs | head'
```

### **Trigger full chain through alert ingestion** 

VPS:

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

Admin:

```
curl -s http://127.0.0.1:8088/events/alertmanager \
  --json '{
    "receiver": "action-runner",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "AdminHostAuditWeekly",
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

---

## **Verification commands**

Inspect the latest state:

```
ar-decision
ar-task
ar-run
ar-chain
ar-runs 10
```

The chain is considered correct when:

- analyzer emits warning or critical
- generate_ai_ops_brief succeeds
- markdown brief is written on VPS
- markdown brief is copied to Mac
- short Telegram notification is delivered

---

## **Operational notes**

### **Why this layer exists**

The brief layer is intentionally not responsible for:

- collecting host data
- parsing logs
- deciding remediation actions
- mutating rules
- running shell commands

Those remain deterministic and domain-owned.
The brief layer exists only to improve operator comprehension.

### **Why one shared brief action is better**

A shared action avoids creating separate AI implementations for:

- VPS audit    
- admin audit
- future monitoring-stack audit

That keeps prompts, output shape, storage model, and downstream usage consistent.

---

## **Current status**

The AI ops brief layer is considered implemented when:

- it can generate standalone brief artifacts from structured analyzer results    
- it is connected to VPS audit non-OK paths
- it is connected to admin audit non-OK paths
- brief artifacts are copied to Mac
- recent briefs are visible from the weekly ops review
