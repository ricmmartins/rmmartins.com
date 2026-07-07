---
slug: "azure-openai-in-production-tokens-throughput-and-high-availability"
translationKey: "azure-openai-em-producao-tokens-throughput-e-alta-disponibilidade"
title: "Azure OpenAI in production: tokens, throughput, and high availability"
description: "HTTP 429 isn't a bug, it's bad capacity planning. Deployment types, PTU vs Standard, multi-region, retry patterns, and how not to take down your chatbot on launch day."
date: 2026-06-19T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - azure-openai
  - ptu
  - rate-limiting
  - high-availability
series:
  - "AI for Infrastructure Engineers"
---

Eleventh post in the series. In the [previous one](/2026/06/15/platform-ops-building-a-self-service-ai-platform/), we built the self-service AI platform with multi-tenancy and scheduling. Now: the service everyone wants to consume, Azure OpenAI, and how to operate it without getting 429'd in the face.

## The 429 that changed everything

Your team launched an internal GPT-4o chatbot on Monday. Day 1: smooth sailing, demos for leadership, Slack full of praise. Day 3: "the bot is slow." Day 5: 30% of requests return HTTP 429. You open Azure Monitor and discover you're hitting the 80K TPM ceiling.

The data science team's response? "Increase the limit." But it's not that simple. Quota increases aren't instantaneous, and throwing more TPM at the problem doesn't fix the underlying design. Some requests consume 4,000 tokens for a question that could fit in 200. The system prompt is 1,800 tokens, copied from a blog post and never trimmed. Retry logic hammers the endpoint without backoff, turning throttling into a cascading failure.

What you need isn't a bigger pipe. You need to understand how Azure OpenAI measures, limits, and charges for capacity.

## Tokens: the fundamental unit

A token is a chunk of a word. LLMs don't process text character by character; they break it into subwords. In English, 1 token ≈ 4 characters ≈ 0.75 words.

**Everything in Azure OpenAI is measured in tokens:** billing, throughput limits, context windows, rate limiting.

```
Total Tokens = System Prompt + User Input + Output (completion)
```

Typical chatbot: 500 tokens (system) + 300 (user) + 800 (response) = 1,600 tokens/request. Multiply by concurrent users and requests per minute: that's your throughput requirement.

**Infra ↔ AI translation:** Tokens are the payload packets of the AI world. TPM is your bandwidth ceiling (throughput per minute). RPM is your packets-per-second limit. Same diagnostic reasoning, different units.

### Context windows

| Model | Context Window |
|-------|---------------|
| GPT-4o | 128K tokens |
| GPT-4o-mini | 128K tokens |
| GPT-4 Turbo | 128K tokens |
| GPT-3.5 Turbo | 16K tokens |

A large context window doesn't mean you should fill it. A 100K-token request consumes the same TPM as 62 requests of 1,600 tokens.

## Deployment types: the architectural decision

| Characteristic | Standard | Global Standard | Provisioned (PTU) |
|---------------|----------|-----------------|-------------------|
| **Billing** | Pay per token | Pay per token | Fixed monthly cost per PTU |
| **Throughput** | Quota-limited (TPM/RPM) | Quota-limited, higher defaults | Reserved, guaranteed capacity |
| **Latency** | Variable (shared infra) | Variable (Microsoft-routed) | Predictable, low variance |
| **Data residency** | Single region | Microsoft selects region | Single region |
| **Throttling** | 429 when quota exceeded | 429 when quota exceeded | No throttling within capacity |
| **Best for** | Dev/test, variable workloads | Global apps, no residency restrictions | Production, apps with SLAs |

### When to use each

1. **Variable, low volume, experimental?** → Standard or Global Standard
2. **Need higher quotas, no data residency restriction?** → Global Standard
3. **Data residency within a geography (US, EU)?** → Data Zone
4. **Production with SLA, consistently high volume?** → Provisioned (PTU)
5. **Mission-critical production with overflow?** → PTU primary + Standard overflow

### Creating deployments via CLI

```bash
# Create Azure OpenAI resource
az cognitiveservices account create \
  --name aoai-prod \
  --resource-group rg-ai-prod \
  --kind OpenAI \
  --sku S0 \
  --location eastus

# Standard deployment (pay-per-token)
az cognitiveservices account deployment create \
  --name aoai-prod \
  --resource-group rg-ai-prod \
  --deployment-name gpt-4o-prod \
  --model-name gpt-4o \
  --model-version "2024-08-06" \
  --model-format OpenAI \
  --sku-name "Standard" \
  --sku-capacity 80
```

The `sku-capacity` in Standard is the TPM (in thousands). 80 = 80K TPM.

> **PTU throughput varies.** There's no fixed TPM-per-PTU number. It depends on the model, prompt length, and response length. Always use the [Azure OpenAI capacity calculator](https://oai.azure.com/portal/calculator) with your actual traffic patterns and validate with load testing before committing.

## Rate limiting: understanding the two axes

Azure OpenAI enforces two independent limits:

- **TPM** (Tokens Per Minute): total tokens (input + output) processed
- **RPM** (Requests Per Minute): number of API calls, regardless of tokens

You can hit TPM with a few large requests (RAG with long documents) or RPM with many small requests (single-line classification). They're different constraints that need different solutions.

### Checking deployment rate limits

```bash
az cognitiveservices account deployment show \
  --name aoai-prod \
  --resource-group rg-ai-prod \
  --deployment-name gpt-4o-prod \
  --query "properties.rateLimits"
```

## The correct retry pattern (and the wrong one)

The most common mistake: immediate retry in a tight loop. This turns occasional throttling into a storm that takes down the system.

```python
import time
import random
import openai

def call_with_backoff(client, messages, max_retries=5):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
        except openai.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            retry_after = int(e.response.headers.get("Retry-After", 1))
            wait = retry_after + random.uniform(0, 1)
            time.sleep(wait)
```

**Always respect the `Retry-After` header** and add random jitter to avoid thundering herd (all clients retrying at the same instant).

## High availability: multi-deployment

For production, never depend on a single deployment in a single region.

### Architecture with APIM as gateway

Azure API Management in front of multiple Azure OpenAI deployments:

1. **Primary:** PTU deployment in East US (guaranteed capacity, no 429s)
2. **Secondary:** Standard deployment in West US (overflow, pay-per-token)
3. **Tertiary:** Global Standard (catch-all when primaries are under pressure)

APIM handles routing based on availability and rate limit headers. If primary returns 429, it redirects to secondary automatically.

### Capacity monitoring

```bash
# Token transaction metrics
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/rg-ai-prod/providers/Microsoft.CognitiveServices/accounts/aoai-prod" \
  --metric "TokenTransaction" \
  --interval PT1M \
  --aggregation Total \
  --filter "ModelDeploymentName eq 'gpt-4o-prod'"
```

### Alerts that matter

| Metric | Threshold | Action |
|--------|-----------|--------|
| TPM usage > 80% | Sustained 5 min | Evaluate scale or routing |
| HTTP 429 rate > 1% | Sustained 2 min | Activate overflow deployment |
| TTFT P95 > 3s | Sustained 5 min | Investigate capacity |
| Error rate > 5% | Immediate | Incident response |

## Cost and performance optimization

### Prompt caching

Azure OpenAI supports automatic caching for repeated prefixes. If your system prompt is identical across all requests (and it should be), cached tokens are charged at a reduced price. Structure prompts with the static part first.

### Multi-model routing

Not every request needs the most capable (and most expensive) model. Route accordingly:

| Request type | Model | Rationale |
|-------------|-------|-----------|
| Simple FAQ, classification | GPT-4o-mini | 94% cheaper, sufficient quality |
| Short summarization | GPT-4o-mini | Good quality for simple texts |
| Complex reasoning | GPT-4o | Needs the full model |
| Code generation | GPT-4o | Accuracy matters more than cost |

A simple router (based on input length, keyword presence, or quick classification) can cut inference costs by 50-80%.

## In the next post

Azure OpenAI running with HA, correct retry, and multi-model routing. Next: the **troubleshooting playbook**. The real scenarios that generate pages at 2 AM: NVIDIA driver crash, CUDA OOM, pods stuck in Pending, and inference latency spikes.

---

*This is post 11 of the series "AI for Infrastructure Engineers", based on the book [AI for Infrastructure Professionals](https://ai4infra.com):*

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
11. **Azure OpenAI in Production**
12. [Troubleshooting Playbook](/2026/06/23/troubleshooting-playbook-incidents-that-will-wake-you-at-2am/)
13. [AI Use Cases for Infra Teams](/2026/06/27/ai-use-cases-for-infra-teams-aiops-and-beyond/)
14. [AI Adoption Framework](/2026/07/01/ai-adoption-framework-from-enthusiasm-to-governance/)
15. [Visual Glossary: Your Rosetta Stone](/2026/07/05/visual-glossary-infra-ai-your-rosetta-stone/)

