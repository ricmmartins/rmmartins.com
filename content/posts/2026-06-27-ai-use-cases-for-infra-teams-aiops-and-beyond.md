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

Thirteenth post in the series. In the [previous one](/2026/06/23/troubleshooting-playbook-incidents-that-will-wake-you-at-2am/), we diagnosed the incidents that wake you up at 2 AM. Now something different: how to use AI to improve the infrastructure work itself.

## Flipping the perspective

Over the past 12 posts, you've been building infra for AI: GPUs, clusters, pipelines, security, monitoring, cost management. You've become an expert at providing compute for data scientists.

But what about using AI for **your** work? Log analysis, anomaly detection, capacity planning, IaC generation, automated incident response. AIOps isn't a new buzzword; it's the practical application of what you already understand (models, inference, tokens) to your day-to-day operations.

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
        model="gpt-4o",
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

> **Cost:** A 5,000-token block of logs (prompt + analysis) costs ~$0.015 with GPT-4o. Reasonable for on-demand incident response. Not reasonable for processing every log entry automatically.

## Use case 2: anomaly detection in metrics

### The problem

Static-threshold alerts generate fatigue. CPU > 80%? Could be normal during a deploy. Memory > 90%? Maybe that's the workload's stable pattern. You need to detect anomalies relative to normal behavior, not absolute values.

### The solution

Azure Monitor has native anomaly detection using ML:

```bash
# Alert rule with dynamic thresholds
az monitor metrics alert create \
  --name "gpu-util-anomaly" \
  --resource-group rg-ai-prod \
  --scopes "/subscriptions/{sub}/resourceGroups/rg-ai-prod/providers/Microsoft.Compute/virtualMachines/gpu-vm-01" \
  --condition "avg DCGM_FI_DEV_GPU_UTIL > dynamic medium of 3 violations out of 5 aggregated points" \
  --action-group ag-oncall \
  --description "GPU utilization anomaly detected"
```

Dynamic thresholds learn the workload's seasonal pattern (peak hours, nightly batch jobs, quiet weekends) and alert when behavior deviates from what's expected, not when it crosses an arbitrary number.

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

Use historical consumption data with time series forecasting to predict when you'll hit quotas or capacity limits:

```kusto
// KQL: project GPU quota consumption for the next 4 weeks
let forecast_window = 28d;
AzureMetrics
| where ResourceProvider == "MICROSOFT.COMPUTE"
| where MetricName == "Percentage CPU" // proxy for GPU utilization
| where TimeGenerated > ago(90d)
| summarize AvgUsage = avg(Average) by bin(TimeGenerated, 1d)
| make-series Usage = avg(AvgUsage) default=0 on TimeGenerated step 1d
| extend forecast = series_decompose_forecast(Usage, toint(forecast_window / 1d))
| project TimeGenerated, Usage, forecast
```

### Combining with Azure OpenAI for narrative

A numeric forecast is useful but not actionable without context. Use an LLM to generate a readable recommendation:

"Based on current GPU consumption trends (+12% week-over-week), you'll exceed the NC24ads_A100_v4 quota in East US within 18 days. Recommended actions: (1) request quota increase now (takes 3-5 business days), (2) evaluate moving batch workloads to West US where utilization is 40% lower."

## Use case 4: IaC generation and review

### The problem

Writing Bicep/Terraform for GPU clusters is repetitive and error-prone. Remembering every parameter for NVIDIA driver extensions, node pool taints, network policies, resource quotas.

### The solution

GitHub Copilot in the editor or Azure OpenAI for template generation:

- **Generation:** "Create a Bicep module for an AKS cluster with NC24ads_A100_v4 GPU node pool, DCGM exporter, managed identity, private endpoint for ACR"
- **Review:** Submit existing IaC for AI review against best practices (security checklist, cost optimization, HA)
- **Migration:** "Convert this ARM template to Bicep maintaining the same functionality"

### Validation is still on you

AI generates, but you validate. Never apply AI-generated IaC without:
1. Reading the output and understanding what each resource does
2. Validating against official documentation (Azure CLI reference, Bicep docs)
3. Running `az deployment group what-if` before any apply
4. Code review by another engineer

## Use case 5: assisted incident response

### The problem

At 2 AM, running on adrenaline and sleep deprivation, you need to diagnose fast. The less you depend on memory, the better.

### The solution

Interactive runbooks with AI as co-pilot:

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

The rule: AI excels at tasks requiring interpretation of unstructured text, complex pattern detection, and draft generation. Traditional tools are better for enforcement, auditing, and deterministic actions.

## In the next post

Practical use cases covered. Next, we go up a level: the **AI adoption framework** for organizations. How to go from "let's use AI" to a governed, scalable, and cost-effective platform, phase by phase.

---

*This is post 13 of the series "AI for Infrastructure Engineers", based on the book [AI for Infrastructure Professionals](https://ai4infra.com):*

1. [Why AI Needs You](/2026/05/10/ai-for-infrastructure-engineers-why-ai-needs-you/)
2. [Data and Storage](/2026/05/14/data-and-storage-for-ai-workloads/)
3. [Compute: Choosing the Right Hardware](/2026/05/18/compute-for-ai-choosing-the-right-hardware/)
4. [GPU Deep Dive](/2026/05/22/gpu-deep-dive-what-happens-inside-the-silicon/)
5. [Infrastructure as Code for AI](/2026/05/26/infrastructure-as-code-for-ai-automating-gpu-clusters/)
6. [MLOps: Model Lifecycle](/2026/05/30/mlops-model-lifecycle-for-infra-engineers/)
7. [Monitoring and Observability](/2026/06/03/monitoring-and-observability-for-ai/)
8. [Security for AI](/2026/06/07/security-for-ai-threats-your-firewall-wont-catch/)
9. [Cost Engineering for AI](/2026/06/11/cost-engineering-for-ai-when-idle-gpus-cost-more-than-your-car/)
10. [Platform Ops: Self-Service AI Platform](/2026/06/15/platform-ops-building-a-self-service-ai-platform/)
11. [Azure OpenAI in Production](/2026/06/19/azure-openai-in-production-tokens-throughput-and-high-availability/)
12. [Troubleshooting Playbook](/2026/06/23/troubleshooting-playbook-incidents-that-will-wake-you-at-2am/)
13. **AI Use Cases for Infra Teams**
14. [AI Adoption Framework](/2026/07/01/ai-adoption-framework-from-enthusiasm-to-governance/)
15. [Visual Glossary: Your Rosetta Stone](/2026/07/05/visual-glossary-infra-ai-your-rosetta-stone/)

