---
slug: "agentic-watchdog-decision-autonomy-guardrails"
aliases:
  - "/2026/07/14/agentic-watchdog-decision-autonomy-guardrails/"
translationKey: "watchdog-agente-autonomia-decisao-guardrails"
title: "From Script to Agent: Giving the Watchdog Decision Autonomy"
description: "Adding a reasoning layer to the 429 watchdog so it can tell a benign batch spike from a runaway agent, with explicit guardrails."
date: 2026-07-14T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai-agents
  - azure-openai
  - mcp
  - guardrails
  - sre
  - alert-fatigue
series:
  - "MCP Agents and Infrastructure"
---
# Chapter 3: From Script to Agent

In the previous post, the Azure OpenAI quota watchdog was a script with `if pct_of_tpm > 0.8: alert`. That works, but it has the same flaw every blunt monitoring rule has: context does not exist. A batch job that predictably eats 90% of TPM for 10 minutes at month-end looks identical to an agent gone feral and burning tokens all afternoon. Both cross the threshold. Only one should wake somebody up.

This post is about closing that gap: giving the watchdog a reasoning layer, without giving up any of the guardrails we've already set.

**tl;dr**
- The one-minute watchdog stays deterministic and only calls the model after the TPM threshold is crossed.
- The agent gets historical usage and priority-based alerting tools, not production write access.
- The model decides whether the event is `info`, `warning`, or `urgent` by comparing the current spike with past patterns.
- Audit the reasoning, rate-limit alerts, and review low-priority decisions so the watchdog stays useful.

## What changes (and what doesn't)

What does **not** change is the part that matters most: the server still only reads telemetry and only writes to notification channels. No new tool gets to act on the resource. Giving autonomy over *how to alert* is one thing. Giving autonomy to *change production* is a different class of problem, and two blog posts do not buy you that much operational maturity.

What changes is what happens between detecting the threshold and deciding what to do. Two new tools join the server:

```python
@mcp.tool()
def get_token_usage_history(deployment_name: str, days_back: int = 30) -> dict:
    """Returns the deployment's consumption pattern over the last N days,
    aggregated by day of week and hour of day, for comparison against
    the current spike."""
    response = _get_metrics_client().query_resource(
        resource_uri=OPENAI_RESOURCE_ID,
        metric_names=["TokenTransaction"],
        timespan=timedelta(days=days_back),
        granularity=timedelta(hours=1),
        filter=f"ModelDeploymentName eq '{deployment_name}'",
    )
    # aggregates by weekday-hour and returns avg/max per bucket
    ...

import httpx
from typing import Literal

@mcp.tool()
def send_priority_alert(message: str, priority: Literal["info", "warning", "urgent"]) -> str:
    """Posts an alert with a priority level. The caller decides the priority;
    this function only formats and sends the message."""
    prefix = {"info": "ℹ️", "warning": "⚠️", "urgent": "🚨 @oncall-ai"}[priority]
    httpx.post(SLACK_WEBHOOK_URL, json={"text": f"{prefix} {message}"}, timeout=10).raise_for_status()
    return "sent"
```

(`mcp` here is the same `FastMCP` instance created in post 2; these two tools join the same `watchdog429` server, not a separate one.)

The first one gives the agent a baseline for comparison: "has this happened before at this same time?" The second separates the act of notifying from the urgency level. The reasoning layer decides the level, not the tool.

## Where the model comes in (and where it doesn't)

One thing to get right here: **the model does not run every minute**. The deterministic script from post 2 stays the poller: it runs on the cron, once a minute, at zero LLM cost, and only triggers a model call once the threshold is crossed. Putting an LLM in the loop on every iteration of a monitoring cycle is wasting money on a path that, the overwhelming majority of the time, needs no reasoning at all. It's only worth paying the cost of a model call to decide the response level in the minutes the threshold actually gets crossed.

1. The cron poller runs once a minute with zero LLM cost.
2. If `get_token_usage_trend` stays at or below `0.8`, the loop ends and the next minute starts.
3. If the threshold is crossed, the host invokes the agent once.
4. The agent calls `get_token_usage_history`, reasons over the spike, and calls `send_priority_alert` with `info`, `warning`, or `urgent`.

The agent's system prompt stays small and direct: it doesn't need much more than this:

```
You are an Azure OpenAI quota watchdog. You were triggered because TPM
consumption passed 80%. Your only decision is the alert's priority
level: info, warning, or urgent.

Use get_token_usage_history to compare the current spike against the
pattern from the last 30 days at the same day of week and time.

- If the current pattern is consistent with past spikes at this same time: info.
- If it's an unprecedented spike but the curve is leveling off: warning.
- If it's an unprecedented spike AND the curve keeps climbing fast: urgent.

You have no tool that can act on the deployment. Your only possible
output is calling send_priority_alert exactly once.
```

Notice the last line: it exists to reinforce, in the prompt itself, the limit that's already baked into the architecture. Intentional redundancy. The real guardrail is the absence of the tool; the prompt is just the second layer.

**Where this actually runs**: the schedule from post 2 and the conditional model invocation fit comfortably in an Azure Container Apps Job with a `*/1 * * * *` cron schedule. It starts a Python container, runs `get_token_usage_trend`, decides whether to invoke the model, and exits. No always-on server. No VM to babysit. The job's managed identity (`azurerm_user_assigned_identity` plus an `azurerm_role_assignment` for `Monitoring Reader` on the Cognitive Services account) replaces any fixed API key; the full Terraform is in the series companion repo.

## Two scenarios side by side

**Scenario A**: last business day of the month, 11 p.m., TPM at 87%. The agent calls `get_token_usage_history`, sees this same deployment has hit 80-90% every month-end at this hour for six months straight, always returning to normal in under 15 minutes. Decision: `info`. A message in the channel, no mention, no page.

**Scenario B**: a random Tuesday, 2 p.m., TPM at 84% and climbing fast over the last three minutes. The agent checks history, finds no similar pattern for this day of week or time, and the curve shows no sign of leveling off. Decision: `urgent`. Same tool, different priority, and this time someone actually gets paged.

The difference between the two scenarios wasn't in any fixed threshold; it was in comparing the present against history, which is exactly the kind of judgment a simple `if` doesn't handle well and an agent handles reasonably well, as long as the right tools are available.

## The extra guardrails this step requires

Giving decision autonomy, even just over an alert's level, opens a new risk category the pure script didn't have: alert fatigue in reverse. A poorly calibrated agent can either over-alert (everything becomes "urgent" and the team learns to ignore it) or under-alert (a real incident gets classified as "info" because history had a coincidental false match). Three things handle most of this.

First, a rate limit on the alert itself: at most N calls to `send_priority_alert` per hour, regardless of what the agent decides, to keep a once-a-minute reassessment from turning into a flood. Second, logging every decision along with the reasoning the model gave, not just the outcome. That's what lets you, in a retro after an incident, answer "why was this classified as info" without guessing. Third, periodic human review of decisions classified as `info`: not to approve each one in real time (that would defeat the point of automating it), but to audit in batches, weekly, whether the classification pattern still makes sense.

One difference from the risk in post 1 matters here. There, the agent reasoned over outside text like logs, which can be tampered with. Here, the input is numeric telemetry from Azure Monitor. The prompt-injection surface is tiny because there is no arbitrary third-party text entering the context. Not every agent carries the same risk profile, so the checklist should change with the workload.

## What this step buys you

This is the point where the watchdog stops being a threshold alarm and starts being an operator aid. It still cannot fix anything, and that is the right call. In the next post, I wire it to the AKS diagnoser so the alert comes with a candidate cause instead of a shrug.

That closes the gap from the opening scenario. The predictable month-end batch still gets logged, but the runaway agent is the one that wakes somebody up.

## What can go wrong

1. **Under-alerting on novel patterns** — If the model sees a superficial similarity between a current spike and historical data (e.g., "this hour of day had high usage once before"), it may classify a genuine incident as `info`. Audit `info` decisions weekly.
2. **Over-alerting during ramp-up** — When the watchdog starts with limited historical data, nearly every spike looks unprecedented. Seed the history window with at least 30 days of data before enabling `urgent` classification.
3. **Model hallucination in reasoning** — The model might fabricate a pattern match ("this is consistent with your usual Tuesday batch") when no such pattern exists. Log the full reasoning chain, not just the final classification, so you can catch this in review.
4. **Rate limit on the watchdog itself** — If the threshold is crossed for an extended period (e.g., 30 consecutive minutes), the once-a-minute cron fires the model 30 times. Set a cooldown: after the first classification, suppress re-evaluation for at least 10 minutes unless the trend changes direction.
5. **Slack notification fatigue** — Even with priority levels, multiple `warning` messages in quick succession can train the team to ignore the channel. Aggregate: one message per incident window, updated in-place if the classification changes.

## Estimated operational cost

The LLM reasoning call only fires when the threshold is crossed, which should be rare. Each call uses roughly 1K-2K tokens (system prompt + history data + response). At typical Azure OpenAI pricing, expect $0.01-0.05 per invocation. The dominant cost is the Azure Container Apps Job running the once-a-minute cron, roughly $2-5/month at consumption pricing. Total: under $10/month for most deployments.

## Series navigation

1. [MCP and agents 101 for infra engineers](/2026/07/01/mcp-and-agents-101-for-infra-engineers/)
2. [Building a deterministic 429 watchdog](/2026/07/08/deterministic-429-watchdog-azure-openai/)
3. **From script to agent: giving the watchdog decision autonomy** ← you are here
4. [Multi-agent orchestration: correlating AKS and Azure OpenAI](/2026/07/21/multi-agent-orchestration-aks-openai-correlation/)
5. [Agent governance on Microsoft Foundry](/2026/07/28/agent-governance-microsoft-foundry/)

## Further reading

- [Monitoring data reference for Azure OpenAI in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/monitor-openai-reference)
- [Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Overview of Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
- [What is Azure role-based access control (Azure RBAC)?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/watchdog-agente-autonomia-decisao-guardrails/).*
