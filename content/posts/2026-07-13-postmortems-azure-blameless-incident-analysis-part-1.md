---
slug: "postmortems-azure-blameless-incident-analysis-part-1"
aliases:
  - "/2026/07/13/postmortems-azure-blameless-incident-analysis-part-1/"
translationKey: "postmortems-no-azure-analise-pos-incidente-blameless-parte-1"
title: "Postmortems on Azure: implementing blameless incident analysis with Azure Monitor (Part 1)"
description: "Learn how to implement blameless postmortems on Azure: complete template, KQL queries for timeline reconstruction, and Logic Apps automation for data collection."
date: 2026-07-13T10:00:00-04:00
categories:
  - Azure
  - SRE
tags:
  - postmortem
  - sre
  - azure-monitor
  - kql
  - blameless
  - incident-management
  - devops
  - observability
series:
  - "Azure SRE"
---

First post in a two-part series on Azure postmortems. Incidents are inevitable. Repeat incidents are optional.

A lot of teams say they do postmortems, but what they really have is a short meeting, a vague document, and a backlog item nobody revisits. A good Azure postmortem is different: it is blameless, evidence-based, and tightly connected to telemetry. If you already use Azure Monitor, Application Insights, Log Analytics, and Azure Activity Logs, you already have most of the raw material you need.

This post walks through a blameless postmortem process on Azure: a reusable template, KQL queries to rebuild the timeline, and a Logic Apps flow that creates the first draft. In [Part 2](/postmortems-azure-automation-devops-metrics-part-2/), the focus shifts to Azure DevOps, incident metrics, and the broader SRE feedback loop.

## tl;dr

- A useful Azure postmortem is blameless, evidence-based, and tied to telemetry.
- Use KQL to rebuild the timeline fast.
- Let Logic Apps create the draft, then let humans do the analysis.

## Why postmortems fail in most organizations

The technical tooling is rarely the real problem. The failure mode is usually organizational.

| Anti-pattern | Consequence | Visible symptom |
|-------------|-------------|-----------------|
| **Blame culture** | People hide details to avoid criticism | The incident timeline has suspicious gaps |
| **Late postmortem** | Critical context is forgotten after a few days | The document reads like guesswork |
| **No action items** | The review becomes a compliance exercise | The same incident returns a few weeks later |
| **Action items without owners** | Improvements exist only on paper | The backlog grows, nothing ships |
| **Scope that is too broad** | The review tries to solve every structural issue at once | Long meeting, no concrete outcome |
| **Focus on “what went wrong” only** | The team misses system contributors and near-misses | Fixes are narrow and fragile |
| **No hard data** | Memory and opinion replace evidence | Participants disagree about basic facts |

A postmortem is not a courtroom transcript. It is an engineering artifact. Its job is to explain impact, reconstruct the timeline, identify systemic contributors, and leave the platform more resilient than it was before the incident.

## What blameless culture really means

Blameless does **not** mean “nobody is accountable.” It means the analysis focuses on why the system allowed a reasonable human action to become a customer-facing failure.

If an engineer ran a command, approved a deployment, or skipped a mitigation step, the useful question is not “Who did this?” The useful question is “Why did our system, process, telemetry, or decision environment make that outcome possible?”

### Traditional vs. blameless incident analysis

| Aspect | Traditional approach | Blameless approach |
|--------|----------------------|--------------------|
| **Primary question** | “Who caused this?” | “What allowed this to happen?” |
| **Focus of analysis** | Individual action | System conditions and contributors |
| **Typical outcome** | Warning, escalation, discomfort | Engineering improvements |
| **Effect on the team** | Fear and defensiveness | Psychological safety and candor |
| **Timeline quality** | Incomplete | Detailed and trustworthy |
| **Chance of recurrence** | Higher | Lower |
| **Organizational learning** | Minimal | Compounding |

### The five principles of a blameless postmortem

1. **Assume positive intent.** Nobody starts the day trying to take production down.
2. **Treat failure as data.** Every incident exposes a gap you did not fully understand before.
3. **Look for contributing factors, not a single villain.** Most incidents are chains, not isolated mistakes.
4. **Prefer systemic fixes.** Improve the system, process, tooling, and detection path.
5. **Make the learning reusable.** If only the incident responders learn from the event, the organization wastes the failure.

The biggest practical benefit of blameless culture is better evidence. When people know they will not be punished for being transparent, they share the commands they ran, the assumptions they made, the dashboards they trusted, and the signals they missed. That information is exactly what prevents the next outage.

## Anatomy of an effective postmortem

A strong postmortem template forces clarity without turning the process into bureaucracy. The template below is intentionally opinionated for Azure-centric environments.

### Complete postmortem template

```markdown
# Postmortem: [Descriptive incident title]

## Metadata
- **Incident date**: YYYY-MM-DD
- **Duration**: HH:MM (from impact start to recovery)
- **Severity**: SEV-1 / SEV-2 / SEV-3 / SEV-4
- **Postmortem author**: [Name]
- **Review facilitator**: [Name]
- **Review date**: YYYY-MM-DD
- **Status**: Draft / In Review / Approved

## Executive summary
[2-3 paragraphs: what happened, customer impact, and how the service was restored.]

## Impact
- **Users affected**: [number or percentage]
- **Impact duration**: [time customers were affected]
- **Revenue impact**: [estimate, if applicable]
- **SLO affected**: [which SLO was violated and by how much]
- **Error Budget consumed**: [percentage of the monthly budget used]
- **Support tickets opened**: [count]

## Detailed timeline
| Time (UTC) | Event | Source |
|------------|-------|--------|
| HH:MM | First sign of degradation in logs | Azure Monitor |
| HH:MM | Alert fired | Action Group |
| HH:MM | On-call engineer paged | PagerDuty / Opsgenie |
| HH:MM | Investigation started | - |
| HH:MM | Root cause identified | Log Analytics |
| HH:MM | Mitigation applied | - |
| HH:MM | Service restored | Azure Monitor |
| HH:MM | Stability confirmed | SLO dashboard |

## Root cause and contributing factors
### Root cause
[Detailed technical explanation of the root cause]

### Contributing factors
1. [Factor 1]
2. [Factor 2]
3. [Factor 3]

### Causal diagram
[Optional: Ishikawa diagram, fault tree, or equivalent]

## What worked well
- [Item 1]
- [Item 2]
- [Item 3]

## What should improve
- [Item 1]
- [Item 2]
- [Item 3]

## Where we got lucky
- [Item 1]
- [Item 2]

## Action items
| ID | Action | Priority | Owner | Due date | Status |
|----|--------|----------|-------|----------|--------|
| AI-001 | Tune alert X threshold | P1 | @owner | 7 days | Open |
| AI-002 | Create runbook for scenario Y | P2 | @owner | 14 days | Open |
| AI-003 | Add chaos test for component Z | P3 | @owner | 30 days | Open |

## Lessons learned
[Insights that apply beyond this incident and should influence future system design]
```

### Severity classification

Severity should change the level of rigor, the deadline, and the required audience.

| Severity | Typical criterion | Postmortem deadline | Required participants |
|----------|-------------------|---------------------|-----------------------|
| **SEV-1** | Full outage or data loss | Within 48 hours of resolution | Engineering, management, product, support |
| **SEV-2** | Major degradation or loss of critical functionality | Within 5 business days | Engineering, management |
| **SEV-3** | Partial impact or moderate degradation | Within 10 business days | Engineering |
| **SEV-4** | Minimal impact, often detected internally | Within 15 business days | Directly involved engineers |

**Rule of thumb:** every SEV-1 and SEV-2 incident should produce a postmortem. Lower severities can use a lighter-weight version, but the process should still exist.

## Collecting postmortem evidence with Azure Monitor and KQL

Timeline reconstruction is where most postmortems get slow. It is also where Azure already helps. If you send application telemetry, dependency telemetry, platform events, and management activity into Azure Monitor, the postmortem author should spend time analyzing data, not hunting for it.

### Reconstructing the timeline with Application Insights

Use request telemetry first. It gives you the best answer to: *when did impact start, how fast did it spread, and what did users experience?*

```kql
// Failure timeline by minute during the incident window
AppRequests
| where TimeGenerated between (datetime("2026-04-15 14:00") .. datetime("2026-04-15 18:00"))
| summarize
    totalRequests = count(),
    failedRequests = countif(Success == false),
    failureRate = round(100.0 * countif(Success == false) / count(), 2),
    avgDuration = round(avg(DurationMs), 2),
    p95Duration = round(percentile(DurationMs, 95), 2)
  by bin(TimeGenerated, 1m)
| order by TimeGenerated asc
| render timechart
```

This query helps you mark the exact minute the service moved from normal to degraded. In many reviews, that single chart already corrects several incorrect assumptions from the war room.

### Identifying the exceptions behind failed requests

Once you know when impact started, find the exception patterns that dominated the window.

```kql
// Top exceptions during the incident window
AppExceptions
| where TimeGenerated between (datetime("2026-04-15 14:00") .. datetime("2026-04-15 18:00"))
| summarize
    occurrences = count(),
    firstSeen = min(TimeGenerated),
    lastSeen = max(TimeGenerated),
    affectedOperations = dcount(OperationId)
  by ProblemId, ExceptionType = tostring(split(Type, ".")[-1]), OuterMessage
| order by occurrences desc
| take 20
```

This is the fastest way to separate the dominant failure from noisy side effects.

### Correlating exceptions with failed requests

Individually, request and exception tables are useful. Together, they tell the story.

```kql
// Correlation between failed requests and exceptions
AppRequests
| where TimeGenerated between (datetime("2026-04-15 14:00") .. datetime("2026-04-15 18:00"))
| where Success == false
| join kind=inner (
    AppExceptions
    | where TimeGenerated between (datetime("2026-04-15 14:00") .. datetime("2026-04-15 18:00"))
) on OperationId
| summarize
    failureCount = count(),
    avgDuration = round(avg(DurationMs), 2)
  by RequestName = Name, ExceptionType = Type, ExceptionMessage = OuterMessage
| order by failureCount desc
```

Use this to answer the executive version of root cause: *which operations failed, and why?*

### Analyzing failed dependencies

A surprising number of Azure incidents are not failures in your code. They are failures in what your code depends on.

```kql
// Dependencies that failed during the incident
AppDependencies
| where TimeGenerated between (datetime("2026-04-15 14:00") .. datetime("2026-04-15 18:00"))
| where Success == false
| summarize
    failures = count(),
    avgDuration = round(avg(DurationMs), 2),
    p99Duration = round(percentile(DurationMs, 99), 2),
    firstFailure = min(TimeGenerated),
    lastFailure = max(TimeGenerated)
  by DependencyType = Type, DependencyName = Name, Target, ResultCode
| order by failures desc
```

This is especially useful for storage, SQL, Redis, Service Bus, downstream APIs, or any service protected by retries and circuit breakers.

### Checking for environment changes with Azure Activity Logs

Every serious postmortem should ask a brutally simple question: *what changed before the incident?*

```kql
// Environment changes in the 6 hours before the incident
AzureActivity
| where TimeGenerated between (datetime("2026-04-15 08:00") .. datetime("2026-04-15 14:30"))
| where OperationNameValue has_any ("write", "delete", "action")
| where ActivityStatusValue == "Success"
| project
    TimeGenerated,
    Caller,
    OperationNameValue,
    ResourceGroup,
    Resource = tostring(split(_ResourceId, "/")[-1]),
    Properties = ActivitySubstatusValue
| order by TimeGenerated desc
```

If there was a deployment, configuration change, RBAC update, scale action, or delete event before impact started, this query will usually find it.

### Reviewing resource health events

Not every issue shows up as application telemetry. Resource Health can expose infrastructure conditions that would otherwise look mysterious from the app layer.

```kql
// Resource health events during the incident
AzureActivity
| where TimeGenerated between (datetime("2026-04-15 13:00") .. datetime("2026-04-15 19:00"))
| where CategoryValue == "ResourceHealth"
| project
    TimeGenerated,
    ResourceType = tostring(split(_ResourceId, "/")[-2]),
    Resource = tostring(split(_ResourceId, "/")[-1]),
    Status = ActivityStatusValue,
    Detail = Properties
| order by TimeGenerated asc
```

### Building a consolidated incident timeline

One of my favorite techniques is to collapse application failures, exceptions, alert activity, and control-plane changes into a single chronological view.

```kql
// Unified incident timeline
let incidentStart = datetime("2026-04-15 14:00");
let incidentEnd = datetime("2026-04-15 18:00");
let lookbackWindow = 2h;
//
// 1. First failure signals (requests)
let requestFailures = AppRequests
| where TimeGenerated between ((incidentStart - lookbackWindow) .. incidentEnd)
| where Success == false
| summarize Count = count() by bin(TimeGenerated, 1m)
| where Count > 5
| extend EventType = "RequestFailure", Detail = strcat(Count, " failed requests");
//
// 2. New exceptions
let exceptions = AppExceptions
| where TimeGenerated between ((incidentStart - lookbackWindow) .. incidentEnd)
| summarize Count = count(), Types = make_set(Type) by bin(TimeGenerated, 1m)
| where Count > 0
| extend EventType = "Exception", Detail = strcat(Count, " exceptions: ", tostring(Types));
//
// 3. Environment changes
let changes = AzureActivity
| where TimeGenerated between ((incidentStart - lookbackWindow) .. incidentEnd)
| where OperationNameValue has_any ("write", "delete")
| where ActivityStatusValue == "Success"
| extend EventType = "EnvironmentChange",
         Detail = strcat(Caller, " executed ", OperationNameValue, " on ", tostring(split(_ResourceId, "/")[-1]));
//
// Alert data requires Azure Resource Graph - query separately if needed
// Consolidation
requestFailures
| union exceptions
| union changes
| project TimeGenerated, EventType, Detail
| order by TimeGenerated asc
```

This is usually the query I paste directly into the timeline section of the draft postmortem before I refine the narrative.

## Automating postmortem data collection with Logic Apps

A manual postmortem process breaks down under incident pressure. The best pattern is to generate a **draft** automatically when an alert is resolved, then let humans improve it.

### Configure an Action Group trigger

Start with an Action Group that invokes a Logic App when a relevant alert transitions to **resolved**.

```bash
# Create an Action Group for postmortem generation
az monitor action-group create \
  --resource-group rg-monitoring \
  --name ag-postmortem-trigger \
  --short-name postmortem \
  --action logicapp "PostmortemGenerator" \
    "/subscriptions/{sub-id}/resourceGroups/rg-automation/providers/Microsoft.Logic/workflows/postmortem-generator" \
    "https://prod-XX.eastus.logic.azure.com:443/workflows/{workflow-id}/triggers/manual/paths/invoke"
```

### Logic App definition for an auto-generated draft

The Logic App below receives the alert payload, queries Log Analytics, and creates a first work item draft that the incident owner can refine.

```json
{
  "definition": {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "triggers": {
      "When_alert_resolved": {
        "type": "Request",
        "kind": "Http",
        "inputs": {
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "object",
                "properties": {
                  "essentials": {
                    "type": "object",
                    "properties": {
                      "alertId": { "type": "string" },
                      "alertRule": { "type": "string" },
                      "severity": { "type": "string" },
                      "monitorCondition": { "type": "string" },
                      "firedDateTime": { "type": "string" },
                      "resolvedDateTime": { "type": "string" }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "actions": {
      "Query_Log_Analytics": {
        "type": "ApiConnection",
        "inputs": {
          "host": {
            "connection": {
              "name": "@parameters('$connections')['azuremonitorlogs']['connectionId']"
            }
          },
          "method": "post",
          "path": "/queryData",
          "body": {
            "workspaceId": "<log-analytics-workspace-id>",
            "query": "AppRequests | where TimeGenerated between (datetime('@{triggerBody()?['data']?['essentials']?['firedDateTime']}') .. datetime('@{triggerBody()?['data']?['essentials']?['resolvedDateTime']}')) | where Success == false | summarize failedCount=count(), avgDuration=avg(DurationMs) by bin(TimeGenerated, 5m), Name | order by TimeGenerated asc",
            "timeRange": {
              "from": "@{triggerBody()?['data']?['essentials']?['firedDateTime']}",
              "to": "@{triggerBody()?['data']?['essentials']?['resolvedDateTime']}"
            }
          }
        }
      },
      "Create_DevOps_Work_Item": {
        "type": "ApiConnection",
        "runAfter": { "Query_Log_Analytics": ["Succeeded"] },
        "inputs": {
          "host": {
            "connection": {
              "name": "@parameters('$connections')['visualstudioteamservices']['connectionId']"
            }
          },
          "method": "post",
          "path": "/MyProject/_apis/wit/workitems/$Bug?api-version=7.1",
          "body": [
            {
              "op": "add",
              "path": "/fields/System.Title",
              "value": "Postmortem: @{triggerBody()?['data']?['essentials']?['alertRule']}"
            },
            {
              "op": "add",
              "path": "/fields/System.Tags",
              "value": "postmortem;incident-review"
            }
          ]
        }
      }
    }
  }
}
```

A few practical notes:

- Generate a draft, not a final document.
- Keep the trigger narrow at first. Start with SEV-1 and SEV-2 alerts.
- Write the raw telemetry into the draft, then let the facilitator add interpretation.
- Do not let automation invent root cause. Data collection can be automated; accountability for analysis stays human.

### Azure CLI script to generate a postmortem draft

If you prefer a CLI-first workflow, use a simple shell script instead of Logic Apps.

```bash
#!/bin/bash
# Script to generate a postmortem draft via CLI
# Usage: ./generate-postmortem.sh <workspace-id> <start> <end>

WORKSPACE_ID=$1
INCIDENT_START=$2
INCIDENT_END=$3

echo "# Postmortem - Automatic Draft"
echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
echo "## Incident window"
echo "- Start: $INCIDENT_START"
echo "- End: $INCIDENT_END"
echo ""

# Failure timeline
echo "## Failure timeline (requests)"
az monitor log-analytics query \
  --workspace "$WORKSPACE_ID" \
  --analytics-query "
    AppRequests
    | where TimeGenerated between (datetime('$INCIDENT_START') .. datetime('$INCIDENT_END'))
    | where Success == false
    | summarize failedCount=count() by bin(TimeGenerated, 5m), Name
    | order by TimeGenerated asc
  " \
  --output table

# Top exceptions
echo ""
echo "## Identified exceptions"
az monitor log-analytics query \
  --workspace "$WORKSPACE_ID" \
  --analytics-query "
    AppExceptions
    | where TimeGenerated between (datetime('$INCIDENT_START') .. datetime('$INCIDENT_END'))
    | summarize count() by ProblemId, Type, OuterMessage
    | order by count_ desc
    | take 10
  " \
  --output table

# Environment changes
echo ""
echo "## Environment changes (2h before incident start)"
az monitor log-analytics query \
  --workspace "$WORKSPACE_ID" \
  --analytics-query "
    AzureActivity
    | where TimeGenerated between (datetime_add('hour', -2, datetime('$INCIDENT_START')) .. datetime('$INCIDENT_START'))
    | where OperationNameValue has_any ('write', 'delete')
    | where ActivityStatusValue == 'Success'
    | project TimeGenerated, Caller, OperationNameValue, ResourceGroup
    | order by TimeGenerated desc
  " \
  --output table

# Failed dependencies
echo ""
echo "## Failed dependencies"
az monitor log-analytics query \
  --workspace "$WORKSPACE_ID" \
  --analytics-query "
    AppDependencies
    | where TimeGenerated between (datetime('$INCIDENT_START') .. datetime('$INCIDENT_END'))
    | where Success == false
    | summarize failures=count() by Type, Name, Target, ResultCode
    | order by failures desc
  " \
  --output table
```

## Final thoughts

Blameless postmortems work when people can speak plainly, the evidence is concrete, and follow-up actually happens. Azure Monitor gives you the data. KQL helps reconstruct the sequence. Logic Apps wires the draft together.

That is the foundation. In [Part 2](/postmortems-azure-automation-devops-metrics-part-2/), the focus shifts to Azure DevOps, MTTD and MTTR metrics, Workbook dashboards, and the rest of the SRE improvement loop.

## What can go wrong

1. **Blame creep despite blameless intent** — The template says "contributing factors," but during the review meeting someone starts saying "if only team X had done Y." The facilitator must redirect language in real time. Consider a written ground rule at the top of every review: "We discuss systems, not individuals."
2. **Incomplete timeline** — If the team waits more than 48 hours to start the postmortem, key details (who was paged, what was tried first, which runbook was used) fade from memory. Trigger the draft within 24 hours of resolution, even if it's incomplete.
3. **KQL query brittleness** — The queries in this post reference specific table names and columns (`AppExceptions`, `AzureActivity`, `AzureDiagnostics`). If your workspace uses custom tables, resource-specific logs, or a different naming convention, the queries need adaptation. Test every query in your own Log Analytics workspace before adding it to the template.
4. **Logic App trigger false starts** — The severity-based Logic App trigger fires on alert resolution, but if the alert auto-resolves and re-fires within minutes (flapping), you get multiple draft postmortems for the same incident. Add deduplication logic based on incident ID or a cooldown window.
5. **Overly detailed postmortems** — A 20-page document with every log line pasted in is worse than no postmortem. Focus on the 5 most significant events in the timeline and link to the raw logs rather than inlining them.

## Series navigation

- **Postmortems in Azure — Part 1: Blameless incident analysis** ← you are here — covers the mechanics: template, timeline, contributing factors, KQL evidence
- [Postmortems in Azure — Part 2: Automation, DevOps, and metrics](/postmortems-azure-automation-devops-metrics-part-2/) — covers the operating model: automation, tracking, dashboards

## Further reading

- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview)
- [Log Analytics overview](https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-overview)
- [Azure Logic Apps overview](https://learn.microsoft.com/azure/logic-apps/logic-apps-overview)
- [KQL reference](https://learn.microsoft.com/kusto/query/)
