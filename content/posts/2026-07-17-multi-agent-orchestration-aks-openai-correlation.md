---
slug: "multi-agent-orchestration-aks-openai-correlation"
translationKey: "orquestracao-multi-agentes-aks-openai-correlacao"
title: "Multi-Agent Orchestration: Correlating AKS and Azure OpenAI"
description: "An orchestrator that combines the AKS diagnostics agent with the token watchdog to answer 'did someone deploy something?' automatically."
date: 2026-07-17T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - multi-agent
  - aks
  - azure-openai
  - mcp
  - orchestration
  - correlation
series:
  - "MCP Agents and Infrastructure"
---
# Chapter 4 — Multi-Agent Orchestration

So far the series has built two separate things: in post 1, an agent that talks to AKS via `aks-mcp` to diagnose the cluster; in posts 2 and 3, a watchdog that watches TPM consumption on Azure OpenAI and decides how urgent an alert should be. Both work in isolation, and isolated they already deliver value. But separated, they also leave the most obvious question unanswered: when token consumption spikes out of nowhere, the first thing any SRE asks is "did someone deploy something?" — and today that question is still manual, someone looking at the watchdog's alert in one tab and the AKS dashboard in another.

This post is about closing that last manual step with an orchestrator.

## The trigger moves

In post 3, when the watchdog classified an event as `urgent`, the `send_priority_alert` tool went straight to Slack. Now that output changes destination: instead of notifying a human directly, an `urgent` classification triggers the orchestrator, which only then decides what (and when) the human sees.

```
 watchdog (post 3)
       │ classification = urgent
       ▼
 ┌─────────────────────────────┐
 │         ORCHESTRATOR          │
 └──────┬────────────────┬──────┘
        │                │
        ▼                ▼
 watchdog sub-agent    AKS sub-agent
 (token telemetry,     (aks-mcp: detectors,
  posts 2/3)             monitor, kubectl)
        │                │
        └───────┬────────┘
                ▼
       send_priority_alert
       (consolidated message,
        with cause hypothesis)
```

Each sub-agent keeps exactly the scope it already had — the watchdog didn't gain access to the cluster, the AKS agent didn't gain access to quota. The orchestrator is the only new piece, and it only has read access to both, plus the same notification tool as always. No new capability to act was created by combining them — only the capability to correlate what each one already knew on its own.

## Correlation in practice

When the orchestrator is triggered, it takes the timestamp of the start of the TPM spike (which the watchdog already computes) and uses it as an anchor to ask the AKS sub-agent: "what happened in the cluster during that window?" The sub-agent, with the `kubectl` and `monitor` components of `aks-mcp` already configured as `readonly` since post 1, queries recent events and rollout history.

```python
@mcp.tool()
def correlate_incident(token_spike_start: str, window_minutes: int = 15) -> dict:
    """Takes the start time of a token consumption spike and looks up
    cluster events (deploys, scaling, restarts) within the same time
    window. Returns candidate causes with their respective confidence
    level, never a single cause stated as certain."""
    cluster_events = aks_agent.get_recent_events(token_spike_start, window_minutes)
    return rank_candidates(cluster_events)
```

The result, instead of two disconnected alerts arriving in different channels, becomes a single message: "TPM at 91% and rising. Candidate cause: deploy of the `recommendation-api` service at 2:01 p.m., which scaled from 3 to 12 replicas via HPA — each new replica makes a warmup call to GPT-4o on startup, which lines up with the start of the spike." That's no longer "two metrics crossed a threshold." It's a verifiable hypothesis, with evidence attached.

## The new risk correlation introduces

It's worth being honest about what this post adds in terms of risk, because it isn't zero: a model correlating events by time proximity can produce a plausible and wrong narrative. Two events close in time aren't necessarily cause and effect — it could be coincidence, it could be a third factor that affected both. It's the classic "correlation isn't causation," except now stated by an agent with the confident tone of someone who knows what they're talking about.

The mitigation isn't trying to make the model "more certain" — it's never letting its output become a categorical claim. The `correlate_incident` tool was deliberately designed to return candidates with a confidence level, not a single cause, and the final Slack message has to preserve that: "candidate cause," not "the cause was." The person receiving the alert still decides whether the hypothesis makes sense — the agent saved the work of pulling the data together, not the final judgment on it.

## What stays the same (and why it matters)

It's worth repeating what didn't change, because it's easy, when introducing an orchestrator, to loosen guardrails out of convenience: none of the three agents — watchdog, AKS sub-agent, orchestrator — gained any tool to act on production. The orchestrator can't roll back the deploy it itself flagged as the candidate cause, can't bump quota, can't restart anything. It reads two already-existing read systems and writes to a single, already-existing notification tool. The composition didn't create a new attack surface — it just saved a human from manually juggling two tabs.

On orchestration itself: for this case, there's no need at all for an agent-to-agent protocol like A2A, which I mentioned in passing in post 1. The two sub-agents belong to the same team, the same system, and the orchestrator simply calls each one the way it would call a function — there's no negotiation between independent parties happening here. A2A makes sense when agents belong to different administrative domains; within your own SRE team, an orchestrator calling sub-agents already gets the job done, no extra complexity needed.

## Cost and latency: the trade-offs nobody asks about until the bill shows up

Worth remembering the layered design from the earlier posts: the once-a-minute cron stays cheap and LLM-free. The reasoning watchdog only runs when the threshold is crossed. And now the orchestrator only runs once the watchdog has already classified something as `urgent` — meaning the most expensive call in the whole chain (two sub-agent queries plus a correlation) only happens on the rarest event of all. Each layer filters before passing the next, pricier one along. It's the same principle behind any well-designed alerting pipeline — except here each layer, besides filtering, also reasons a bit more than the one before it.

Latency adds a few extra seconds before the final alert goes out, compared to an instant generic Slack ping. For a real incident, trading a few seconds for a ready-made cause hypothesis is a favorable trade — but it is a trade, and it's worth measuring, not assuming.

## Up next in the series

1. ✅ MCP and agents — the 101
2. ✅ The deterministic 429 watchdog
3. ✅ Giving it decision autonomy with guardrails
4. ✅ This post — an orchestrator correlating AKS and token consumption
5. Baseline governance for Azure AI Foundry agents

With four different agents running (watchdog, AKS sub-agent, orchestrator, and the post-1 agent that can still be called on its own), the question left over isn't technical anymore — it's governance: who knows these agents exist, who decides which tools each one gets, and how do you audit this six months from now when nobody remembers why the orchestrator was configured that way. That's exactly the subject of the next post.

---

*This is post 4 of the series "MCP, Agents, and Agent Teams for Infrastructure Engineers":*

1. [MCP and Agents 101](/2026/07/08/mcp-and-agents-101-for-infra-engineers/)
2. [The Deterministic 429 Watchdog](/2026/07/10/deterministic-429-watchdog-azure-openai/)
3. [From Script to Agent](/2026/07/14/agentic-watchdog-decision-autonomy-guardrails/)
4. **Multi-Agent Orchestration**
5. [Governance on Microsoft Foundry](/2026/07/21/agent-governance-microsoft-foundry/)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/orquestracao-multi-agentes-aks-openai-correlacao/).*
