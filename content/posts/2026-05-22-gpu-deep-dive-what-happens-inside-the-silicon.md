---
slug: "gpu-deep-dive-what-happens-inside-the-silicon"
aliases:
  - "/2026/05/22/gpu-deep-dive-what-happens-inside-the-silicon/"
translationKey: "gpu-deep-dive-o-que-acontece-dentro-do-silicio"
title: "GPU deep dive: what happens inside the silicon"
description: "Why doesn't a 14 GB model fit on a 40 GB GPU? How to read nvidia-smi like a pro? Understand GPU architecture, memory hierarchy, multi-GPU strategies, and troubleshooting."
date: 2026-05-22T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - gpu
  - cuda
  - deepspeed
series:
  - "AI for Infrastructure Engineers"
---

Fourth post in the series. In the [previous one](/2026/05/18/compute-for-ai-choosing-the-right-hardware/), you learned which GPU VMs to provision and how to connect them. This time we look **inside** the GPU so you can troubleshoot better and talk to the ML team without guessing.

## The 2 AM ticket

Slack fires at 2 AM. The ML team's training job crashed again. The error is a single line:

```
CUDA out of memory. Tried to allocate 2.00 GiB
```

The data science lead is frustrated: *"The model has 7 billion parameters in FP16. That's only 14 GB. The A100 has 40 GB of memory. There should be 26 GB to spare. What's going on?"*

You SSH in, run `nvidia-smi`, and see memory usage at 100%. But the math doesn't add up: 14 GB of weights do not fill 40 GB. Unless something else is eating the rest. And it is. Model parameters are just **one piece** of the memory puzzle. Gradients, optimizer states, and activations each claim their own slice. A "14 GB model" needs 90+ GB to train with full-precision Adam.

This post gives you the knowledge to answer that question and dozens like it.

## GPU architecture for infrastructure engineers

You don't need to design circuits. But you need a mental model of what's inside the box, because it explains why workloads behave the way they do, why certain errors appear, and why certain SKUs are dramatically better than others for the same job.

### Streaming Multiprocessors (SMs)

A GPU is built from repeated units called **Streaming Multiprocessors (SMs)**. Each SM is an independent processor with its own cores, cache, and scheduling hardware. The A100 has 108 SMs. The H100 has 132.

Think of each SM as a small, self-contained factory floor. It has its own workers (cores), local storage (shared memory and registers), and its own scheduler.

### CUDA Cores vs. Tensor Cores

Inside each SM:

- **CUDA Cores**: general-purpose parallel processors. A100 = 6,912, H100 = 16,896. Handle floating-point and integer math.
- **Tensor Cores**: specialized units that perform matrix-multiply-and-accumulate in a single clock cycle. A100 = 432 (3rd gen), H100 = 528 (4th gen). They're the reason modern GPUs dominate AI.

**Infra ↔ AI translation:** A GPU is like a 100-lane highway where each lane carries math operations simultaneously. A CPU is a 4-lane highway where each lane can handle curves, exits, and complex decisions. For matrix multiplication (the foundation of AI), you want the highway.

### NVLink: the GPU-to-GPU superhighway

When you have multiple GPUs in the same node, they need to communicate. PCIe provides a baseline connection (64 GB/s), but for serious multi-GPU training, you need **NVLink**:

| GPU | NVLink Bandwidth (bidirectional) |
|-----|--------------------------------|
| A100 | 600 GB/s |
| H100 | 900 GB/s |
| B200 | 1.8 TB/s |

Check NVLink with:

```bash
nvidia-smi topo -m
```

If it shows `PIX` or `PHB` between GPUs instead of `NV#`, you're on PCIe, not NVLink. Confirm you're on the right SKU (ND-series) before debugging performance issues.

## GPU memory: the resource you'll manage most

If you remember one section from this post, make it this one. GPU memory, and specifically running out of it, is the #1 problem you'll troubleshoot in AI infrastructure.

### Memory hierarchy

| Layer | A100 Spec | H100 Spec | Analogy |
|-------|-----------|-----------|---------|
| **HBM** (High Bandwidth Memory) | 40 or 80 GB, 2 TB/s | 80 GB, 3.35 TB/s | System RAM |
| **L2 Cache** | 40 MB | 50 MB | CPU L3 cache |
| **Shared Memory / L1** | Up to 164 KB per SM | Up to 256 KB per SM | CPU L1/L2 cache |
| **Registers** | 256 KB per SM | 256 KB per SM | CPU registers |

**HBM** is what `nvidia-smi` reports. It's the GPU's "main memory", where model weights, training data, and intermediate results live.

### What fills memory during training

Four main consumers:

**1. Model Parameters (the weights)**
Straightforward sizing: parameters × bytes per parameter. 7B params in FP16 (2 bytes each) = ~14 GB.

**2. Gradients**
One gradient per parameter during backpropagation. 7B × 2 bytes = another ~14 GB.

**3. Optimizer States (the hidden killer)**
The Adam optimizer maintains **two additional values** per parameter (momentum and variance), stored in FP32 regardless of model precision. 7B × 4 bytes × 2 states = **~56 GB** just for the optimizer.

**4. Activations**
Intermediate results from each layer, saved during the forward pass and consumed during backpropagation. Depend on architecture and **batch size**.

### The math that saves your weekend

```
Total GPU Memory ≈ Parameters + Gradients + Optimizer States + Activations
```

For the 7B model from the ticket:

| Component | Calculation | Memory |
|-----------|------------|--------|
| Parameters (FP16) | 7B × 2 bytes | ~14 GB |
| Gradients (FP16) | 7B × 2 bytes | ~14 GB |
| Optimizer States (FP32, Adam) | 7B × 4 bytes × 2 | ~56 GB |
| Activations (varies) | Depends on batch size | ~8-20 GB |
| **Total** | | **~92-104 GB** |

A "14 GB model" needs 90+ GB to train. An A100-40GB never stood a chance. Even an A100-80GB is tight.

> **Rule of thumb:** when an ML engineer says "the model is X gigabytes," they almost always mean the parameter size (the checkpoint file). Training memory is usually **4x to 8x larger**. Multiply by at least 4x for a quick estimate with Adam.

**Gradient checkpointing** (activation recomputation) trades compute for memory: instead of saving all activations during the forward pass, it saves only some and recomputes the rest during backpropagation. Reduces training speed by ~20-30% but cuts activation memory by 60-80%.

## Precision: trading accuracy for speed and memory

| Format | Bits | Bytes/param | Range | Use case |
|--------|------|-------------|-------|----------|
| **FP32** | 32 | 4 | ±3.4 × 10³⁸ | Full-precision training, master weights |
| **TF32** | 19* | 4 (stored) | = FP32 | Default on A100+ for matmul, transparent |
| **BF16** | 16 | 2 | ±3.4 × 10³⁸ | Preferred for training (same range as FP32) |
| **FP16** | 16 | 2 | ±65,504 | Training with loss scaling, inference |
| **INT8** | 8 | 1 | -128 to 127 | Quantized inference |
| **INT4** | 4 | 0.5 | -8 to 7 | Aggressively quantized inference |

**BF16** is the current sweet spot for training. It maintains the same exponent range as FP32 but uses half the memory. Most modern pipelines use BF16.

**INT8/INT4** are for inference. A model trained in BF16 can be quantized to INT8 or INT4 after training, drastically reducing memory with slight quality loss.

**Infra ↔ AI translation:** Think of precision like JPEG quality. FP32 is RAW (highest quality, largest file). BF16 is high-quality JPEG (imperceptibly different, half the size). INT4 is a thumbnail (visibly lossy, but loads instantly).

## Multi-GPU strategies

When the model doesn't fit on one GPU or training takes days:

### Data Parallelism (DP)

Full copy of the model on each GPU. Each GPU processes a different batch. After each step, GPUs synchronize gradients via **all-reduce**. Scales nearly linearly: 8 GPUs ≈ 8× throughput.

Catch: each GPU needs to hold the entire model + gradients + optimizer states.

### DeepSpeed ZeRO: the memory limit destroyer

| Stage | What's partitioned | Savings per GPU | Communication overhead |
|-------|-------------------|-----------------|----------------------|
| **ZeRO-1** | Optimizer states | Optimizer memory is sharded across GPUs | Minimal |
| **ZeRO-2** | Optimizer states + Gradients | Adds gradient sharding on top of ZeRO-1 | Moderate |
| **ZeRO-3** | Optimizer + Gradients + Parameters | Full sharding, maximum memory savings | Higher |

Back to the 7B example: training with Adam on one GPU = ~92 GB. With 8 GPUs and ZeRO-3, each GPU holds only about one-eighth of the sharded states, plus activations. That brings the per-GPU footprint down enough that the model that would not fit on one A100-80GB can train across eight A100-40GBs.

### FSDP (Fully Sharded Data Parallel)

PyTorch's native answer to ZeRO-3. Same capability (full sharding of parameters, gradients, optimizer states), integrated directly into PyTorch's distributed training API. From an infra perspective, FSDP and ZeRO-3 have similar requirements.

### Pipeline Parallelism (PP)

Divides the model's layers sequentially across GPUs: GPU 0 = layers 1-10, GPU 1 = layers 11-20, etc. Each GPU holds only a fraction of the parameters. Downside: **pipeline bubbles** (GPUs waiting for data).

### Tensor Parallelism (TP)

The most granular approach splits individual layers across GPUs. It really wants NVLink. Running TP over PCIe is technically possible, but usually not worth the pain.

### 3D Parallelism (100B+ models)

Combines all three:
- **TP** within the node (over NVLink)
- **PP** across a few nodes
- **DP** (with ZeRO) across many nodes

This is the standard pattern for training very large models.

| Model Size | Strategy | GPUs | Network required |
|-----------|----------|------|-----------------|
| < 1B params | Single GPU or DP | 1-8 | PCIe OK |
| 1-10B params | DP + ZeRO-2 | 4-16 | NVLink preferred |
| 10-70B params | ZeRO-3 / FSDP | 8-64 | NVLink + InfiniBand |
| 70-200B+ params | 3D Parallelism | 64-512+ | NVLink + InfiniBand mandatory |

## The NVIDIA software stack

Every GPU debugging session ends up in software compatibility. The stack is layered, where each level depends on the one below:

```
Model code (training script)
    ↓
Framework (PyTorch 2.x, TensorFlow, JAX)
    ↓
cuDNN (optimized DL primitives) + NCCL (multi-GPU)
    ↓
CUDA Toolkit (libraries, runtime, compiler)
    ↓
NVIDIA Driver (kernel module → GPU hardware)
    ↓
GPU Hardware (A100, H100, etc.)
```

A mismatch at any level = problems ranging from cryptic error messages to silent crashes.

**The container escape hatch:** Use NVIDIA NGC images (`nvcr.io/nvidia/pytorch`) that bundle a tested combination of driver API, CUDA, cuDNN, NCCL, and framework:

```bash
# Pull official NVIDIA PyTorch container (monthly releases)
docker pull nvcr.io/nvidia/pytorch:24.05-py3

# Run with GPU access
docker run --gpus all -it nvcr.io/nvidia/pytorch:24.05-py3
```

**Troubleshooting tip:** Always collect three versions first:

```bash
# Driver version + max supported CUDA
nvidia-smi

# Installed CUDA Toolkit
nvcc --version

# CUDA that PyTorch was compiled against
python -c "import torch; print(torch.version.cuda)"
```

A mismatch between any of these = most likely cause of the problem.

## Reading nvidia-smi like a pro

`nvidia-smi` is the `top` of the GPU world. Typical output:

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.161.08    Driver Version: 535.161.08    CUDA Version: 12.2               |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |          Memory-Usage  | GPU-Util  Compute M. |
|=========================================+========================+======================|
|   0  NVIDIA A100-SXM4-80GB         On   | 00000001:00:00.0  Off  |                    0 |
| N/A   42C    P0              72W / 400W |  71458MiB / 81920MiB   |     94%      Default |
+-----------------------------------------+------------------------+----------------------+
```

### Fields that matter

| Field | What it means | Healthy (training) | Problematic |
|-------|--------------|-------------------|-------------|
| **GPU-Util** | % of active compute | 85-100% | Below 50% |
| **Memory-Usage** | HBM in use | 70-95% | 100% (OOM) or < 30% (underutilized) |
| **Temp** | Temperature °C | 35-75°C | Above 83°C (throttling) |
| **Pwr:Usage/Cap** | Consumption vs. limit | 60-90% of cap | Below 30% (idle) |
| **Perf** | Performance state | P0 | P2+ during active job |
| **ECC Errors** | Memory errors | 0 | Any value > 0 |
| **Persistence-M** | Persistent driver | On | Off (adds latency) |

### Essential commands

```bash
# Basic snapshot (90% of usage)
nvidia-smi

# Continuous monitoring (refresh every 5s)
nvidia-smi -l 5

# CSV output for scripting and dashboards
nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used --format=csv

# Compact real-time monitoring
nvidia-smi dmon -s u

# GPU topology: check NVLink
nvidia-smi topo -m

# Check ECC errors (hardware health)
nvidia-smi --query-gpu=ecc.errors.uncorrected.volatile.total --format=csv

# List GPU processes
nvidia-smi pmon -s u -c 1
```

## The 7 GPU problems you'll encounter

### 1. CUDA Out of Memory (OOM)

```
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
```

**Fixes (in order):** reduce batch size → enable gradient checkpointing → ZeRO-2/3 → mixed precision BF16 → bigger GPU.

### 2. CUDA Version Mismatch

```
CUDA error: no kernel image is available for execution on the device
```

**Fix:** check the 3 versions (driver, toolkit, framework). Use an NGC container with versions tested together.

### 3. GPU Not Found

```
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
```

**Fix:** verify VM SKU (NC/ND/NV?), check VM Extension status, reboot, reinstall driver.

### 4. ECC Errors (hardware failure)

```bash
nvidia-smi --query-gpu=ecc.errors.uncorrected.volatile.total --format=csv
# If it returns > 0: open a ticket with Azure for replacement
```

GPUs don't support live migration on Azure. Expect downtime.

### 5. Thermal Throttling

Temp above 83°C, perf state drops from P0 to P2/P3, throughput drops 20-40%. In cloud, this is Azure's problem. Document it and open a ticket.

### 6. Low GPU Utilization

GPU-Util < 50% during active training = **data starvation**. Fixes: increase DataLoader `num_workers`, `pin_memory=True`, cache on local NVMe, optimized formats (WebDataset, TFRecord).

### 7. NVLink Not Detected

`nvidia-smi topo -m` shows `PHB`/`PIX` instead of `NV#`. Verify you're on ND-series (NC/NV don't have NVLink).

## GPU generations on Azure

| Generation | GPU | Azure VM | HBM | NVLink | InfiniBand |
|-----------|-----|----------|-----|--------|------------|
| Volta (2017) | V100 | NC v3 | 16/32 GB | No | No |
| Ampere (2020) | A100 | ND A100 v4 | 40/80 GB | 600 GB/s | 200 Gb/s |
| Hopper (2022) | H100 | ND H100 v5 | 80 GB | 900 GB/s | 400 Gb/s |
| Blackwell (2024) | B200 | ND GB200 v6 | 192 GB | 1.8 TB/s | 400 Gb/s |

Each generation doubles HBM bandwidth and introduces new precision formats: Ampere brought TF32 and structured sparsity, Hopper brought FP8 and Transformer Engine, Blackwell brings FP4 and 192 GB of HBM per GPU.

## Next up

Now that you understand what happens inside the GPU (architecture, memory, software stack, debugging), it's time to automate everything around it. Next post: **Infrastructure as Code for AI**, how to template GPU clusters, inference endpoints, and training pipelines in a reproducible, versioned, and auditable way.