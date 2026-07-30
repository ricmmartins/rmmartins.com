---
slug: "postmortems-azure-automation-devops-metrics-part-2"
aliases:
  - "/2026/07/13/postmortems-azure-automation-devops-metrics-part-2/"
translationKey: "postmortems-no-azure-automacao-devops-metricas-parte-2"
title: "Postmortems on Azure: automation with Azure DevOps and learning metrics (Part 2)"
description: "Integrate postmortems with Azure DevOps, measure effectiveness with MTTD/MTTR metrics, build Workbooks dashboards, and connect to the complete SRE cycle."
date: 2026-07-13T10:30:00-04:00
categories:
  - Azure
  - SRE
tags:
  - postmortem
  - azure-devops
  - kql
  - mttd
  - mttr
  - sre
  - observability
  - incident-management
series:
  - "Azure SRE"
---

Second post in the Azure postmortem series. In [Part 1](/postmortems-azure-blameless-incident-analysis-part-1/), we built the foundation: blameless culture, a reusable template, KQL-based evidence collection, and Logic Apps automation. Now we move from documentation to operations.

A mature postmortem process should leave traces in the engineering system: linked work items, measurable trends, dashboards, and visible feedback into reliability practices such as SLOs, alert tuning, and chaos experiments. If a postmortem ends as a document nobody operationalizes, the process failed.

## tl;dr

- The postmortem is only useful when it changes the system.
- Track follow-up in Azure DevOps and measure learning with MTTD, MTTR, and recurrence.
- Feed the results back into SLOs, alerts, runbooks, and chaos tests.

## Integrating postmortems with Azure DevOps

Azure DevOps is the natural place to track remediation work, especially when incident improvements compete with feature work. The point is not to “store the document in DevOps.” The point is to make the learning executable.

### Creating a work item for postmortem follow-up

You can use the built-in `Bug` type or introduce a custom work item type for incident reviews. Even if you stay with `Bug`, standardize fields and tags so the portfolio becomes queryable.

```bash
# Configure Azure DevOps CLI first
az extension add --name azure-devops

# Set the organization and project defaults
az devops configure --defaults organization=https://dev.azure.com/myorg project=MyProject

# Create a work item for a new postmortem
az boards work-item create \
  --type "Bug" \
  --title "Postmortem: [Incident Title]" \
  --description "$(cat postmortem-template.md)" \
  --area "\\MyProject\\SRE" \
  --iteration "\\MyProject\\Current-Sprint" \
  --fields "System.Tags=postmortem;sev-1;action-required" \
           "Microsoft.VSTS.Common.Priority=1" \
           "Microsoft.VSTS.Common.Severity=1 - Critical"
```

### Recommended Azure DevOps structure

| Artifact | Recommendation | Why it helps |
|---------|----------------|--------------|
| **Parent work item** | One incident review item per SEV-1 or SEV-2 event | Gives the incident a durable engineering record |
| **Child items** | One work item per remediation action | Makes follow-up measurable |
| **Tags** | `postmortem`, `sev-1`, `incident-review`, service name | Enables queries, widgets, and dashboards |
| **Area path** | Central SRE or service-specific area | Makes ownership visible |
| **Iteration path** | Current or next sprint | Forces prioritization instead of “someday” |

### WIQL query for open postmortem action items

```wiql
SELECT [System.Id], [System.Title], [System.State],
       [System.AssignedTo], [Microsoft.VSTS.Scheduling.TargetDate],
       [System.Tags]
FROM WorkItems
WHERE [System.TeamProject] = @project
  AND [System.Tags] CONTAINS "postmortem"
  AND [System.State] <> "Closed"
  AND [System.State] <> "Done"
ORDER BY [Microsoft.VSTS.Common.Priority] ASC,
         [Microsoft.VSTS.Scheduling.TargetDate] ASC
```

### Useful Azure DevOps dashboard widgets

| Widget | Configuration | Purpose |
|--------|---------------|---------|
| **Query Results** | Open postmortem action items | See owners and current status |
| **Chart for Work Items** | Burndown by sprint | Track whether improvements actually close |
| **Query Tile** | Overdue action items | Surface reliability debt visually |
| **Chart for Work Items** | Action items by severity | Make prioritization obvious |
| **Markdown** | Link to the postmortem handbook | Give engineers fast process access |

## Postmortem metrics: are you learning or just documenting?

If you want executive sponsorship for postmortems, show outcomes. The best metrics are not vanity counts. They measure whether the organization learns faster and repeats failures less often.

### Core postmortem metrics

| Metric | Formula | Suggested target | What it tells you |
|--------|---------|------------------|-------------------|
| **Postmortem completion rate** | Completed postmortems / SEV-1 and SEV-2 incidents | 100% | Process adherence |
| **Time to postmortem** | Review date - incident resolution date | < 5 business days for SEV-1 | Learning speed |
| **Action item completion rate** | Completed actions / created actions | > 85% within 30 days | Improvement execution |
| **Overdue action items** | Overdue actions / total actions | < 10% | Team discipline |
| **Recurrence rate** | Incidents with similar root cause / total incidents | < 5% | Whether previous fixes worked |
| **MTTD** | Average time from impact start to detection | Downward trend | Observability maturity |
| **MTTR** | Average time from detection to recovery | Downward trend | Incident response effectiveness |

The important word in that table is **trend**. You do not need one magic number. You need evidence that the organization gets better over time.

## KQL queries for incident metrics

### Calculating MTTD and MTTR

```kql
// Calculating incident MTTD and MTTR (using custom logs or Sentinel)
let incidents = datatable(
    IncidentId: string,
    ImpactStart: datetime,
    DetectionTime: datetime,
    ResolutionTime: datetime,
    Severity: string
) [
    "INC-001", datetime("2026-04-01 14:00"), datetime("2026-04-01 14:03"), datetime("2026-04-01 15:30"), "SEV-1",
    "INC-002", datetime("2026-04-05 09:15"), datetime("2026-04-05 09:20"), datetime("2026-04-05 10:00"), "SEV-2",
    "INC-003", datetime("2026-04-10 22:00"), datetime("2026-04-10 22:15"), datetime("2026-04-10 23:45"), "SEV-1"
];
incidents
| extend
    MTTD_minutes = datetime_diff('minute', DetectionTime, ImpactStart),
    MTTR_minutes = datetime_diff('minute', ResolutionTime, DetectionTime),
    TotalDuration_minutes = datetime_diff('minute', ResolutionTime, ImpactStart)
| summarize
    AvgMTTD = round(avg(MTTD_minutes), 1),
    AvgMTTR = round(avg(MTTR_minutes), 1),
    AvgTotal = round(avg(TotalDuration_minutes), 1),
    P95_MTTR = round(percentile(MTTR_minutes, 95), 1),
    IncidentCount = count()
  by Severity
```

### Detecting recurring incidents

Recurring failures are where postmortems either prove their value or expose that the organization is mostly writing documents.

```kql
// Identify recurring incident patterns
AppExceptions
| where TimeGenerated > ago(90d)
| summarize
    OccurrenceCount = count(),
    DistinctDays = dcount(bin(TimeGenerated, 1d)),
    FirstOccurrence = min(TimeGenerated),
    LastOccurrence = max(TimeGenerated),
    AffectedOperations = dcount(OperationName)
  by ProblemId, ExceptionType = tostring(split(Type, ".")[-1])
| where DistinctDays > 3
| extend RecurrencePattern = iff(DistinctDays > 7, "Chronic", "Intermittent")
| order by OccurrenceCount desc
```

Use this output during quarterly reliability reviews. High recurrence almost always means one of three things: the fix was too local, the action item was never done, or the team misdiagnosed the real contributor.

## Creating an Azure Workbook for postmortem metrics

Azure Workbooks are ideal for turning postmortem data into something leaders and engineers can both consume.

```jsonc
// Pseudocode - adapt to actual Workbook ARM schema
{
  "version": "Notebook/1.0",
  "items": [
    {
      "type": "markdown",
      "content": "## Incident learning and postmortem metrics"
    },
    {
      "type": "query",
      "title": "MTTD and MTTR - monthly trend",
      "query": "// MTTD/MTTR query grouped by month",
      "visualization": "linechart"
    },
    {
      "type": "query",
      "title": "Recurring incident rate",
      "query": "// Recurring incident query",
      "visualization": "piechart"
    },
    {
      "type": "query",
      "title": "Top 10 exceptions - last 30 days",
      "query": "AppExceptions | where TimeGenerated > ago(30d) | summarize count() by ProblemId | top 10 by count_",
      "visualization": "barchart"
    }
  ]
}
```

A practical dashboard usually includes four sections:

1. **Incident volume and severity trend**
2. **MTTD and MTTR trend over time**
3. **Recurring exceptions and recurring services**
4. **Action item health: open, overdue, completed**

## Connecting postmortems to the full SRE cycle

A postmortem should close the loop across the rest of your reliability program.

### From postmortems to SLOs

Every meaningful review should ask:

- Which SLO was violated?
- How much Error Budget did we burn?
- Was detection slow because the wrong indicator was measured?
- Do we need to change the SLO, or improve the system so it can meet the existing one?

A common decision path looks like this:

```text
Postmortem -> Error Budget consumed > 50% -> Freeze feature releases
                                           -> Focus sprint on reliability
                                           -> Prioritize P1 action items
```

### From postmortems to chaos engineering

Incidents reveal the failure scenarios you should have tested proactively.

```text
Postmortem -> Root cause: timeout in dependency X
           -> Action item: create a Chaos Studio experiment
           -> Scenario: inject latency into dependency X
           -> Validation: does the circuit breaker trip in < 5 seconds?
```

### From postmortems to alerts and runbooks

| Gap found in the postmortem | Follow-up action |
|-----------------------------|------------------|
| Alert fired 10 minutes after customer impact started | Reduce alert window size from 10 to 5 minutes |
| Runbook did not cover rollback for service Y | Create a dedicated rollback runbook for service Y |
| On-call engineer lacked access to a required resource | Review RBAC for the on-call rotation |
| Stakeholder communication was delayed | Add automatic notification through an Action Group |

## Advanced scenarios

### Automated postmortem draft with an SRE agent

If your organization uses an internal SRE assistant or Azure-focused troubleshooting agent, the most useful automation is getting the first draft on the page:

1. Rebuild the timeline from Azure Monitor, Activity Logs, and Resource Health.
2. Correlate recent changes with the first signs of degradation.
3. Suggest candidate action items based on recurring gaps.
4. Produce a draft that the facilitator reviews before the meeting.

The boundary is simple: use automation for **collection and synthesis**, not for assigning blame or declaring root cause with false certainty.

### Cross-cloud postmortems

Many modern incidents span Azure plus another provider or SaaS boundary. In those cases, extend the postmortem with a few extra sections.

| Additional section | Why it matters |
|-------------------|----------------|
| **Cross-cloud topology** | Shows which components in each platform were involved |
| **Timestamp correlation** | Validates that all systems are aligned to UTC |
| **Integration points** | Highlights the APIs, queues, or data planes that crossed boundaries |
| **Per-cloud evidence** | Separates Azure Monitor data from CloudWatch or other telemetry sources |
| **Observability recommendations** | Captures missing correlation IDs or tracing gaps |

### Failed-request-count review workflows

```bash
# Example alert based on failed request count that forces a review
az monitor metrics alert create \
  --resource-group rg-monitoring \
  --name "failed-requests-critical" \
  --scopes "/subscriptions/{sub}/resourceGroups/rg-app/providers/Microsoft.Insights/components/app-production" \
  --condition "total requests/failed > 50" \
  --window-size 1h \
  --evaluation-frequency 5m \
  --action ag-postmortem-trigger \
  --description "Failed request count above threshold - investigate service reliability impact" \
  --severity 1
```

## Running the review meeting well

The meeting is where an incident stops being a Slack story and becomes shared engineering learning.

### Before the meeting

| Preparation | Owner | Deadline |
|------------|-------|----------|
| Complete draft with timeline and data | Postmortem author | 24 hours before |
| All participants review the draft | Everyone | 4 hours before |
| Prepare focused discussion questions | Facilitator | 2 hours before |
| Book 60-90 minutes with the right attendees | Facilitator | When scheduling |

### During the meeting

1. **Restate the blameless principle** in the first minute.
2. **Walk the timeline chronologically** and correct missing context.
3. **Discuss root cause and contributing factors** using structured questioning.
4. **Capture what worked, what did not, and where luck helped.**
5. **Define action items** with owner, deadline, and completion criteria.
6. **End on time** with explicit next steps.

### The 5 Whys technique in practice

```text
Incident: Payment API returned 500s for 45 minutes

Why? -> The database connection pool was exhausted.

Why? -> One query took 30 seconds instead of 200 ms.

Why? -> The transactions table index was removed.

Why? -> A CI/CD migration removed the index.

Why? -> The migration was not reviewed by someone with
         production schema expertise.

Action item: Require peer review for database migrations,
             including an index impact checklist.
```

### Golden rules for the facilitator

- Never allow “Person X should have...” to stay unchallenged.
- If someone becomes defensive, acknowledge complexity and redirect to the system.
- Park side topics instead of letting the meeting drift.
- Pull in quieter participants explicitly; they often have the observations everyone else missed.
- Keep the cadence efficient. If the process feels wasteful, teams will stop taking it seriously.

## Common mistakes and how to avoid them

| Mistake | Impact | How to avoid it |
|--------|--------|-----------------|
| Writing the postmortem weeks later | Lost detail, fuzzy timeline | Start the draft within 24 hours; automate evidence collection |
| No owners for action items | Nothing gets implemented | Every action item needs owner, due date, and completion definition |
| No follow-up on action items | Repeat incidents keep happening | Review the dashboard weekly |
| Overly long, bureaucratic documents | Teams disengage from the process | Keep the template focused on actionable learning |
| Skipping the “where we got lucky” section | Hidden risk remains invisible | Always document near-misses and luck factors |
| Restricting visibility too much | The wider engineering org does not learn | Share postmortems broadly unless sensitive data blocks it |
| Treating incidents in isolation | Systemic patterns remain hidden | Review trends quarterly across services |
| Skipping reviews for “simple” incidents | Operational debt accumulates | Define clear review thresholds up front |

## Conclusion and implementation checklist

A blameless Azure postmortem process is not done when the document is approved. It is done when the system changes.

### Implementation checklist

1. Adopt the template from [Part 1](/postmortems-azure-blameless-incident-analysis-part-1/).
2. Save the KQL queries needed for fast evidence collection.
3. Trigger draft creation automatically when critical alerts resolve.
4. Track every postmortem and action item in Azure DevOps.
5. Build a Workbook for MTTD, MTTR, recurrence, and follow-up health.
6. Feed gaps back into alerts, runbooks, SLOs, and chaos scenarios.
7. Run quarterly trend reviews across all postmortems.

Part 1 covers the mechanics. Part 2 covers the operating model. Put together, they turn Azure incidents into a repeatable learning system instead of a cycle of institutional amnesia.

## What can go wrong

1. **Action items survive in the backlog forever.** Without a hard SLA (e.g., P1 items closed within 14 days), postmortem follow-ups compete with feature work and always lose. Use the overdue query from this post as a weekly PagerDuty-style check.
2. **Recurrence detection returns false positives.** The `ProblemId`-based KQL query groups by exception signature, not by user-facing impact. Two exceptions with the same `ProblemId` may affect different customers for different reasons. Validate recurrence by cross-referencing with the incident timeline, not just exception counts.
3. **MTTD/MTTR numbers become vanity metrics.** Teams optimize the number (declaring detection earlier, closing incidents faster) instead of the outcome. Track alongside customer-facing SLO burn to keep honesty.
4. **Workbook schema drift.** The Workbook JSON in this post is pseudocode (`// Pseudocode - adapt to actual Workbook ARM schema`). The real ARM schema for Workbooks uses a different structure — export an existing Workbook as ARM template and adapt from there.
5. **Chaos experiment without a blast radius limit.** The "postmortem → chaos test" loop is powerful, but an experiment that injects real latency into a production dependency without a scope limit becomes its own SEV-1. Always set `StopOnFirstFailure` and scope to a single resource.

## Further reading
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview)
- [Log Analytics overview](https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-overview)
- [Investigate failures with Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/failures-performance-transactions)
- [Azure DevOps Work Items](https://learn.microsoft.com/azure/devops/boards/work-items/about-work-items)
- [Azure Logic Apps overview](https://learn.microsoft.com/azure/logic-apps/logic-apps-overview)
- [Azure Workbooks overview](https://learn.microsoft.com/azure/azure-monitor/visualize/workbooks-overview)
- [Google SRE Book - Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [KQL reference](https://learn.microsoft.com/kusto/query/)
