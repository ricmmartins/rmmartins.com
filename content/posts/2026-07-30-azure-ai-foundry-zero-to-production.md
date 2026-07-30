---
slug: "azure-ai-foundry-zero-to-production"
aliases:
  - "/2026/07/30/azure-ai-foundry-zero-to-production/"
translationKey: "azure-ai-foundry-do-zero-a-producao"
title: "Azure AI Foundry: From Zero to Production — A Practical Guide"
description: "What I cover when a customer asks 'we want to build AI applications on Azure, where do we start?' — distilled from a recent workshop into a production-ready playbook covering model selection, PTU vs PAYGO, spillover architecture, and cost optimization."
date: 2026-07-30T18:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - azure-ai-foundry
  - openai
  - ptu
  - cost-optimization
  - ai-architecture
  - production-readiness
---

*What I cover when a customer asks "we want to build AI applications on Azure, where do we start?" — distilled from a recent workshop into a production-ready playbook.*

## The starting point

A few weeks ago, I had a conversation with a customer's engineering team that was ready to build their first AI-powered application on Azure. They had experimented with ChatGPT, prototyped with the OpenAI API directly, and now needed to understand: *how do we go from playground to production at enterprise scale?*

That conversation became a workshop, the workshop became a structured deck, and now I'm turning it into this guide — because the questions they asked are the same ones I hear from every team making this transition.

## What is Azure AI Foundry?

[Azure AI Foundry](https://ai.azure.com) is the unified platform for building, deploying, and operating AI applications on Azure. Think of it as the control plane for everything AI in your Azure environment:

- **Model Catalog** — Access to 1,900+ models (OpenAI, Meta Llama, Mistral, Cohere, Phi, and more)
- **Prompt Engineering** — Playground, prompt flow, evaluation tools
- **Deployment Options** — Serverless (pay-per-token), Provisioned Throughput (PTU), Global/Data Zone routing
- **Safety & Governance** — Content filters, red teaming tools, model monitoring
- **Agent Framework** — Build multi-step AI agents with tool-calling, code interpreter, file search

The key insight: Foundry isn't just "another Azure service." It's the orchestration layer that connects models, data, compute, and governance into a coherent development experience.

## The architecture decision tree

Every team building on Foundry faces the same sequential decisions:

### 1. Model Selection

The model landscape in mid-2026:

| Model | Best for | Trade-off |
|-------|----------|-----------|
| **GPT-5.x** | Orchestration, complex reasoning, multi-step agents | Highest capability, highest cost |
| **GPT-5-mini** | Fast tasks, classification, summarization | 90% of GPT-5 quality at 20% of cost |
| **GPT-4.1** | Legacy workloads (deprecating) | Stable but being superseded |
| **Phi-4** | Edge deployment, fine-tuning, embedding | Small, fast, cheap, customizable |
| **Llama 3.x** | Open-weight flexibility, on-prem requirements | Full control, self-managed |

**My recommendation for agentic workloads:** GPT-5.x for the orchestrator (best tool-calling accuracy), GPT-5-mini for sub-tasks (classification, extraction, formatting), and Phi-4 or fine-tuned models for domain-specific components.

### 2. Deployment Type: PAYGO vs PTU

This is where most teams get confused. Here's the simple framework:

**Start with PAYGO (Pay-As-You-Go)** when:
- You're in development/testing
- Traffic is unpredictable or bursty
- You're still figuring out which models you'll use long-term

**Move to PTU (Provisioned Throughput Units)** when:
- Sustained utilization exceeds 60-70% of equivalent PTU capacity
- You need guaranteed latency (no noisy-neighbor throttling)
- You're running production workloads with predictable patterns

### 3. How PTU works

PTU is a token-bucket model. Each PTU reserves a fixed throughput in tokens per minute. The rate varies by model:

- **GPT-5-mini**: ~3,500 TPM per PTU
- **GPT-5**: varies by variant
- **GPT-4.1**: 3,000 TPM per PTU (deprecating)

Example: 100 PTUs of GPT-5-mini = ~350,000 tokens/minute guaranteed. If load exceeds that, the API returns 429 — no queue, no wait. It's a hard cutoff.

### 4. The cost math

| Tier | Price (reference Jul/2026) | Commitment |
|------|---------------------------|------------|
| On-Demand | ~$2/hour/PTU = $14,400/month | None |
| Monthly Reserved | ~$0.72/hour/PTU = $5,184/month | 1 month |
| Yearly Reserved | ~$0.60/hour/PTU = $4,320/month | 1 year |

The break-even: if sustained utilization is above 60-70% of your PTU capacity, monthly reservation already beats PAYGO.

> ⚠️ These are reference prices as of July 2026. EA/MCA negotiated rates may differ. Always validate against your specific agreement.

**Tool**: Use [ptucalc.com](https://ptucalc.com) to model your specific scenario. It's open source, with 12,000+ sessions to date — input your usage patterns and it calculates the optimal tier and PTU count.

### 5. Spillover Architecture (best of both worlds)

The pattern I recommend for production:

```
[Traffic] → [PTU (handles baseline load, guaranteed latency)]
               ↓ (overflow when PTU is saturated)
            [PAYGO (absorbs spikes, no capacity ceiling)]
```

Configure your deployment with PTU as primary and PAYGO as spillover. You get:
- Guaranteed latency for your baseline traffic (PTU)
- No dropped requests during spikes (PAYGO absorbs overflow)
- Cost optimization (PTU for steady-state, PAYGO only for peaks)

This is configured at the deployment level in Foundry — no application code changes needed.

## Production readiness checklist

Before going to production, validate these:

### Security & Network
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

### Cost Governance
- [ ] Budget alerts configured
- [ ] Chargeback tags for multi-team environments
- [ ] PTU utilization monitoring (target: 70-85%)
- [ ] Regular review cadence (monthly) for tier optimization

## The progression: from POC to production

Most teams follow this path:

```
Week 1-2:  Playground → Prove the concept works
Week 3-4:  PAYGO Standard → Build the application logic
Month 2:   PAYGO + monitoring → Understand real usage patterns
Month 3:   PTU Monthly Reserved → Lock in cost savings
Month 6+:  PTU Yearly → Maximum discount with confidence
```

Don't skip steps. Each phase teaches you something about your workload that informs the next decision.

## What's next

If you're building AI applications on Azure and navigating these decisions, here are your next steps:

1. **Start in the [Foundry Playground](https://ai.azure.com)** — test models against your actual use cases
2. **Model your costs** with [ptucalc.com](https://ptucalc.com) before committing to PTU
3. **Deploy with spillover** from day one — it costs nothing extra when PTU handles everything, but saves you from dropped requests when spikes happen
4. **Set up monitoring early** — you can't optimize what you can't measure

---

**Resources:**
- 🔗 [Azure AI Foundry](https://ai.azure.com)
- 📊 [PTU Calculator](https://ptucalc.com)
- 📖 [Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-studio/)
- 🏗️ [Well-Architected Framework for AI](https://learn.microsoft.com/en-us/azure/well-architected/ai/)

---

*Building with Foundry and have questions about deployment strategy or cost optimization? Drop a comment — happy to dig deeper into any of these topics.*
