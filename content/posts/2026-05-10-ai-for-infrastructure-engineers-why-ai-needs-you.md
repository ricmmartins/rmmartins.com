---
slug: "ai-for-infrastructure-engineers-why-ai-needs-you"
aliases:
  - "/2026/05/10/ai-for-infrastructure-engineers-why-ai-needs-you/"
translationKey: "ai-para-engenheiros-de-infraestrutura-por-que-ai-precisa-de-voce"
title: "AI for infrastructure engineers: why AI needs you"
description: "You don't need to become a data scientist to work with AI. Your infrastructure skills already prepare you more than you think for the age of artificial intelligence."
date: 2026-05-10T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - gpu
  - career
  - mlops
series:
  - "AI for Infrastructure Engineers"
---

This is the first post in a series where I'll translate the world of AI into the language that infrastructure engineers already speak. If you're the kind of professional who configures VMs, builds CI/CD pipelines, and gets woken up at 2 AM when Nagios fires, this content is for you.

The series is based on my open-source book [AI for Infrastructure Professionals](https://ai4infra.com), adapted and expanded here on the blog.

## The Monday morning message

It's 8:47 AM on a Monday. You're halfway through your coffee, reviewing a Terraform plan for a network redesign, when a Slack message lights up your screen. It's from the data science team lead:

> *"Hey, we need 8 GPU VMs provisioned by Wednesday for a fine-tuning job. We also need a private endpoint for the model's inference API, and can you set up TPM monitoring? Thanks!"*

You read it twice. GPU VMs? Fine-tuning? You know what a private endpoint is. You've configured hundreds. Monitoring? That's your bread and butter. But what the hell is "TPM" in this context? It isn't Trusted Platform Module. It's **Tokens Per Minute**, a throughput metric for language models. You don't know that yet, but that's fine.

Notice something: **everything else in that request is pure infrastructure.**

Provisioning compute. Configuring network security. Setting up observability. You've been doing this for years. The only difference is the type of workload.

## AI is just another workload

Let me be direct. Strip away the buzzwords. AI is a workload. It consumes compute, storage, and networking, just like every other workload you've ever managed. What changes is the *shape* of that demand: more parallel compute, larger datasets, and different performance metrics.

The AI stack runs on three layers you already know:

| AI Layer | What it does | Your infra equivalent |
|----------|-------------|----------------------|
| **Data** | Feeds the model with examples | Storage: Blob, Data Lake, NFS, databases |
| **Model** | Learns patterns and makes predictions | The application, your compiled binary running on compute |
| **Infrastructure** | Holds everything up underneath | Your domain: compute, networking, security, observability |

The model is the application. The data is what it consumes and produces. The infrastructure is everything that makes it run reliably, securely, and at scale. **That part is yours.**

## Translating AI into infrastructure language

Back in 2014, when I started writing about Docker on this blog, the first thing I did was translate the concepts into something sysadmins already understood. I'm doing the same thing now with AI.

When someone from the AI team throws jargon you don't recognize, map it back to what you already know:

| AI Concept | Infrastructure Equivalent | Why it works |
|------------|--------------------------|--------------|
| Trained model | Compiled binary | A static artifact produced by a build process, deployed to serve requests |
| Training a model | Batch job | Long-running, compute-intensive process that reads data and produces an output artifact |
| Inference | An API call | Request comes in, the model processes it, response goes out. Just like any microservice |
| Fine-tuning | Patching a binary | You take an existing artifact and customize it for your environment |
| Dataset | Database / Data Lake | Structured input that the workload depends on |
| Training pipeline | CI/CD pipeline | Automated workflow: ingest → process → build → validate → deploy |
| Model registry | Artifact repository | Versioned storage for deployable artifacts (like ACR, but for models) |
| GPU cluster | High-performance compute | Specialized hardware allocated for heavy workloads |

> 💡 **Meeting tip**: When the data science team starts talking about "epochs", "hyperparameters", and "loss functions", don't panic. Those are *their tuning knobs*, the equivalent of your connection pool sizes, cache TTLs, and autoscale thresholds. You do not need to master them. You need to understand what they demand from your infrastructure.

## What changes and what stays the same

The good news: AI infrastructure isn't a different planet. It's more like a new neighborhood in a city you already know. The streets follow the same grid, the utilities work the same way, but the buildings look different and the residents have unusual needs.

### What changes

| Dimension | Traditional Infra | AI Infra |
|-----------|-------------------|----------|
| **Compute** | CPUs, general-purpose VMs | GPUs (NVIDIA T4, A100, H100), multi-GPU nodes |
| **Storage** | SSD/HDD, managed disks | Data Lakes, high-throughput Blob, local NVMe for scratch |
| **Networking** | 1 to 25 GbE Ethernet | InfiniBand (up to 400 Gb/s), RDMA, GPU-to-GPU communication |
| **Deployment** | VMs, App Services, containers | Inference endpoints, model-as-a-service, GPU-enabled containers |
| **Observability** | CPU %, memory, disk I/O | GPU utilization, VRAM, tokens/second, time-to-first-token |
| **Cost** | $/hour per VM | $/hour per GPU (10x to 30x CPU cost), PTUs for managed services |

### What doesn't change

This matters just as much. The workload may run on GPUs, but these fundamentals **do not change**:

- **Security**: Network segmentation, private endpoints, identity management, encryption. A GPU VM still needs an NSG. An inference API still needs authentication.
- **Networking**: VNets, subnets, DNS, load balancing. Packets still flow the same way.
- **Infrastructure as Code**: Bicep, Terraform, ARM templates. GPU VMs are still Azure resources with properties and parameters.
- **Monitoring**: You'll still set thresholds, build dashboards, and respond to incidents. The metrics just have different names.
- **Cost management**: Budgets, tagging, right-sizing. If anything, cost governance is **more critical** with AI workloads.

> ⚠️ **Production alert**: The most common failures in production AI systems aren't model accuracy problems. They're the same old villains: disk full, network timeout, expired certificate, missing RBAC permission. Your instincts are right.

## Why AI needs you (not the other way around)

The AI industry has a people problem, and it's not what you'd expect. Data scientists who can build models in Jupyter notebooks are plentiful. What's actually scarce are engineers who can take those models and run them reliably in production.

In my experience working with startups and enterprises at Microsoft, I see the same pattern over and over:

**Uncontrolled GPU sprawl.** A data scientist requests 4 `Standard_NC24ads_A100_v4` VMs for an experiment. No resource locks, no budget alerts, no tagging. Three weeks later, the VMs are still running. Nobody remembers who provisioned them or whether the experiment finished. Monthly burn rate: **about $11,000**.

**Exposed inference endpoints.** The ML team deploys a model to a managed endpoint with public network access. No private endpoint, no WAF, no API management. The model can end up serving responses that expose proprietary business logic.

**Blind observability.** The team monitors model accuracy but not infrastructure health. Inference latency jumps from 200 ms to 8 seconds, and nobody can tell whether the cause is the model, the compute, the network, or a noisy neighbor.

> ⚠️ **The $13K GPU weekend**: A team provisioned 8 `Standard_ND96asr_v4` VMs on a Friday afternoon for a training run that was supposed to finish Saturday morning. The job crashed at 3 AM because checkpoint storage was misconfigured, but the VMs kept running. Nobody had set up auto-shutdown or budget alerts. Monday surprise: **about $13,000 in compute** for 60 hours of idle GPU. An infrastructure engineer would have configured `auto-shutdown`, set a budget alert at $2,000, and stored checkpoints in Blob with lifecycle policies. Fifteen minutes of infra work would have saved roughly **$11,000**.

## Hands-on: your first AI reconnaissance

You don't need to train a model or write Python. You need to understand that GPU compute is available to you and what your subscription's limits are. This is reconnaissance, the same first step you'd take before architecting any new workload.

### Discover GPU VMs in your region

```bash
az vm list-skus --location eastus2 --size Standard_N --resource-type virtualMachines --output table
```

This filters the `Standard_N` family, which includes all GPU-accelerated VMs in Azure. Pay attention to three prefixes:

- **NC**: Compute-optimized GPUs for training and inference (NVIDIA T4, A100)
- **ND**: High-end GPUs for distributed deep learning with InfiniBand (A100, H100)
- **NV**: GPUs for visualization and lightweight inference (AMD Radeon, NVIDIA A10)

### Check your GPU quota

```bash
az vm list-usage --location eastus2 --output table | grep -E "NC|ND|NV"
```

> On Windows/PowerShell, replace `grep -E "NC|ND|NV"` with `Select-String -Pattern "NC|ND|NV"`.

If your quota is zero across the board, you'll need to request an increase before any provisioning. That's exactly the kind of infra work that the data science team doesn't know (and doesn't want to know) how to do.

## Next up

I'll talk about **data and storage for AI workloads**, the piece everyone ignores until it becomes the hidden performance bottleneck in almost every AI project I've seen.

The full book is available for free at [ai4infra.com](https://ai4infra.com).