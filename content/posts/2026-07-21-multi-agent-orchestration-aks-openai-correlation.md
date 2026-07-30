---
slug: "multi-agent-orchestration-aks-openai-correlation"
aliases:
  - "/2026/07/21/multi-agent-orchestration-aks-openai-correlation/"
translationKey: "orquestracao-multi-agentes-aks-openai-correlacao"
title: "Multi-Agent Orchestration: Correlating AKS and Azure OpenAI"
description: "An orchestrator that combines the AKS diagnostics agent with the token watchdog to answer 'did someone deploy something?' automatically."
date: 2026-07-21T10:00:00-04:00
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
# Chapter 4: Multi-Agent Orchestration

So far the series has built two separate things: in post 1, an agent that talks to AKS via `aks-mcp` to diagnose the cluster; in posts 2 and 3, a watchdog that watches TPM consumption on Azure OpenAI and decides how urgent an alert should be. Both are useful on their own. Together, they still leave the first SRE question hanging in the air: when token consumption jumps out of nowhere, did somebody deploy something? In most teams that answer still lives in two browser tabs and one annoyed human.

This post is about closing that last manual step with an orchestrator.

**tl;dr**
- Escalate to the orchestrator only after the watchdog classifies a spike as `urgent`.
- Keep scopes tight: the watchdog reads quota, the AKS agent reads cluster state, and only the orchestrator sends the final alert.
- Correlate events inside a time window and return candidate causes with confidence, not certainty.
- Spend a few extra seconds on correlation so the page includes a usable hypothesis.

## The trigger moves

In post 3, when the watchdog classified an event as `urgent`, the `send_priority_alert` tool went straight to Slack. Now that output changes destination: instead of notifying a human directly, an `urgent` classification triggers the orchestrator, which only then decides what (and when) the human sees.

- The watchdog from post 3 classifies the event as `urgent`.
- The orchestrator fans out to two scoped sub-agents:
  - the watchdog sub-agent for token telemetry from posts 2 and 3
  - the AKS sub-agent for `aks-mcp` detectors plus `monitor` and `kubectl`
- The orchestrator sends one consolidated alert with the cause hypothesis.

Each sub-agent keeps the same scope it already had. The watchdog did not gain access to the cluster. The AKS agent did not gain access to quota. The orchestrator is the only new piece, and it still only gets read access plus the same notification tool as before. Combining them created correlation, not new authority.

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
    return rank_candidates(cluster_events)  # domain-specific ranking
```

> **Note:** `rank_candidates()` is pseudocode. The actual ranking logic depends on your incident taxonomy — you might score by event proximity, blast radius, or historical frequency. The point is the interface: candidates with confidence levels, never a single answer.

The result, instead of two disconnected alerts arriving in different channels, becomes a single message: "TPM at 91% and rising. Candidate cause: deploy of the `recommendation-api` service at 2:01 p.m., which scaled from 3 to 12 replicas via HPA; each new replica makes a warmup call to GPT-4o on startup, which lines up with the start of the spike." That's no longer "two metrics crossed a threshold." It's a verifiable hypothesis, with evidence attached.

## The new risk correlation introduces

This post does add a new risk dimension, because it isn't zero: a model correlating events by time proximity can produce a plausible and wrong narrative. Two events close in time aren't necessarily cause and effect; it could be coincidence, it could be a third factor that affected both. It's the classic "correlation isn't causation," except now stated by an agent with the confident tone of someone who knows what they're talking about.

The mitigation is not to make the model sound more certain. It is to stop it from speaking in absolutes. The `correlate_incident` tool returns candidates with confidence levels, not a single blessed answer, and the final Slack message needs to keep that language intact: "candidate cause," not "case closed." The person receiving the alert still decides whether the hypothesis is any good. The agent saved the data gathering, not the judgment.

## What stays the same (and why it matters)

A quick inventory of what did not change, because this is where teams get sloppy: none of the three agents gained a tool that acts on production. The orchestrator cannot roll back the deploy it just blamed, bump quota, or restart anything. It reads from two existing read systems and writes to one existing notification tool. The composition did not create a new attack surface. It just saved a human from juggling tabs.

On orchestration itself: for this case, there's no need at all for an agent-to-agent protocol like A2A, which I mentioned in passing in post 1. The two sub-agents belong to the same team, the same system, and the orchestrator simply calls each one the way it would call a function. There's no negotiation between independent parties happening here. A2A makes sense when agents belong to different administrative domains; within your own SRE team, an orchestrator calling sub-agents already gets the job done, no extra complexity needed.

## Cost and latency: the trade-offs nobody asks about until the bill shows up

The layered design from the earlier posts matters here: the once-a-minute cron stays cheap and LLM-free. The reasoning watchdog only runs when the threshold is crossed. And now the orchestrator only runs once the watchdog has already classified something as `urgent`, meaning the most expensive call in the whole chain (two sub-agent queries plus a correlation) only happens on the rarest event of all. Each layer filters before passing the next, pricier one along. It's the same principle behind any well-designed alerting pipeline, except here each layer, besides filtering, also reasons a bit more than the one before it.

Latency adds 2–5 seconds before the final alert goes out (depending on AKS query performance and metric ingestion lag), compared to an instant generic Slack ping. For a real incident, trading a few seconds for a ready-made cause hypothesis is a favorable trade, but it is a trade, and it's worth measuring, not assuming.

## The trade worth making

A few seconds of extra latency is a fine price to pay when the alert arrives with a plausible cause attached. Once you have several agents doing real work, the hard part stops being orchestration code and starts being governance. That is where the last post goes.

So yes, you can answer "did someone deploy something?" with one alert instead of two browser tabs. You just keep the answer framed as a candidate cause until a human confirms it.

## What can go wrong

1. **Sub-agent timeout.** If the AKS agent takes too long to query events (network latency, large event history), the orchestrator hangs. Set a 30-second timeout per sub-agent and return partial results with a "data incomplete" flag.
2. **False correlation.** Two events coinciding in the same 15-minute window doesn't prove causation. A deploy at 2:01 p.m. and a spike at 2:03 p.m. could be coincidence. Always present candidates, never certainty — and log the reasoning so you can audit false positives later.
3. **Stale metrics.** Azure Monitor metrics have ~1 minute ingestion lag. A spike that already resolved may still trigger correlation. The orchestrator should check current values, not just the trigger snapshot.
4. **Window too narrow or too wide.** A 15-minute window catches most deploys, but a canary rollout over 2 hours will be missed. If your deployment strategy is slow, parameterize the window.
5. **Orchestrator as single point of failure.** If the orchestrator crashes mid-correlation, neither the watchdog alert nor the AKS data reaches anyone. Keep the watchdog's direct-to-Slack path as a fallback for when the orchestrator is unavailable.

## Further reading

- [Monitor Azure Kubernetes Service (AKS)](https://learn.microsoft.com/en-us/azure/aks/monitor-aks)
- [Scaling options for applications in Azure Kubernetes Service (AKS)](https://learn.microsoft.com/en-us/azure/aks/concepts-scale)
- [Monitoring data reference for Azure OpenAI in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/monitor-openai-reference)
- [Overview of Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/orquestracao-multi-agentes-aks-openai-correlacao/).*
