---
slug: "cost-engineering-for-ai-when-idle-gpus-cost-more-than-your-car"
translationKey: "cost-engineering-para-ai-quando-gpu-idle-custa-mais-que-seu-carro"
title: "Cost engineering for AI: when idle GPUs cost more than your car"
description: "A GPU idle over the weekend costs $4,700. Spot VMs, PTU vs pay-per-token, right-sizing, tagging, and FinOps to keep the CFO happy without killing innovation."
date: 2026-06-11T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - finops
  - costs
  - spot-vms
  - reserved-instances
  - azure-openai
series:
  - "AI for Infrastructure Engineers"
---

Ninth post in the series. In the [previous one](/2026/06/07/security-for-ai-threats-your-firewall-wont-catch/), we hardened the platform against prompt injection and data leakage. Now for the part Finance notices first: how not to go bankrupt in the process.

## The $127,000 Monday

Monday morning. Coffee in hand, email from Finance with the subject line: "URGENT: Azure invoice $127,000, please explain." Forecast was $42,000. Two ND96isr_H100_v5 VMs, provisioned three weeks ago for a "quick experiment," never shut down. At about $98/hour each, running 24/7 for three weeks: roughly $99,000 in idle GPU compute. Nobody was using them. Nobody remembered they existed.

This isn't hypothetical. Some version of this happens all the time. The ML engineer who provisioned them wasn't negligent. They were iterating fast, which is what you want. The failure was systemic: no auto-shutdown policy, no budget alerts, and no tags linking the VMs to a project or owner.

## Why cost engineering for AI is different

| Factor | Traditional infra | AI workloads |
|--------|-------------------|--------------|
| **Cost per VM** | ~$0.19/hour (D4s_v5) | ~$98/hour (ND96isr_H100_v5) |
| **VM idle over a weekend** | ~$9 | ~$4,700 |
| **Usage pattern** | Steady-state | Bursty (0 → 64 GPUs → 0) |
| **Pricing model** | Per hour/second | Per hour + per token |
| **Margin of error** | Hundreds of dollars | Tens of thousands |

**Infra ↔ AI translation:** An idle GPU is like leaving all the lights in a stadium on after the game. The power bill is enormous, nobody benefits, and the fix is a simple timer. But someone needs to install the timer before the first game.

## Cost formulas

### Training (GPU VMs)

```
Training Cost = (VM count × Hours × Price/VM-hour) + Storage + Networking
```

**Example: fine-tuning a 7B model with QLoRA**

| Component | Calculation | Cost |
|-----------|-------------|------|
| Compute | 1× `NC24ads_A100_v4` × 18h × $9.90/h | ~$178 |
| Storage | 500 GB Premium SSD × 18h | ~$3 |
| Networking | Negligible (single VM) | ~$0 |
| **Total** | | **~$181** |

**Example: pre-training a 70B model**

| Component | Calculation | Cost |
|-----------|-------------|------|
| Compute | 8× `ND96isr_H100_v5` × 72h × $98.32/h | ~$56,632 |
| Storage | 10 TB × 72h | ~$85 |
| **Total** | | **~$56,717** |

The difference illustrates why right-sizing matters. Provisioning H100s for a job that runs fine on A100s doesn't just waste money. It can blow the budget by an order of magnitude.

### Inference (Azure OpenAI, pay-per-token)

```
Inference Cost = Requests × Avg Tokens/Request × Price per 1K Tokens
```

**Example: chatbot with GPT-4o (10K requests/day)**

| Component | Calculation | Cost |
|-----------|-------------|------|
| Input tokens | 10,000 req × 800 tokens × $0.0025/1K | $20/day |
| Output tokens | 10,000 req × 400 tokens × $0.01/1K | $40/day |
| **Monthly** | $60/day × 30 | **~$1,800/month** |

**Same chatbot with GPT-4o-mini:**

| Component | Calculation | Cost |
|-----------|-------------|------|
| Input tokens | 10,000 req × 800 tokens × $0.00015/1K | $1.20/day |
| Output tokens | 10,000 req × 400 tokens × $0.0006/1K | $2.40/day |
| **Monthly** | $3.60/day × 30 | **~$108/month** |

94% reduction. For many customer support scenarios, GPT-4o-mini is good enough. That price gap should force a design review, not a shrug.

## Purchasing models

| Factor | Pay-as-you-go | Reserved 1 year | Reserved 3 years | Spot VMs |
|--------|--------------|-----------------|-------------------|----------|
| **Discount** | 0% (baseline) | ~30-40% | ~50-60% | ~60-90% |
| **Commitment** | None | 1 year | 3 years | None |
| **Eviction risk** | None | None | None | High |
| **Best for** | Experimentation | Stable inference | Long-term training clusters | Fault-tolerant training |
| **Predictability** | Low | High | High | Low |

> **Don't reserve before you have data.** Wait 2-3 months of real utilization before committing to reserved instances. Many organizations reserve too early and end up paying for GPUs they don't use.

## Spot VMs: 60-90% discount with a catch

Azure Spot VMs offer the same GPU hardware at a steep discount, but Azure can reclaim them with 30 seconds' notice. This works when your framework supports **checkpoint-and-resume**.

### When Spot is safe

- Framework saves state periodically (weights, optimizer state, current epoch)
- Checkpoints go to durable storage (Blob Storage, not local disk)
- Examples: PyTorch Lightning (`ModelCheckpoint`), DeepSpeed (automatic checkpointing), Hugging Face Transformers (`save_steps` + `resume_from_checkpoint`)

### When Spot isn't safe

- Non-negotiable deadline (repeated evictions can cause delays)
- Checkpointing not implemented (each eviction restarts from zero, may cost more than pay-as-you-go)
- Very short jobs (< 1 hour; checkpoint/resume overhead doesn't pay off)
- Production inference (needs availability guarantees)

### Real savings

| Scenario | Pay-as-you-go | Spot (70% discount) | Savings |
|----------|--------------|---------------------|---------|
| 8× `NC24ads_A100_v4` (8 A100 GPUs), 72 hours | ~$5,702 | ~$1,711 | ~$3,991 |
| 1× `ND96isr_H100_v5` (8 H100 GPUs), 72 hours | ~$7,079 | ~$2,124 | ~$4,955 |

> **Checkpoint frequency:** If training costs $50/hour, checkpointing every 15 minutes caps re-work at $12.50 per eviction. And the checkpoint must go to Blob Storage, not local disk (which is lost on eviction).

## Right-sizing: don't use H100 when T4 will do

| Workload | Recommended SKU | Why |
|----------|----------------|-----|
| Inference (models ≤13B) | NC-series T4 | 16 GB memory, cost-effective |
| Inference (models 13B-70B) | NC-series A100 | 80 GB memory, good throughput |
| Fine-tuning (models ≤13B) | NC-series A100 (1-2 GPUs) | Sufficient with LoRA/QLoRA |
| Fine-tuning (models 70B+) | ND-series A100 (8 GPUs) | Needs multi-GPU + NVLink |
| Pre-training | ND-series H100 | Maximum throughput, NVLink + InfiniBand |

### Auto-shutdown for dev/test (mandatory)

```bash
# Configure auto-shutdown for 19:00 UTC
az vm auto-shutdown \
  --resource-group rg-ai-dev \
  --name gpu-vm-experiment-01 \
  --time 1900

# Turn it off again if you need an overnight run
az vm auto-shutdown \
  --resource-group rg-ai-dev \
  --name gpu-vm-experiment-01 \
  --off
```

An ND96isr_H100_v5 running from Friday evening to Monday morning: ~$4,700. Auto-shutdown eliminates that entirely.

## Azure OpenAI: Standard vs PTU

| Factor | Standard (pay-per-token) | Provisioned Throughput (PTU) |
|--------|--------------------------|------------------------------|
| **Pricing** | Per 1K tokens consumed | Fixed hourly/monthly rate |
| **Commitment** | None | Monthly or annual |
| **Best for** | Variable/unpredictable traffic | High, consistent traffic |
| **Latency** | Shared (variable) | Dedicated (consistent) |
| **High-volume cost** | Scales linearly (expensive) | Amortized (cheaper) |
| **Scale to zero** | Yes | No (minimum PTU) |

**Rule of thumb:** If your Standard deployment is consistently above 60-70% of the capacity a PTU would provide, PTU typically becomes cheaper.

### Token optimizations

- **Prompt caching:** Azure OpenAI supports automatic caching for repeated prefixes. Static system prompt at the beginning = cached tokens at reduced price
- **Shorter system prompts:** A 3,000-token prompt that could be 800 wastes 2,200 tokens per request. At 10,000 req/day with GPT-4o = ~$55/day in unnecessary tokens
- **`max_tokens`:** If the app needs 200-word responses, don't allow 2,000 tokens
- **Multi-model routing:** Simple queries (classification, extraction, FAQ) to GPT-4o-mini, complex ones to GPT-4o. Well-implemented routing cuts 50-80% of costs

## FinOps: mandatory tagging

Every AI resource needs at minimum:

| Tag | Purpose | Example |
|-----|---------|---------|
| `project` | Cost attribution | `project:chatbot-v2` |
| `team` | Responsible party | `team:ml-engineering` |
| `environment` | Lifecycle | `environment:dev` |
| `owner` | Accountable person | `owner:jane.smith` |
| `expected-end-date` | When to decommission | `expected-end-date:2026-06-15` |

```bash
# Find GPU VMs missing the owner tag
az resource list \
  --resource-type Microsoft.Compute/virtualMachines \
  --query "[?starts_with(properties.hardwareProfile.vmSize, 'Standard_N') && tags.owner == null].[name, resourceGroup, properties.hardwareProfile.vmSize]" \
  --output table
```

### Budget alerts (configure before provisioning)

```bash
# Create budget with alerts at 80% and 100%
az consumption budget create \
  --budget-name "ai-gpu-monthly" \
  --amount 50000 \
  --category cost \
  --time-grain monthly \
  --start-date 2026-01-01 \
  --end-date 2026-12-31 \
  --resource-group rg-ai-prod \
  --notifications '{
    "Actual_GreaterThan_80": {
      "enabled": true,
      "operator": "GreaterThan",
      "threshold": 80,
      "contactEmails": ["finops@contoso.com"]
    },
    "Actual_GreaterThan_100": {
      "enabled": true,
      "operator": "GreaterThan",
      "threshold": 100,
      "contactEmails": ["finops@contoso.com", "platform-oncall@contoso.com"]
    }
  }'
```

## In the next post

Once the cost controls are in place, the next problem is platform sprawl. The next post covers **platform ops**: how to move from "GPU provisioner on demand" to building a self-service AI platform with multi-tenancy, quotas, GPU queues, and governance.