---
slug: "deterministic-429-watchdog-azure-openai"
translationKey: "watchdog-429-deterministico-azure-openai"
title: "Building a Deterministic 429 Watchdog for Azure OpenAI"
description: "An MCP server that detects token consumption trends before the 429 happens — no LLM required, just metrics and a cron job."
date: 2026-07-08T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - azure-openai
  - monitoring
  - mcp
  - terraform
  - sre
  - throttling
series:
  - "MCP Agents and Infrastructure"
---
# Chapter 2: The Deterministic 429 Watchdog

In the previous post I explained what MCP is and how an agent decides the sequence of calls on its own from the tools available. Now let's build a real use case, scoped small enough to finish in a weekend: an MCP server that watches token consumption on your Azure OpenAI / AI Foundry deployment and warns you on Slack or email **before** the 429 happens, not after the client has already eaten the error in production.

## Why this is subtler than it looks

The first reaction from anyone who's never been bitten by a 429 is "easy, just measure usage and compare it to the quota." The problem is that TPM (tokens per minute) and RPM (requests per minute) on Azure OpenAI are evaluated over **rolling** windows, on short intervals, typically 1 to 10 seconds, not a smooth average across the minute. That means you can blow the limit even while staying "under quota" in aggregate, simply because requests arrived in a burst instead of spread out. That's why teams report 429s "even within the documented limit": the problem isn't total volume, it's distribution over time.

The industry-standard answer is retry with exponential backoff and jitter, reading the `retry-after-ms` header the API already returns. That's necessary, but it's reactive: the client already felt the error. What we want here is the layer before that: seeing the consumption trend climb toward the limit and acting before the first 429 ever fires.

## What Azure already solves without you writing a line of code

Before building anything, though: the platform already solves a good chunk of this on its own. Azure OpenAI exposes native metrics in Azure Monitor per deployment: the real API names are `TokenTransaction` (processed tokens), `AzureOpenAIRequests` (total calls), `ProcessedPromptTokens`, `GeneratedTokens`, and the latency metrics, all filterable by the `ModelDeploymentName` dimension. A simple threshold alert, "warn when `TokenTransaction` crosses X tokens in 1 minute", doesn't need an agent, MCP, or any code at all. It's an `azurerm_monitor_metric_alert` pointing at an `azurerm_monitor_action_group` with email and a Slack webhook, solved in plain Terraform:

```hcl
resource "azurerm_monitor_action_group" "ia_oncall" {
  name                = "ag-ia-oncall"
  resource_group_name = azurerm_resource_group.ia.name
  short_name          = "iaoncall"

  email_receiver {
    name          = "sre-team"
    email_address = "sre-ai@yourcompany.com"
  }

  webhook_receiver {
    name        = "slack-webhook"
    service_uri = var.slack_webhook_url
  }
}

resource "azurerm_monitor_metric_alert" "tpm_80pct" {
  name                = "alert-tpm-80pct-gpt4o"
  resource_group_name = azurerm_resource_group.ia.name
  scopes              = [azurerm_cognitive_account.openai.id]
  description         = "TokenTransaction crossed 80% of configured TPM on the gpt-4o-prod deployment"
  severity            = 2
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.CognitiveServices/accounts"
    metric_name      = "TokenTransaction"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 200000 # 80% of a 250k TPM deployment — adjust to yours

    dimension {
      name     = "ModelDeploymentName"
      operator = "Include"
      values   = ["gpt-4o-prod"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.ia_oncall.id
  }
}
```

That alone already covers the most common case, with no agent, no MCP, no code to maintain. The full Terraform, including the `azurerm_cognitive_account` and `azurerm_cognitive_deployment` referenced above, is in the series companion repo (link in post 5).

The reason it's still worth building the MCP server on top of this is what that native alert **doesn't** do: it fires once when it crosses the threshold, but it doesn't see the slope of the curve (climbing fast vs. flattening out), doesn't compare against the historical pattern for the same time of day, and doesn't consolidate TPM, RPM, and error rate into a single message with context. For that, the tool needs to query the time series and compute trend. That's where code comes in.

## The architecture

The server exposes a deliberately small set of tools, split into two groups that don't mix: telemetry reads and notifications. No tool with the power to act on the resource itself: nothing that bumps quota or redistributes traffic on its own. That's intentional, and I'll explain why further down.

```
 ┌─────────────────────────────┐
 │            HOST              │   Claude / agent runtime / simple cron
 └──────────────┬────────────────┘
                 │ MCP (stdio or HTTP)
                 ▼
 ┌─────────────────────────────┐
 │     MCP SERVER: watchdog429   │
 │  get_token_usage_trend        │
 │  get_token_usage_history      │
 │  send_slack_alert             │
 │  send_priority_alert          │
 └──────────────┬────────────────┘
                 ▼
   Azure Monitor (TokenTransaction, AzureOpenAIRequests)
```

The central tool is `get_token_usage_trend`. It queries the Azure Monitor metrics API for the Azure OpenAI resource via the official `azure-monitor-query` package (`MetricsQueryClient`), pulls `TokenTransaction` over a short window (say, the last 5 minutes in 1-minute buckets, filtered by `ModelDeploymentName`), and returns the percentage of configured TPM already consumed, along with the slope of the curve: not just "how much," but "how fast it's climbing."

```python
# pip install mcp azure-monitor-query azure-identity
from datetime import timedelta
from mcp.server.fastmcp import FastMCP
from azure.monitor.query import MetricsQueryClient
from azure.identity import DefaultAzureCredential

mcp = FastMCP("watchdog429")
metrics_client = MetricsQueryClient(DefaultAzureCredential())

OPENAI_RESOURCE_ID = os.environ["OPENAI_RESOURCE_ID"]

@mcp.tool()
def get_token_usage_trend(deployment_name: str, window_minutes: int = 5) -> dict:
    """Returns the percentage of TPM consumed over the last N minutes for the
    given deployment, plus the trend (rising/stable/falling). Uses the native
    TokenTransaction Azure Monitor metric, filtered by the ModelDeploymentName
    dimension. Performs no action on the deployment itself."""
    response = metrics_client.query_resource(
        resource_uri=OPENAI_RESOURCE_ID,
        metric_names=["TokenTransaction"],
        timespan=timedelta(minutes=window_minutes),
        granularity=timedelta(minutes=1),
        filter=f"ModelDeploymentName eq '{deployment_name}'",
    )
    series = [p.total or 0 for p in response.metrics[0].timeseries[0].data]
    tpm_limit = get_configured_tpm(deployment_name)  # comes from your Terraform/inventory
    pct_used = sum(series) / tpm_limit
    trend = "rising" if series[-1] > series[0] else "stable"
    return {"deployment_name": deployment_name, "pct_of_tpm": pct_used, "trend": trend, "window_minutes": window_minutes}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

And the notification tool is deliberately dumb: it doesn't decide anything, it just sends what it's told to:

```python
@mcp.tool()
def send_slack_alert(channel: str, message: str) -> str:
    """Sends a message to a Slack channel. Doesn't decide the content,
    just transmits it. The decision to alert belongs to whoever calls this tool."""
    httpx.post(SLACK_WEBHOOK_URL, json={"channel": channel, "text": message}, timeout=10)
    return "sent"
```

## The simplest version that already works

For this post, the "agent" can start as a script on a one-minute cron, with no LLM in the loop at all: call `get_token_usage_trend`, and if `pct_of_tpm > 0.8`, call `send_slack_alert`. That already solves 80% of the practical problem, and it's what I'd recommend shipping first, before putting a model in charge of the decision, prove the telemetry and the alert actually work.

```python
trend = get_token_usage_trend("gpt-4o-prod", window_minutes=5)
if trend["pct_of_tpm"] > 0.8 and trend["trend"] == "rising":
    send_slack_alert("#oncall-ai", f"Deployment gpt-4o-prod at {trend['pct_of_tpm']:.0%} of TPM and rising")
```

Notice this doesn't even need a real MCP host; it's just a script calling the same functions the server exposes. The payoff from packaging it as MCP comes later, when you want a more general-purpose agent (the same one that already investigates the AKS cluster in the previous post) to also see this telemetry without you writing a new integration for every consumer.

## Where this gets interesting (and where it gets dangerous)

The fixed-threshold version (80%, 90%, whatever) has a classic monitoring problem: it can't tell a legitimate end-of-month spike, such as a batch job that always eats 90% of quota for 10 minutes and then returns to normal, from some agent loose somewhere in your environment looping and burning tokens nonstop, which is exactly the scenario from the previous post. Both cross the same threshold; only one of them deserves a page.

That's where the next piece of the series comes in: giving the monitor a reasoning layer instead of a fixed `if`, so it can compare the current pattern against recent history before deciding between "heads-up on Slack" and "an actual page." That's the subject of the next post: moving from a deterministic script to an agent that actually decides, with the right guardrails so that decision doesn't get out of hand.

For now, the most important guardrail is already in the design: the server **only reads telemetry and only writes to notification channels**. It doesn't have, and shouldn't have, any tool capable of changing quota, redistributing traffic across regions, or restarting a deployment. Before this agent gets any power to act on the resource, it needs to first prove, in production, that it can tell noise from signal. That's post 3.

## Up next in the series

1. ✅ MCP and agents: the 101 (with the AKS-MCP example)
2. ✅ This post: the server that detects 429 trends before they happen
3. From script to agent: giving the watchdog decision autonomy, with explicit guardrails against alert fatigue
4. Multi-agent teams in practice: combining AKS diagnostics with the quota watchdog into a single orchestrator
5. Baseline governance for Azure AI Foundry agents

If you want to test the pure-script version before even touching MCP, it's literally the two functions above and a cron job. Start there.

---

*This is post 2 of the series "MCP, Agents, and Agent Teams for Infrastructure Engineers":*

1. [MCP and Agents 101](/2026/07/01/mcp-and-agents-101-for-infra-engineers/)
2. **The Deterministic 429 Watchdog**
3. [From Script to Agent](/2026/07/14/agentic-watchdog-decision-autonomy-guardrails/)
4. [Multi-Agent Orchestration](/2026/07/21/multi-agent-orchestration-aks-openai-correlation/)
5. [Governance on Microsoft Foundry](/2026/07/28/agent-governance-microsoft-foundry/)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/watchdog-429-deterministico-azure-openai/).*
