---
title: "Azure AI Foundry: from zero to production"
slug: azure-ai-foundry-zero-to-production
aliases: [/azure-ai-foundry-zero-to-production/]
translationKey: azure-ai-foundry
description: "What I cover when a customer asks where to start with AI on Azure. Model selection, PAYGO vs PTU, spillover architecture, and production checklist."
date: 2026-07-30
categories: [Azure, AI]
tags: [azure-ai-foundry, ptu, openai, ai-agents, cost-optimization]
---
# Azure AI Foundry: from zero to production

*What I cover when a customer asks "we want to build AI applications on Azure, where do we start?"*

> **TL;DR:** Azure AI Foundry is the unified platform for building AI apps on Azure. Start with PAYGO, move to PTU when utilization exceeds 60-70%, and always configure spillover (PTU primary + PAYGO overflow). Use [ptucalc.com](https://ptucalc.com) to model your costs before committing.

---

## The starting point

A few weeks ago, I had a conversation with a customer's engineering team that was ready to build their first AI-powered application on Azure. They had experimented with ChatGPT, prototyped with the OpenAI API directly, and now needed to understand: *how do we go from playground to production at enterprise scale?*

That conversation became a workshop, then a deck, and now this guide. The questions they asked are the same ones I hear from every team making this jump.

## What is Azure AI Foundry?

[Azure AI Foundry](https://ai.azure.com) is the unified platform for building, deploying, and operating AI applications on Azure. Think of it as the control plane for everything AI in your Azure environment:

- Model Catalog: 1,900+ models (OpenAI, Meta Llama, Mistral, Cohere, Phi, others)
- Prompt Engineering: playground, prompt flow, evaluation tools
- Deployment Options: serverless pay-per-token, Provisioned Throughput (PTU), Global/Data Zone routing
- Safety and Governance: content filters, red teaming tools, model monitoring
- Agent Framework: multi-step AI agents with tool-calling, code interpreter, file search

Foundry is not just another Azure service. It is the layer that ties models, data, compute, and governance together into one development surface.

## The decisions you will face

Every team building on Foundry hits the same questions in roughly the same order.

### 1. Model selection

The model landscape in mid-2026:

| Model | Best for | Trade-off |
|-------|----------|-----------|
| **GPT-5.x** | Orchestration, complex reasoning, multi-step agents | Highest capability, highest cost |
| **GPT-5-mini** | Fast tasks, classification, summarization | 90% of GPT-5 quality at 20% of cost |
| **GPT-4.1** | Legacy workloads (deprecating) | Stable but being superseded |
| **Phi-4** | Edge deployment, fine-tuning, embedding | Small, fast, cheap, customizable |
| **Llama 3.x** | Open-weight flexibility, on-prem requirements | Full control, self-managed |

**My recommendation for agentic workloads:** GPT-5.x for the orchestrator (best tool-calling accuracy), GPT-5-mini for sub-tasks (classification, extraction, formatting), and Phi-4 or fine-tuned models for domain-specific components.

### 2. Deployment type: PAYGO vs PTU

Most teams overthink this. The rule is simple:

![PAYGO vs PTU decision tree](/img/foundry-paygo-vs-ptu.svg)

**Start with PAYGO (Pay-As-You-Go)** when:
- You're in development/testing
- Traffic is unpredictable or bursty
- You're still figuring out which models you'll use long-term

**Move to PTU (Provisioned Throughput Units)** when:
- Sustained utilization exceeds 60-70% of equivalent PTU capacity
- You need guaranteed latency (no noisy-neighbor throttling)
- You're running production workloads with predictable patterns

### 3. How PTU actually works

PTU is a token-bucket model. Each PTU reserves a fixed throughput in tokens per minute. The rate varies by model:

- **GPT-5-mini**: ~3,500 TPM per PTU
- **GPT-5**: varies by variant
- **GPT-4.1**: 3,000 TPM per PTU (deprecating)

So 100 PTUs of GPT-5-mini give you roughly 350,000 tokens/minute guaranteed. Go past that and the API returns 429. No queue, no wait. Hard cutoff.

### 4. The cost math (this is where it gets interesting)

| Tier | Price (reference Jul/2026) | Commitment |
|------|---------------------------|------------|
| On-Demand | ~$2/hour/PTU = $14,400/month | None |
| Monthly Reserved | ~$0.72/hour/PTU = $5,184/month | 1 month |
| Yearly Reserved | ~$0.60/hour/PTU = $4,320/month | 1 year |

The break-even: if sustained utilization is above 60-70% of your PTU capacity, monthly reservation already beats PAYGO.

> ⚠️ These are reference prices as of July 2026. EA/MCA negotiated rates may differ. Always validate against your specific agreement.

I built [ptucalc.com](https://ptucalc.com) to help with exactly this calculation. It is open source, 12,000+ sessions so far. Plug in your usage patterns and it tells you the optimal tier and PTU count.

### 5. Spillover architecture

The pattern I recommend for production:

![Spillover Architecture](/img/foundry-spillover-architecture.svg)

Configure your deployment with PTU as primary and PAYGO as spillover. You get:
- Guaranteed latency for your baseline traffic (PTU)
- No dropped requests during spikes (PAYGO absorbs overflow)
- Cost optimization (PTU for steady-state, PAYGO only for peaks)

You configure this at the deployment level in Foundry. No application code changes.

## Production checklist

Things I check before any customer goes live:

### Security and network
- [ ] Private endpoints configured (no public internet exposure)
- [ ] Managed Identity for authentication (no API keys in code)
- [ ] Content Safety filters tuned (not just defaults)
- [ ] VNet integration if required by compliance
- [ ] Data residency: model deployment region matches data requirements

### Reliability
- [ ] Multi-region deployment (primary + failover)
- [ ] Retry logic with exponential backoff
- [ ] Circuit breaker pattern for downstream dependencies
- [ ] Health probes and availability monitoring
- [ ] Spillover configured (PTU → PAYGO)

### Observability
- [ ] Token consumption metrics in Azure Monitor
- [ ] Latency P50/P95/P99 dashboards
- [ ] Cost allocation tags on all Foundry resources
- [ ] Alerting on 429 rates (throttling indicator)
- [ ] Model performance evaluation pipeline (drift detection)

### Cost governance
- [ ] Budget alerts configured
- [ ] Chargeback tags for multi-team environments
- [ ] PTU utilization monitoring (target: 70-85%)
- [ ] Regular review cadence (monthly) for tier optimization

## The typical progression

Most teams I work with follow this path:

![POC to Production](/img/foundry-progression.svg)

Don't skip steps. Each phase teaches you something about your workload that informs the next decision.

## Where to start

1. Open the [Foundry Playground](https://ai.azure.com) and test models against your actual use cases
2. Model your costs with [ptucalc.com](https://ptucalc.com) before committing to PTU
3. Deploy with spillover from day one. It costs nothing extra when PTU handles the load, but saves you when spikes hit
4. Set up monitoring early. You cannot optimize what you cannot measure

---

**Resources:**
- [Azure AI Foundry](https://ai.azure.com)
- [PTU Calculator](https://ptucalc.com)
- [Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-studio/)
- [Well-Architected Framework for AI](https://learn.microsoft.com/en-us/azure/well-architected/ai/)

---

*Questions about deployment strategy or cost modeling? Leave a comment.*

