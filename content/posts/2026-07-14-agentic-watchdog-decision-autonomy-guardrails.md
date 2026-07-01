---
slug: "agentic-watchdog-decision-autonomy-guardrails"
translationKey: "watchdog-agente-autonomia-decisao-guardrails"
title: "From Script to Agent: Giving the Watchdog Decision Autonomy"
description: "Adding a reasoning layer to the 429 watchdog so it can tell a benign batch spike from a runaway agent — with explicit guardrails."
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
# Chapter 3 — From Script to Agent

In the previous post, the Azure OpenAI quota watchdog was a script with `if pct_of_tpm > 0.8: alert`. It works, but it has a problem anyone who's ever configured a monitoring alert knows by heart: a fixed threshold can't tell context apart. A batch job that always eats 90% of TPM for 10 minutes at month-end and returns to normal is, to the script, the same event as some agent loose in your environment looping and burning tokens nonstop. Both cross the same threshold; only one deserves to wake someone up.

This post is about closing that gap — giving the watchdog a reasoning layer, without giving up any of the guardrails we've already set.

## What changes (and what doesn't)

What does **not** change: the server still only reads telemetry and only writes to notification channels. No new tool to act on the resource. That boundary was right in post 2 and is still right now — giving autonomy over *how to alert* is one thing; giving autonomy to *act on the production resource* is something else entirely, and I wouldn't recommend the latter without a lot more operational maturity than two blog posts can guarantee.

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

@mcp.tool()
def send_priority_alert(channel: str, message: str, priority: Literal["info", "warning", "urgent"]) -> str:
    """Sends an alert with a priority level: 'info' (normal channel, no
    mention), 'warning' (normal channel, with context), or 'urgent'
    (mentions the on-call group). The priority choice belongs to whoever
    calls this tool, not to this function."""
    prefix = {"info": "ℹ️", "warning": "⚠️", "urgent": "🚨 @oncall-ai"}[priority]
    httpx.post(SLACK_WEBHOOK_URL, json={"channel": channel, "text": f"{prefix} {message}"}, timeout=10)
    return "sent"
```

(`mcp` here is the same `FastMCP` instance created in post 2 — these two tools join the same `watchdog429` server, not a separate one.)

The first one gives the agent a baseline for comparison: "has this happened before at this same time?" The second separates the act of notifying from the urgency level — the reasoning layer decides the level, not the tool.

## Where the model comes in (and where it doesn't)

Here's the most important operational point in this post: **the model does not run every minute**. The deterministic script from post 2 stays the poller — it runs on the cron, once a minute, at zero LLM cost, and only triggers a model call once the threshold is crossed. Putting an LLM in the loop on every iteration of a monitoring cycle is wasting money on a path that, the overwhelming majority of the time, needs no reasoning at all — it's only worth paying the cost of a model call to decide the response level in the minutes the threshold actually gets crossed.

```
 cron (1x/min, zero LLM cost)
       │
       ▼
 get_token_usage_trend > 0.8 ?  ──no──▶  loop continues
       │ yes
       ▼
 invoke the agent (1 model call)
       │
       ▼
 get_token_usage_history + reasoning
       │
       ▼
 send_priority_alert(priority = info | warning | urgent)
```

The agent's system prompt stays small and direct — it doesn't need much more than this:

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

Notice the last line: it exists to reinforce, in the prompt itself, the limit that's already baked into the architecture. Intentional redundancy — the real guardrail is the absence of the tool, the prompt is just the second layer.

**Where this actually runs**: the cron from post 2 and the conditional step of invoking the model fit comfortably in an Azure Container Apps Job with a once-a-minute schedule trigger — it spins up a Python container, runs `get_token_usage_trend`, decides whether to invoke the model, and exits. No server staying up the whole time, no VM to maintain. The job's managed identity (`azurerm_user_assigned_identity` + an `azurerm_role_assignment` for the `Monitoring Reader` role on the Cognitive Services account) is what replaces any fixed API key — the full Terraform is in the series companion repo.

## Two scenarios side by side

**Scenario A** — last business day of the month, 11 p.m., TPM at 87%. The agent calls `get_token_usage_history`, sees this same deployment has hit 80-90% every month-end at this hour for six months straight, always returning to normal in under 15 minutes. Decision: `info`. A message in the channel, no mention, no page.

**Scenario B** — a random Tuesday, 2 p.m., TPM at 84% and climbing fast over the last three minutes. The agent checks history, finds no similar pattern for this day of week or time, and the curve shows no sign of leveling off. Decision: `urgent`. Same tool, different priority, and this time someone actually gets paged.

The difference between the two scenarios wasn't in any fixed threshold — it was in comparing the present against history, which is exactly the kind of judgment a simple `if` doesn't handle well and an agent handles reasonably well, as long as the right tools are available.

## The extra guardrails this step requires

Giving decision autonomy, even just over an alert's level, opens a new risk category the pure script didn't have: alert fatigue in reverse. A poorly calibrated agent can either over-alert (everything becomes "urgent" and the team learns to ignore it) or under-alert (a real incident gets classified as "info" because history had a coincidental false match). Three things handle most of this.

First, a rate limit on the alert itself — at most N calls to `send_priority_alert` per hour, regardless of what the agent decides, to keep a once-a-minute reassessment from turning into a flood. Second, logging every decision along with the reasoning the model gave, not just the outcome — that's what lets you, in a retro after an incident, answer "why was this classified as info" without guessing. Third, periodic human review of decisions classified as `info`: not to approve each one in real time (that would defeat the point of automating it), but to audit in batches, weekly, whether the classification pattern still makes sense.

Worth noting a difference from the risk in post 1: there, the data feeding the agent's reasoning came from outside (logs, which can be tampered with). Here, the input is numeric metrics from Azure Monitor itself — the prompt injection surface is practically nonexistent, because there's no arbitrary third-party text entering the context. Not every agent carries the same risk profile, and it's worth mapping that case by case instead of applying the same checklist to everything.

## Up next in the series

1. ✅ MCP and agents — the 101
2. ✅ The deterministic 429 watchdog
3. ✅ This post — giving it decision autonomy with guardrails
4. Multi-agent teams in practice: an orchestrator combining the AKS diagnostics from post 1 with this watchdog, to automatically correlate "token consumption spiked" with "recent deployment to the cluster"
5. Baseline governance for Azure AI Foundry agents

The natural next step is to stop treating these two agents as isolated projects and see what happens when an orchestrator has access to both at once — which is exactly where "agent team" stops being a slide concept and becomes a real debugging tool.

---

*This is post 3 of the series "MCP, Agents, and Agent Teams for Infrastructure Engineers":*

1. [MCP and Agents 101](/2026/07/08/mcp-and-agents-101-for-infra-engineers/)
2. [The Deterministic 429 Watchdog](/2026/07/10/deterministic-429-watchdog-azure-openai/)
3. **From Script to Agent**
4. [Multi-Agent Orchestration](/2026/07/17/multi-agent-orchestration-aks-openai-correlation/)
5. [Governance on Microsoft Foundry](/2026/07/21/agent-governance-microsoft-foundry/)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/watchdog-agente-autonomia-decisao-guardrails/).*
