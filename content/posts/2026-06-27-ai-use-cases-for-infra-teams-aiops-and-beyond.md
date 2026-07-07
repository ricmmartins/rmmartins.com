---
slug: "ai-use-cases-for-infra-teams-aiops-and-beyond"
translationKey: "ai-use-cases-pra-infra-teams-aiops-e-alem"
title: "AI use cases for infra teams: AIOps and beyond"
description: "AI isn't just for data scientists. Log analysis with LLMs, anomaly detection, predictive capacity planning, IaC generation, and how to use AI to improve your own infra work."
date: 2026-06-27T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - aiops
  - copilot
  - anomaly-detection
  - capacity-planning
series:
  - "AI for Infrastructure Engineers"
---

Thirteenth post in the series. In the [previous one](/2026/06/23/troubleshooting-playbook-incidents-that-will-wake-you-at-2am/), we dealt with the incidents that wake you up at 2 AM. This time the angle flips: using AI to make the infrastructure work itself less miserable.

## Flipping the perspective

Over the past 12 posts, you've been building infra for AI: GPUs, clusters, pipelines, security, monitoring, cost management. You know how to keep the runway paved for data scientists.

But what about using AI for **your** work? Log analysis, anomaly detection, capacity planning, IaC generation, assisted incident response. AIOps is not magic and it is not new. It is just applying the same model and inference patterns to day-to-day operations.

## Use case 1: log analysis with LLMs

### The problem

An AKS cluster with 50 microservices generates hundreds of thousands of log entries per hour. When an incident happens, you grep for errors, correlate timestamps, and try to construct the timeline manually. If you're lucky, it takes 30 minutes. If not, hours.

### The solution

LLMs are good at processing unstructured text and extracting patterns. Send a block of logs to Azure OpenAI with a well-crafted prompt:

```python
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint="https://aoai-prod.openai.azure.com/",
    api_version="2024-06-01"
)

def analyze_logs(log_block):
    response = client.chat.completions.create(
        model="gpt-4o-prod",
        messages=[
            {"role": "system", "content": """You are an SRE analyzing Kubernetes logs.
Given a block of logs, identify:
1. The root cause event (first error in the chain)
2. Cascading failures triggered by it
3. Affected services
4. Suggested remediation
Be specific about timestamps and service names."""},
            {"role": "user", "content": f"Analyze these logs:\n\n{log_block}"}
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content
```

### When this works well

- Incident post-mortem: summarize 10,000 lines of logs into a concise timeline
- Cross-service correlation: identify that an error in Service A caused a cascade in B, C, D
- Pattern matching: "these logs look like the incident from last March"

### When not to replace specialized tools

- Real-time alerting: use Azure Monitor alerts, not LLM inference
- Compliance and auditing: needs reproducible structured queries (KQL)
- Very high volume: sending all logs to an LLM is expensive and slow

> **Cost:** Pricing moves, but a 5,000-token log investigation with GPT-4o is still measured in cents. Fine for on-demand incident response. Silly for every log line.

## Use case 2: anomaly detection in metrics

### The problem

Static-threshold alerts generate fatigue. CPU > 80%? Could be normal during a deploy. Memory > 90%? Maybe that's the workload's stable pattern. You need to detect anomalies relative to normal behavior, not absolute values.

### The solution

Azure Monitor has native anomaly detection using dynamic thresholds:

```bash
# Alert rule with dynamic thresholds
az monitor metrics alert create \
  --name "gpu-host-cpu-anomaly" \
  --resource-group rg-ai-prod \
  --scopes "/subscriptions/{sub}/resourceGroups/rg-ai-prod/providers/Microsoft.Compute/virtualMachines/gpu-vm-01" \
  --condition "avg Percentage CPU > dynamic medium 3 of 5" \
  --action ag-oncall \
  --window-size 5m \
  --evaluation-frequency 1m \
  --description "Unexpected CPU anomaly on a GPU host"
```

Dynamic thresholds learn the workload's seasonal pattern and alert when behavior deviates from what is normal, not when it crosses a number somebody guessed six months ago. If you are working with DCGM metrics through Managed Prometheus, use the same idea there, but through Prometheus recording and alerting rules rather than Azure metric alerts.

### Good metrics for anomaly detection

| Metric | Why it works well | What static thresholds miss |
|--------|-------------------|----------------------------|
| GPU utilization | Strong seasonal pattern (training schedule) | Legitimate training would trigger alerts |
| API latency P95 | Stable baseline with significant deviations | Normal value varies by time of day |
| Error rate | Near-zero normally, any spike matters | 0.1% can be normal or catastrophic depending on volume |
| Token consumption | Correlated with actual usage | Organic growth vs anomalous spike |

## Use case 3: predictive capacity planning

### The problem

Traditional capacity planning: look at current usage, project linear growth, add margin. Works for stable workloads. Doesn't work for AI, where usage is bursty and growth is unpredictable.

### The solution

Use historical consumption data with time series forecasting to predict when you will hit quotas or capacity limits:

```kusto
// KQL: project Azure OpenAI token consumption for the next 4 weeks
let forecast_window = 28d;
AzureMetrics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where MetricName == "TokenTransaction"
| where TimeGenerated > ago(90d)
| summarize DailyTokens = sum(Total) by bin(TimeGenerated, 1d)
| make-series DailyTokens = avg(DailyTokens) default=0
    on TimeGenerated from startofday(ago(90d)) to startofday(now()) step 1d
| extend forecast = series_decompose_forecast(DailyTokens, toint(forecast_window / 1d))
| project TimeGenerated, DailyTokens, forecast
```

### Combining with Azure OpenAI for narrative

A numeric forecast is useful, but operations teams still need the plain-English version. Use an LLM to generate a readable recommendation:

"Based on current token consumption trends (+12% week-over-week), you'll run out of your East US `gpt-4o` quota buffer in about 18 days. Recommended actions: request more quota now, trim the system prompt, or spill overflow traffic into a second region."

## Use case 4: IaC generation and review

### The problem

Writing Bicep/Terraform for GPU clusters is repetitive and error-prone. Remembering every parameter for NVIDIA driver extensions, node pool taints, network policies, resource quotas.

### The solution

GitHub Copilot in the editor or Azure OpenAI for template generation:

- **Generation:** "Create a Bicep module for an AKS cluster with NC24ads_A100_v4 GPU node pool, DCGM exporter, managed identity, private endpoint for ACR"
- **Review:** Submit existing IaC for AI review against best practices (security checklist, cost optimization, HA)
- **Migration:** "Convert this ARM template to Bicep maintaining the same functionality"

### Validation is still on you

AI generates. You validate. Never apply AI-generated IaC without:
1. Reading the output and understanding what each resource does
2. Validating against official documentation (Azure CLI reference, Bicep docs)
3. Running `az deployment group what-if` for Bicep or `terraform plan` for Terraform before any apply
4. Code review by another engineer

## Use case 5: assisted incident response

### The problem

At 2 AM, running on adrenaline and sleep deprivation, you need to diagnose fast. The less you depend on memory, the better.

### The solution

Interactive runbooks with AI as a copilot:

1. Alert fires → webhook calls Logic App
2. Logic App collects context: recent logs, metrics, recent changes
3. Azure OpenAI analyzes context and suggests diagnosis + next commands
4. On-call engineer receives suggestion in Teams/Slack

It doesn't replace the engineer. It reduces diagnosis time when you're operating at 30% cognitive capacity at 2 AM.

## Decision matrix: when to use AI vs. traditional tools

| Scenario | Use AI | Use traditional tooling |
|----------|:---:|:---:|
| Ad-hoc incident analysis | ✅ | |
| Real-time alerting | | ✅ (Azure Monitor) |
| IaC draft generation | ✅ | |
| Compliance validation | | ✅ (Azure Policy) |
| Post-mortem summarization | ✅ | |
| RBAC enforcement | | ✅ (Entra ID) |
| Capacity forecasting | ✅ (for narrative) | ✅ (for numbers, KQL) |
| Anomaly detection | ✅ (dynamic thresholds) | ✅ (if static threshold suffices) |

The rule is simple: AI helps when the job involves messy text, pattern recognition, or drafting. Traditional tooling wins when the job is enforcement, auditing, or any action that has to be deterministic.

## In the next post

That is the practical layer. Next comes the **AI adoption framework** for organizations: how to get from "let's use AI" to a platform that is governed, scalable, and not quietly setting money on fire.