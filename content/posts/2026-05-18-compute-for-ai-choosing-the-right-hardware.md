---
slug: "compute-for-ai-choosing-the-right-hardware"
aliases:
  - "/2026/05/18/compute-for-ai-choosing-the-right-hardware/"
translationKey: "compute-para-ai-escolhendo-o-hardware-certo"
title: "Compute for AI: choosing the right hardware (and connecting it properly)"
description: "The difference between a two-day training job and a 90-minute one isn't a faster GPU. It's knowing which GPU to use and how to connect them. A complete guide to GPU VMs on Azure."
date: 2026-05-18T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - gpu
  - compute
  - aks
  - infiniband
series:
  - "AI for Infrastructure Engineers"
---

Third post in the series where I translate AI into the language of people who live and breathe infrastructure. In the [previous post](/2026/05/14/data-and-storage-for-ai-workloads/), we talked about the storage bottleneck nobody notices until it hurts. This one is about **compute**.

Spoiler: it is not enough to buy the most expensive GPU. You need the **right** GPU, connected the **right way**.

**tl;dr**

- Pick hardware based on training vs inference, not on sticker price.
- GPU family, memory size, and interconnect matter more than vCPU count.
- For distributed jobs, quota, availability, and network fabric decide whether the cluster performs or stalls.

## The story you don't want to live

The ML team asks for "a GPU cluster for training." You do what any infra engineer would do under time pressure: provision eight `Standard_D64s_v5` VMs. Sixty-four vCPUs each, 256 GiB of RAM, Premium SSD. On paper, it looks respectable.

The team launches the training script. Progress bar: estimated completion in **47 hours**. CPUs pinned at 100%, network barely registering traffic, and nobody looks happy.

Then a colleague suggests two `Standard_ND96asr_v4` nodes, each with eight A100 GPUs and 200 Gb/s InfiniBand. Same training job, same dataset, same code. The job finishes in **90 minutes**.

The difference is not just the GPUs. It is how they talk to each other inside the node with NVLink, how they synchronize gradients across nodes with InfiniBand, and how data moves without the CPU becoming the choke point. Compute for AI is not raw horsepower. It is the **right kind** of power, wired the **right way**.

## Training vs. inference: two different worlds

Before choosing any SKU, you need to know which workload will run. Training and inference look similar on the surface, but their infrastructure profiles are completely opposite.

| Dimension | Training | Inference |
|-----------|----------|-----------|
| **Workload pattern** | Batch, runs for hours/days/weeks | Real-time, millisecond responses |
| **GPU demand** | Saturates all available cores | Often runs on a single GPU (or CPU) |
| **Memory pressure** | GPU memory-bound (weights + gradients + optimizer states) | Compute-bound (forward pass only) |
| **Scaling axis** | Scale *up* (bigger GPUs, more nodes) | Scale *out* (more replicas behind a load balancer) |
| **Cost model** | Total job cost (hours × GPUs × price/hr) | Cost per request (latency × throughput × price) |
| **Failure impact** | Restart from last checkpoint, hours lost | Lost request, retry in milliseconds |
| **Network sensitivity** | Extreme: gradient sync every few seconds | Moderate: small payloads |

**Infra to AI translation:** Think of **training** as a massive batch job, like re-indexing a petabyte data warehouse. Think of **inference** as a high-traffic API endpoint, like your authentication service handling thousands of logins per second. The infra patterns you already know apply directly.

### When CPU is enough

Not every AI workload needs a GPU. Lightweight inference scenarios (small classification models, embedding generation for search, edge deployment) run fine on `Standard_D` or `Standard_F` VMs. If the model fits comfortably in RAM and the latency requirement is above 50 ms, benchmark on CPU first. GPUs are expensive; don't use them when you don't need to.

**Practical tip:** ask the ML team two things before provisioning anything: (1) "Are we training or serving?" and (2) "How big is the model in parameters?" A 350-million-parameter model usually runs inference on CPU. A 70-billion-parameter one does not.

## Why GPUs dominate AI

A modern server CPU has 32 to 128 cores optimized for complex logic with branching. A GPU like the NVIDIA H100 has **16,896 CUDA cores** and **528 Tensor Cores**, all designed to do one thing extremely well: multiply matrices in parallel.

AI workloads are mostly matrix multiplication. Every layer of a neural network multiplies an input matrix by a weight matrix, adds a bias, and applies an activation function. The CPU processes this sequentially across a few dozen cores. The GPU processes thousands of these operations simultaneously.

**Infra ↔ AI translation:** Think of the GPU like a SmartNIC that offloads packet processing from the CPU. Just as a SmartNIC handles millions of packets per second without overloading the host, the GPU offloads millions of matrix operations. The CPU orchestrates; the GPU does the heavy math.

### CUDA Cores vs. Tensor Cores

Not all GPU cores are equal:

- **CUDA cores** are general-purpose parallel processors that handle any floating-point math
- **Tensor Cores** are specialized units that perform matrix multiply-and-accumulate in mixed-precision in a single clock cycle

For AI workloads using FP16 or BF16 (which is most training today), Tensor Cores deliver up to **8× the throughput** of CUDA cores alone. When looking at GPU specs, pay attention to the Tensor Core count. That number defines your real AI performance more than the CUDA core count.

## GPU VM families on Azure: the decision matrix

Choosing the right GPU VM family is the highest-impact decision you'll make for an AI workload. Get it right and training finishes on time, within budget. Get it wrong and you burn money on idle hardware or wait days for results that should take hours.

| Family | Example SKU | GPUs | GPU Mem | Interconnect | Best For | ~Cost/hr |
|--------|-------------|------|---------|--------------|----------|----------|
| **NC T4 v3** | `Standard_NC4as_T4_v3` | 1× T4 | 16 GiB | Ethernet | Cost-efficient inference, light training, dev/test | $0.53 |
| **NC T4 v3** | `Standard_NC64as_T4_v3` | 4× T4 | 64 GiB | Ethernet | Multi-model inference, batch scoring | $4.25 |
| **ND A100 v4** | `Standard_ND96asr_v4` | 8× A100 40GB | 320 GiB | InfiniBand 200 Gb/s | Distributed training, large model fine-tuning | $27.20 |
| **ND H100 v5** | `Standard_ND96isr_H100_v5` | 8× H100 80GB | 640 GiB | InfiniBand 400 Gb/s | Flagship training, LLMs, NCCL-optimized | $98.32 |
| **NV A10 v5** | `Standard_NV36ads_A10_v5` | 1× A10 (full) | 24 GiB | Ethernet | Visualization, light AI, dev/test | $1.80 |
| **NV A10 v5** | `Standard_NV6ads_A10_v5` | ⅙× A10 | 4 GiB | Ethernet | Fractional GPU for small workloads | $0.45 |
| **D/E/F series** | `Standard_D16s_v5` | None | N/A | Accel. Networking | Preprocessing, data pipelines, CPU inference | $0.77 |

*Approximate pay-as-you-go prices, East US. Always verify on the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/).*

> **Warning:** The **original ND-series** (ND6s, ND12s, ND24s, ND24rs) was **retired in September 2023**. If you find Terraform templates or blog posts referencing those SKUs, they'll fail on deploy. The current ND-series is `Standard_ND96asr_v4` (A100) and `Standard_ND96isr_H100_v5` (H100).

### How to choose

**For inference:** start with `Standard_NC4as_T4_v3`. The T4 is NVIDIA's inference workhorse: supports INT8 and FP16, has dedicated Tensor Cores, and costs a fraction of the A100. If the model fits in 16 GiB of GPU memory, start here.

**For training:** depends on model size. Fine-tuning a model with fewer than 10B parameters? A single `Standard_ND96asr_v4` node with eight A100s may suffice. Training a 70B+ model from scratch? Multiple `Standard_ND96isr_H100_v5` nodes connected via InfiniBand, running DeepSpeed or PyTorch FSDP.

**For dev/test:** use `Standard_NV6ads_A10_v5` (fractional GPU) or CPU-only VMs. Don't burn ND-series quota on Jupyter notebooks.

**Check availability before anything else:**

```bash
az vm list-skus \
  --location eastus2 \
  --resource-type virtualMachines \
  --query "[?contains(name,'Standard_N')].{Name:name, Zones:locationInfo[0].zones, Restrictions:restrictions[0].reasonCode}" \
  -o table
```

If the `Restrictions` column shows `NotAvailableForSubscription`, you need to request a quota increase in the Azure portal under **Subscriptions → Usage + quotas**.

## Clustering: when one VM isn't enough

Three reasons to distribute an AI workload: the model is too large for one GPU's memory, training is too slow on a single node, or you need to serve more inference requests than one VM can handle. Each reason points to a different clustering strategy.

| Platform | Best For | GPU Support | Scaling | Complexity |
|----------|----------|-------------|---------|------------|
| **AKS** | Inference at scale, microservices | GPU node pools, device plugin, taints | HPA + Cluster Autoscaler | Medium |
| **Azure Machine Learning** | Experiment tracking, managed training | Managed compute clusters, auto-provisioning | Built-in, job-based | Low |
| **VMSS** | Homogeneous GPU workloads, batch | Custom images with pre-installed drivers | Instance-based autoscaling | Low-Medium |
| **Ray / DeepSpeed / Horovod** | Distributed training frameworks | Run on top of AKS or VMs | Managed by framework | High |

### AKS for GPU workloads

AKS is the most common platform for serving AI models at scale. When you add GPU VMs to an AKS cluster, three things need to be configured correctly: the **taint on the node pool**, the **NVIDIA device plugin**, and the **tolerations on your pods**.

AKS automatically applies a taint to GPU node pools so non-GPU workloads don't land on expensive nodes:

```
sku=gpu:NoSchedule
```

Your GPU pods need a matching toleration and must explicitly request GPU resources:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-inference
spec:
  tolerations:
  - key: "sku"
    operator: "Equal"
    value: "gpu"
    effect: "NoSchedule"
  containers:
  - name: model-server
    image: myregistry.azurecr.io/model-server:latest
    resources:
      limits:
        nvidia.com/gpu: 1
```

The NVIDIA device plugin runs as a DaemonSet on GPU nodes and exposes `nvidia.com/gpu` as a schedulable resource to Kubernetes. Without it, Kubernetes does not even know GPUs exist on the node.

> **Warning:** The GPU taint in AKS is `sku=gpu:NoSchedule`, **not** `nvidia.com/gpu`. Many tutorials use the wrong key, which leaves your pods stuck in `Pending` forever.

## Networking: the hidden multiplier

A fact that surprises most infra engineers the first time they run into AI workloads: **the network is often the bottleneck, not the GPU**. In distributed training, GPUs synchronize gradients after each forward and backward pass. With eight GPUs per node and multiple nodes, that creates tens of gigabytes of traffic every few seconds. If the network cannot keep up, the GPUs wait, and you keep paying for expensive silicon that is doing nothing.

### InfiniBand and RDMA

**InfiniBand** enables **RDMA (Remote Direct Memory Access)**. With GPUDirect RDMA, one node can move data between the NIC and GPU memory without bouncing it through host CPU memory first. That is why gradient synchronization gets dramatically faster on the right hardware.

On Azure, InfiniBand is available on:
- `Standard_ND96asr_v4`: 200 Gb/s InfiniBand (HDR)
- `Standard_ND96isr_H100_v5`: 400 Gb/s InfiniBand (NDR)

For distributed training with NCCL (NVIDIA Collective Communications Library), InfiniBand delivers **10× or more throughput** compared to TCP/IP over Ethernet. NCCL detects and uses InfiniBand automatically when available.

### Accelerated Networking

For VMs that don't support InfiniBand (NC-series, NV-series, D/E/F-series), **Accelerated Networking** uses SR-IOV to bypass the host's virtual switch. Network latency drops from ~500 μs to ~25 μs, and throughput reaches the VM's maximum. No extra cost; just make sure it's enabled on the NIC.

### Network comparison table

| Feature | Throughput | Latency | Available On | Use Case |
|---------|-----------|---------|--------------|----------|
| InfiniBand NDR | 400 Gb/s | < 2 μs | ND H100 v5 | Multi-node LLM training |
| InfiniBand HDR | 200 Gb/s | < 2 μs | ND A100 v4 | Distributed training |
| Accelerated Networking | Up to 100 Gbps | ~25 μs | Most D/E/F/N series | Inference, data pipelines |
| Standard Ethernet | Up to 100 Gbps | ~500 μs | All VMs | General workloads |

### Proximity placement groups

Deploying distributed training nodes across **different availability zones** adds cross-zone latency that can reduce training throughput by **30-50%**. For multi-node jobs, always use a **proximity placement group**:

```bash
# Create proximity placement group
az ppg create \
  --resource-group rg-ai-training \
  --name ppg-training-cluster \
  --location eastus2 \
  --intent-vm-sizes Standard_ND96asr_v4

# Create VMSS inside the proximity placement group
az vmss create \
  --resource-group rg-ai-training \
  --name vmss-training \
  --image Ubuntu2204 \
  --vm-sku Standard_ND96asr_v4 \
  --instance-count 4 \
  --ppg ppg-training-cluster \
  --accelerated-networking true
```

**Troubleshooting tip:** when investigating slow distributed training, check network throughput *before* blaming the GPUs. Run `ib_write_bw` (InfiniBand bandwidth test) between nodes. If it's significantly below the expected 200 or 400 Gb/s, the problem is network configuration, not model code.

## Hands-on: create your first GPU VM

Time to get your hands dirty. We'll provision a GPU VM, install NVIDIA drivers, and validate that the GPU is operational. We'll use `Standard_NC4as_T4_v3`, the cheapest option and a good lab box.

### Step 0: define variables

```bash
RESOURCE_GROUP="rg-ai-lab"
LOCATION="eastus2"
VM_NAME="vm-gpu-lab"
VM_SIZE="Standard_NC4as_T4_v3"
ADMIN_USER="azureuser"
```

### Step 1: check quota

```bash
az vm list-skus \
  --location $LOCATION \
  --size $VM_SIZE \
  --resource-type virtualMachines \
  --query "[].{Name:name, Restrictions:restrictions[0].reasonCode}" \
  -o table
```

If it shows `NotAvailableForSubscription`, request a quota increase in the portal.

### Step 2: create the resource group

```bash
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

### Step 3: create the GPU VM

```bash
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --image Ubuntu2204 \
  --size $VM_SIZE \
  --admin-username $ADMIN_USER \
  --generate-ssh-keys \
  --accelerated-networking true \
  --public-ip-sku Standard
```

This provisions an Ubuntu 22.04 VM with one NVIDIA T4, 4 vCPUs, and 28 GiB of RAM.

### Step 4: install NVIDIA drivers (via VM Extension)

The VM Extension is the recommended approach. It installs the correct driver version, signs the kernel module for Secure Boot, and integrates with Azure update management:

```bash
az vm extension set \
  --resource-group $RESOURCE_GROUP \
  --vm-name $VM_NAME \
  --name NvidiaGpuDriverLinux \
  --publisher Microsoft.HpcCompute
```

Monitor progress (takes 5-10 minutes):

```bash
az vm extension show \
  --resource-group $RESOURCE_GROUP \
  --vm-name $VM_NAME \
  --name NvidiaGpuDriverLinux \
  --query provisioningState \
  -o tsv
```

### Step 5: validate the GPU

SSH into the VM and confirm the GPU is recognized:

```bash
ssh $ADMIN_USER@$(az vm show \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --show-details \
  --query publicIps -o tsv)
```

Once connected:

```bash
nvidia-smi
```

You should see a Tesla T4 with ~15 GiB of available memory, driver version, and CUDA version. If `nvidia-smi` returns "command not found", the extension hasn't finished installing yet.

### Step 6: cleanup

GPU VMs are expensive even when idle. Delete the resource group when done:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

> **Real cost:** A `Standard_NC4as_T4_v3` costs ~$0.53/hr. Manageable for a lab. But a `Standard_ND96isr_H100_v5` costs ~$98/hr. Leaving one running over a weekend = **$4,700+**. Always configure [cost alerts](https://learn.microsoft.com/azure/cost-management-billing/costs/cost-mgt-alerts-monitor-usage-spending) and auto-shutdown policies for GPU VMs.

## Monitoring GPU workloads

GPU infrastructure needs specific observability. Traditional CPU metrics (load average, memory usage) tell you nothing about whether the GPU is being utilized or starving.

| Metric | Tool | What it tells you |
|--------|------|-------------------|
| GPU utilization (%) | `nvidia-smi`, DCGM Exporter | Is the GPU computing or idle? |
| GPU memory used (GiB) | `nvidia-smi`, DCGM Exporter | Close to OOM (out-of-memory)? |
| GPU temperature (°C) | `nvidia-smi`, DCGM Exporter | Thermal throttling? GPUs reduce clock above 83°C |
| Inference latency (P50/P95/P99) | App Insights, OpenTelemetry | User experience, SLA compliance |
| Token throughput (tokens/sec) | Application logs, Azure OpenAI metrics | Model serving efficiency |

**Recommended setup:** Deploy **NVIDIA DCGM Exporter** as a DaemonSet on AKS GPU node pools. It exposes GPU metrics in Prometheus format, which **Azure Managed Prometheus** scrapes automatically. Combine with pre-built **Grafana** dashboards for GPU utilization, memory, temperature, and error rates.

## Closing the loop

The 47-hour job in the opening story was never a general compute shortage. It was a hardware selection mistake. CPU-heavy VMs and the wrong interconnect cannot substitute for the right GPU family.

## Further reading

- [Virtual machine sizes overview for Azure VMs](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/overview#gpu-accelerated)
- [Use GPUs on Azure Kubernetes Service (AKS)](https://learn.microsoft.com/en-us/azure/aks/use-nvidia-gpu)
- [Proximity placement groups](https://learn.microsoft.com/en-us/azure/virtual-machines/co-location)

## Next up

Now that you know which VMs to provision and how to connect them, it's time to look **inside** the GPU. In the next post, we'll do a deep dive into GPU architecture: CUDA memory hierarchy, multi-GPU strategies, the driver ecosystem, and how to read `nvidia-smi` output like a pro. You do not need to write CUDA kernels, but understanding what happens inside the silicon will make you a better troubleshooter and a better capacity planner.