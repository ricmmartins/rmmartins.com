---
slug: "visual-glossary-infra-ai-your-rosetta-stone"
aliases:
  - "/2026/07/05/visual-glossary-infra-ai-your-rosetta-stone/"
translationKey: "glossario-visual-infra-ai-sua-pedra-de-roseta"
title: "Visual glossary infra ↔ AI: your Rosetta Stone"
description: "Every AI term mapped to an infrastructure concept you already know. From 'model' to 'ZeRO', with practical analogies and context for when each one shows up in your work."
date: 2026-07-05T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - glossary
  - reference
series:
  - "AI for Infrastructure Engineers"
---

Final post in the series. In the [previous one](/2026/07/01/ai-adoption-framework-from-enthusiasm-to-governance/), we built the 6-phase adoption framework. This one is the cheat sheet.

You already speak infrastructure fluently. AI is not a foreign language. It is infrastructure with worse naming and more hype. This glossary maps each AI term to something you already understand.

## How to use this

Every entry has: the **AI term**, the **infra analogy** in parentheses, a **concise definition**, and **when you'll encounter it** in your work. It is split into 6 categories so you can find things fast instead of pretending you remember all of it.

## Core AI concepts

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **Model** | Compiled binary | The trained artifact, deployable to serve predictions. Contains the learned parameters. | Managing deployments, versioning artifacts, sizing storage (models range from MBs to hundreds of GBs) |
| **Training** | Batch job | The process of teaching the model by feeding data and adjusting parameters. Long-running, GPU-intensive. | Provisioning GPU clusters, estimating job duration, planning compute bursts |
| **Inference** | API endpoint | Running a trained model on new data to generate responses. Real-time, latency-sensitive. | Every time a user or system calls an AI service. This is the production workload you monitor and scale |
| **LLM** | Specialized API service (text-in, text-out) | Foundation model trained on a massive text corpus to understand and generate human language. GPT-4, Claude, LLaMA. | Deploying Azure OpenAI endpoints, sizing token quotas, capacity planning |
| **Fine-tuning** | Configuration customization | Adapting a pre-trained model to your domain by training on your data. | When teams need the model to understand internal terminology or specific processes |
| **Foundation Model** | Base image / golden image | Large pre-trained model (GPT-4, LLaMA, Mistral) meant to be adapted for many downstream tasks. | Selecting which base model to deploy or fine-tune. It's the starting artifact in most AI projects |
| **Parameters / Weights** | Configuration values | The internal numerical values that define how the model processes input and generates output. Large models can have enormous parameter counts, though vendors often keep the exact number private. | Sizing infra: more parameters = more memory, more compute, more storage |
| **Epoch** | Full backup cycle | One complete pass through the entire training dataset. Fine-tuning jobs often talk in epochs; large-scale pretraining usually talks in tokens instead. | Estimating duration and cost of training jobs |
| **Batch Size** | Chunk size | Number of samples processed before updating weights. Larger = more GPU memory, more efficient. | Tuning training jobs and troubleshooting OOM errors (reducing batch size is usually the first fix) |
| **Transfer Learning** | Template reuse | Using a model pre-trained on one task as a starting point for another, preserving learned knowledge. | When teams want faster, cheaper results by starting from a foundation model |

## Data and storage

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **Dataset** | Data source / storage volume | Structured or unstructured data used to train, validate, or test a model. GBs to PBs. | Provisioning storage, planning data pipelines, managing access controls |
| **Embedding** | Hash / index key | Numerical vector representation of text/images that captures semantic meaning. Enables similarity search. | Deploying RAG architectures, sizing vector databases |
| **Tokenization** | Serialization | Breaking text into smaller units (tokens) that the model processes. Similar to object serialization. | Calculating costs (you pay per token like you pay per byte transferred), estimating context window usage, optimizing prompts |
| **Vector Database** | Search index | Specialized database that stores embeddings and searches by similarity (nearest-neighbor). | Deploying RAG, provisioning Azure AI Search with vector capabilities |
| **Feature Store** | Caching layer for ML inputs | Centralized repository of pre-computed features for training and inference. | Architecting ML platforms that need low-latency access to features |
| **Data Drift** | Schema change / input distribution shifted | When statistical properties of production data diverge from training data. Degrades accuracy. | Model performance degrades without code changes. The silent killer of ML accuracy |

## Compute and hardware

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **GPU** | Coprocessor | Processor designed for massive parallel computation, offloading matrix math from the CPU. | Everywhere in AI infra: provisioning VM SKUs, monitoring utilization, managing costs |
| **CUDA** | GPU instruction set / SDK | NVIDIA's parallel computing platform that enables code to execute on GPUs. | Installing drivers, configuring GPU containers, troubleshooting "CUDA out of memory" |
| **HBM** | GPU RAM | High-bandwidth memory stacked on the GPU die. A100 has 80 GB HBM2e. | Selecting GPU SKUs: HBM capacity determines the maximum model size a GPU can support |
| **InfiniBand** | High-speed node-to-node networking | Ultra-low-latency, high-bandwidth interconnect for distributed training. Much faster than Ethernet. | Provisioning multi-node GPU clusters (ND-series VMs) for large training jobs |
| **NVLink** | GPU-to-GPU interconnect | High-speed link connecting GPUs within a single node. It provides much more bandwidth than plain PCIe, though the exact ratio depends on the generation. | Sizing multi-GPU VMs: GPUs with NVLink exchange data fast enough to matter for model parallel workloads |
| **Tensor Core** | Specialized matrix math unit | Dedicated hardware in NVIDIA GPUs optimized for matrix multiply-and-accumulate operations that dominate AI. | Evaluating GPU generations: Tensor Cores are why A100 is dramatically faster for AI than gaming GPUs |

## Model operations

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **Checkpoint** | Snapshot / backup | Saved copy of model state during training: weights, optimizer state, progress. | Managing storage (checkpoints can be tens of GBs each), designing fault-tolerant training |
| **Gradient** | Error signal | Mathematical value indicating direction and magnitude of weight adjustments to reduce error. | Troubleshooting training instability: "exploding gradients" and "vanishing gradients" |
| **Hyperparameter** | Tunable config value | Value set before training that controls the process: learning rate, batch size, layers. Like thread count or pool size. | When data scientists ask for multiple training runs with different configs: each combo is a separate job |
| **MLOps** | DevOps for models | Applying DevOps practices (CI/CD, versioning, monitoring, automation) to the ML lifecycle. | Building ML platforms, designing model deployment pipelines |
| **Model Registry** | Container registry for models | Versioned repository for storing and managing trained model artifacts. | Implementing MLOps pipelines that need to version, promote, and rollback model deployments |

## Deployment and serving

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **Prompt** | API request body | Text input sent to the model to guide output: instructions, context, examples, question. | Every LLM interaction. Prompt design impacts quality, token consumption, and cost |
| **Completion** | API response body | Output generated by the model in response to a prompt. | Parsing responses, calculating output token costs, monitoring quality |
| **Context Window** | Maximum request payload size | Maximum tokens the model processes in one request (prompt + completion combined). | Designing prompts and RAG systems: exceeding context window truncates input or causes errors |
| **Inference Endpoint** | API endpoint serving predictions | Deployed model exposed as an HTTP API that accepts input and returns predictions. | Provisioning, scaling, and monitoring the production-facing AI service |
| **PTU** | Reserved capacity (like reserved instances) | Provisioned Throughput Unit. Pre-allocated capacity for Azure OpenAI models that gives you more predictable latency and throughput inside the capacity you bought. | When workloads need predictable performance and you can justify reserved capacity |
| **RAG** | Dynamic prompt enrichment with external data | Pattern that retrieves relevant documents from a knowledge base and injects them into the prompt before generation. | Building enterprise AI solutions that need to answer using specific, up-to-date data |
| **TPM** | Bandwidth / throughput quota | Maximum tokens processed per minute for a deployment. Primary throughput metric for LLM endpoints. | Sizing deployments, estimating costs, diagnosing throttling |
| **RPM** | Request rate limit | Maximum API calls per minute for a deployment. Independent of token quotas. | Capacity planning and troubleshooting HTTP 429 |

## Advanced concepts

| AI Term | Infra Analogy | Definition | When it shows up |
|---------|---------------|------------|-----------------|
| **Data Parallelism** | Sharding data across GPUs | Strategy where the dataset is split across GPUs, each processing a different batch with a full model copy. | Scaling training to multiple GPUs. The simplest approach to distributed training |
| **Model Parallelism** | Sharding model across GPUs | Splitting a model across multiple GPUs when it doesn't fit in one GPU's memory. Each GPU holds part of the layers. | Deploying very large models (70B+ parameters) that exceed a single GPU's HBM |
| **LoRA** | Lightweight fine-tuning | Technique that trains a small set of adapter weights instead of the entire model, often a tiny fraction of the total parameters. | When teams want to customize a foundation model without the cost of full fine-tuning |
| **Mixed Precision** | Variable data type optimization | Training with a mix of FP32 and BF16/FP16, using lower precision where possible to reduce memory and increase throughput. | Optimizing training jobs: mixed precision can nearly double throughput on modern GPUs |
| **Quantization** | Compression | Reducing model precision (FP32 → INT8 or INT4) to shrink size and speed up inference. Trades small accuracy for large efficiency. | Deploying models with cost or latency constraints: quantization can cut memory usage by 4x+ |
| **Prompt Injection** | SQL injection for AI | Attack where untrusted input is crafted to override model instructions, causing unintended behavior. | Securing AI endpoints exposed to user input. One of the first security problems you have to deal with in LLM applications |
| **ZeRO** | Memory optimization for distributed training | Zero Redundancy Optimizer. A family of techniques that partitions optimizer states, gradients, and parameters across GPUs to eliminate redundancy. | Training large models that do not fit in GPU memory even with data parallelism. A standard DeepSpeed approach |

## Quick reference: top 20 terms

Pin this card. You will need it.

| # | AI Term | Infra Translation |
|---|---------|-------------------|
| 1 | **Model** | Compiled binary, deployable training output |
| 2 | **Training** | Long-running batch job that produces a model |
| 3 | **Inference** | Real-time API call against a deployed model |
| 4 | **GPU** | Coprocessor that offloads matrix math |
| 5 | **LLM** | Text-in/text-out API service |
| 6 | **Prompt** | API request body |
| 7 | **Completion** | API response body |
| 8 | **Token** | Minimum processing unit (you pay per token like you pay per byte transferred) |
| 9 | **Context Window** | Maximum request payload size |
| 10 | **Fine-tuning** | Customize a base image with your data |
| 11 | **RAG** | Dynamic prompt enrichment with fetched data |
| 12 | **Embedding** | Numerical hash/index key for similarity search |
| 13 | **Checkpoint** | Snapshot/backup of training state |
| 14 | **TPM** | Bandwidth quota (tokens per minute) |
| 15 | **PTU** | Reserved capacity with predictable throughput |
| 16 | **CUDA** | NVIDIA's GPU SDK/instruction set |
| 17 | **LoRA** | Adapter-based fine-tuning with a tiny parameter slice |
| 18 | **MLOps** | DevOps applied to model lifecycle |
| 19 | **Data Drift** | Input distribution shifted, model degrades |
| 20 | **Quantization** | Model compression (4x less memory) |

## Series wrap-up

15 posts. From the first concept (why infrastructure engineers matter for AI) to this glossary. If you made it through the whole series, you now have enough context to talk to data scientists, architects, finance, and security without treating AI like a magic trick.

The full book, in English, is available for free at [ai4infra.com](https://www.ai4infra.com). If this series saved you a few hours, send it to another infra engineer who is getting dragged into AI projects.

AI does not replace what you know. It leans on it. Networking, storage, compute, security, automation, cost control, and ugly incident response at bad hours are still the job. Now you have the vocabulary to map those instincts onto AI systems.