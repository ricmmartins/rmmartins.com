---
slug: "data-and-storage-for-ai-workloads"
aliases:
  - "/2026/05/14/data-and-storage-for-ai-workloads/"
translationKey: "dados-e-storage-para-workloads-de-ai"
title: "Data and storage for AI workloads: the bottleneck nobody sees"
description: "Expensive GPUs sitting idle waiting for slow disk is the #1 problem in AI infrastructure. Learn how to diagnose data starvation, choose the right storage, and build a pipeline that keeps GPUs fed."
date: 2026-05-14T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - storage
  - gpu
  - blobfuse2
  - azcopy
series:
  - "AI for Infrastructure Engineers"
---

This is the second post in the series where I translate AI into the language of infrastructure engineers. In the [first post](/2026/05/10/ai-for-infrastructure-engineers-why-ai-needs-you/), I showed that AI is just another workload and that your infra skills already prepare you more than you think.

Now for the bottleneck **everyone ignores**: storage. It is the hidden villain behind performance problems in almost every AI project I've seen.

## The midnight call

You did everything right. The ML team asked for a GPU cluster and you delivered: eight NVIDIA A100s across two nodes, high-bandwidth networking, CUDA drivers up to date. Clean deployment. The team kicked off their first training job Friday at 6 PM and you went home feeling good.

Your phone rings at midnight. The data science lead is frustrated: *"The GPUs aren't working. The training that was supposed to take four hours hasn't even finished the first epoch."*

You remote in and pull the metrics:

- **GPU utilization**: 12%
- **GPU memory**: one-third of total
- **Disk I/O**: 100%, read throughput crawling at 60 MB/s

The team stored 2 TB of training images on an Azure Files Standard HDD share, mounted over SMB. Your storage design is **starving** the most expensive hardware in the rack.

This story plays out at organizations every week. Teams spend serious money on GPUs and then discover that the data pipeline, the part **we** in infra own, is the real bottleneck.

## Why everything starts with data

Every AI system, from a simple classifier to a trillion-parameter LLM, depends on a formula:

**Data + Model + Compute = AI**

Remove any of the three and you have nothing. But the insight most of us miss early on is this: of the three components, **data is the one that touches infrastructure at every stage**. The model is code. Compute is provisioned and sits there running. Data has to be ingested, stored, prepared, served for training, and delivered at inference, and **each of those stages is an infrastructure problem**.

| Infra Concept | AI Equivalent | Why it matters |
|---------------|---------------|----------------|
| Storage account / volume | Dataset repository | Where raw data lives before the model sees it |
| Read throughput (MB/s) | Data loader speed | Determines how fast GPUs receive training batches |
| IOPS | Samples per second | Small-file workloads (images) need high IOPS |
| Storage tiers (Hot/Cool/Archive) | Lifecycle stages | Hot for active training, Cool for completed datasets, Archive for compliance |
| NFS/SMB mount | POSIX access for frameworks | PyTorch and TensorFlow expect filesystem semantics |
| Encryption at rest | Data protection compliance | Mandatory for PII, medical data, and financial records |

If you already manage storage, networking, and access control, you understand **70% of the AI data stack**. What changes is the *intensity*: AI workloads push read throughput, IOPS, and sequential I/O harder than almost anything you've provisioned before.

## Data starvation: the invisible bottleneck

The counterintuitive truth about AI infrastructure is simple: **the most common cause of low GPU utilization isn't a GPU problem. It's a storage problem**.

When the data loader can't feed batches to the GPU fast enough, the GPU sits idle waiting for data. This is called *data starvation*, and it turns your $50,000/month GPU cluster into an expensive space heater.

### How to diagnose

If a data scientist reports suspiciously low GPU utilization, **check storage before investigating anything else**. Nine times out of ten, the problem is one of these:

1. Training data on **Standard HDD**
2. Remote mount **without caching**
3. BlobFuse2 cache pointing at the **OS disk** instead of local NVMe

Classic data starvation signals:

```bash
# GPU utilization: if below 80% during training, storage is almost certainly the cause
nvidia-smi dmon -s u -d 5

# Disk I/O: if at 100% with low GPU, classic bottleneck
iostat -x 1 5

# Network (if dataset is remote): actual throughput vs capacity
sar -n DEV 1 5
```

The diagnostic pattern is simple:

| GPU Util | CPU Util | Disk I/O | Diagnosis |
|----------|----------|----------|-----------|
| Low | Low | High | **Data starvation**: storage can't feed data fast enough |
| Low | High | Low | CPU preprocessing is the bottleneck (heavy data augmentation) |
| High | High | High | Everything working well, balanced system |
| Low | Low | Low | Problem in model code or wrong batch size |

> ⚠️ **Rule of thumb**: A five-minute storage fix can turn a three-day training run into an overnight one. Always start with storage.

## Choosing the right storage: the decision matrix

This is the highest-impact decision you'll make for AI workload performance. Here's the map:

| Storage | Best for | Throughput | Latency | Cost | Don't use when |
|---------|----------|------------|---------|------|----------------|
| **Blob Storage** | Datasets, artifacts, checkpoints | Up to 60 Gbps/account | Moderate (ms) | Low (~$0.018/GB/month) | You need native POSIX without a mount |
| **Data Lake Gen2** | Analytical pipelines, versioned datasets | Up to 60 Gbps/account | Moderate (ms) | Low | Simple workload that doesn't need granular ACLs |
| **Local NVMe** | Training scratch, data loader cache | 3-7 GB/s per disk | Ultra-low (μs) | Included with the VM | You need persistence (data is lost on deallocation) |
| **Azure Files (NFS)** | Shared datasets across nodes | Up to 10 Gbps (premium) | Low-moderate | Moderate | Single-node workload where local NVMe is enough |
| **Azure Files (SMB)** | Legacy compatibility, Windows | Up to 4 Gbps (premium) | Moderate | Moderate | High-performance Linux training |
| **Cosmos DB** | Feature stores, real-time inference | N/A (request-based) | Single-digit ms | Higher | Storing raw training datasets |

The most common production pattern is a **two-tier approach**: store raw datasets in Blob Storage or Data Lake Gen2 for durability and cost, then stage the active working set to local NVMe for performance.

**Blob is your warehouse. NVMe is your workbench.**

> ⚠️ **Never use Standard HDD for training.** The IOPS and throughput limits are orders of magnitude below what GPUs need. A single A100 can consume data faster than Standard HDD-backed storage can serve it.

## The recommended pattern: Blob + NVMe + BlobFuse2

Most ML frameworks (PyTorch, TensorFlow) expect training data accessible through a filesystem path. **BlobFuse2** is the virtual filesystem driver that mounts Azure Blob Storage containers as a local directory on Linux.

BlobFuse2 has two caching modes, and choosing the right one matters:

- **File cache**: Downloads entire files to a local cache before serving reads. **Use for training** because datasets are read repeatedly across multiple epochs.
- **Block cache (streaming)**: Streams in chunks without downloading the complete file. Use for preprocessing or inference on large media files.

### Mount with file cache for training

Assume `config.yaml` already points at the target storage account and uses managed identity.

```bash
# Create cache directory on fast local storage (NVMe temp disk)
sudo mkdir -p /mnt/resource/blobfuse2cache
sudo chown $(whoami) /mnt/resource/blobfuse2cache

# Create mount point
sudo mkdir -p /mnt/training-data

# Mount with file cache
sudo blobfuse2 mount /mnt/training-data \
  --config-file=./config.yaml \
  --tmp-path=/mnt/resource/blobfuse2cache
```

### Preload: data ready before training starts

```bash
# Mount with preload: downloads data to cache at mount time
sudo blobfuse2 mount /mnt/training-data \
  --config-file=./config.yaml \
  --tmp-path=/mnt/resource/blobfuse2cache \
  --preload
```

> 💡 **Always** point `--tmp-path` to the VM's local NVMe disk (`/mnt/resource` on Azure VMs), not the OS disk. That gives the BlobFuse2 cache the lowest possible latency. On ND-series GPU VMs, the local temp disk can deliver 3-7 GB/s of read throughput.

### AzCopy for bulk data ingestion

When you need to move large datasets into Azure (or between storage accounts), AzCopy is the fastest option. It supports parallel transfers, automatic retries, and resumable uploads.

```bash
# Login with Microsoft Entra ID
azcopy login

# Copy an entire dataset directory to Blob Storage
azcopy copy './local-dataset/' \
  "https://${STORAGE_ACCOUNT}.blob.core.windows.net/training-data/v1/" \
  --recursive

# Copy between storage accounts (server-side, no local download)
azcopy copy \
  "https://<source-account>.blob.core.windows.net/<container>" \
  "https://<dest-account>.blob.core.windows.net/<container>" \
  --recursive
```

> 💡 Use `--cap-mbps` to limit throughput during business hours and unleash full speed at night.

## Security: built in, not bolted on

AI workloads handle some of the most sensitive data in the organization: customer records, medical images, financial transactions, proprietary text corpora.

Three non-negotiable rules:

**1. Managed identities + RBAC, always.**

Forget storage account keys. They're static, shareable, and hard to rotate. Managed identities are bound to specific resources, automatically rotated, and auditable.

```bash
# Assign Storage Blob Data Reader to a VM's managed identity
az role assignment create \
  --role "Storage Blob Data Reader" \
  --assignee <managed-identity-principal-id> \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>"
```

**2. Classify before ingesting.**

Before any data enters a training pipeline: is it public, internal, confidential, or restricted? Your storage architecture needs to enforce these classifications with network isolation, encryption, and access controls.

**3. Combat shadow data sprawl.**

Data scientists frequently copy data to local machines, shared drives, or unmanaged storage accounts for "quick experiments." Use Azure Policy to restrict storage account creation and Microsoft Purview to scan for copies outside approved locations.

## Hands-on: end-to-end optimized storage for AI

Here is a complete flow: provision, transfer, mount, and validate. The Azure CLI commands use `--auth-mode login`, and BlobFuse2 uses managed identity in `config.yaml`. No storage keys anywhere.

### 1. Create the storage account with Data Lake Gen2

```bash
RESOURCE_GROUP="rg-ai-training"
LOCATION="eastus2"
STORAGE_ACCOUNT="staitraining$(openssl rand -hex 4)"

az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION

az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2 \
  --enable-hierarchical-namespace true \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false
```

### 2. Configure RBAC (no keys!)

```bash
USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee-object-id $USER_OBJECT_ID \
  --assignee-principal-type User \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"
```

> Role assignments take 1-2 minutes to propagate. Wait before proceeding.

### 3. Create container and transfer data

```bash
az storage container create \
  --account-name $STORAGE_ACCOUNT \
  --name training-data \
  --auth-mode login

# For large datasets, use AzCopy
azcopy login
azcopy copy './local-dataset/' \
  "https://${STORAGE_ACCOUNT}.blob.core.windows.net/training-data/v1/" \
  --recursive
```

### 4. Mount with BlobFuse2 and NVMe cache

```bash
sudo mkdir -p /mnt/resource/blobfuse2cache
sudo chown $(whoami) /mnt/resource/blobfuse2cache
sudo mkdir -p /mnt/training-data

sudo blobfuse2 mount /mnt/training-data \
  --config-file=./config.yaml \
  --tmp-path=/mnt/resource/blobfuse2cache \
  --preload
```

### 5. Validate the pipeline is feeding the GPUs

```bash
# Verify data is accessible
ls /mnt/training-data/v1/ | head -20

# During training, monitor GPU vs I/O
nvidia-smi dmon -s u -d 5 &
iostat -x 1 5
```

If `nvidia-smi` shows GPU util above 80% and `iostat` isn't pegged at 100%, your data pipeline is healthy.

## Exit checklist

Before handing off storage for an AI workload:

- [ ] Active training data is staged on **premium or local storage** (Premium Files or local NVMe), never Standard HDD
- [ ] BlobFuse2 cache points to **local NVMe** (`/mnt/resource`), not the OS disk
- [ ] Access via **managed identity + RBAC**, no storage keys
- [ ] Data classified **before** entering the pipeline
- [ ] Storage sized for **10× current data** (datasets multiply with augmentation and versioning)
- [ ] **Throughput and IOPS** alerts configured
- [ ] Checkpoints writing back to **Blob Storage** for durability

## Next up

Now that you understand how data flows through AI systems and why your storage decisions determine training performance, it's time to look at the compute that consumes all that data. I'll talk about **GPUs, VM families, and cluster architecture**, and why a well-tuned storage layer is only half the equation.

The full book is available for free at [ai4infra.com](https://ai4infra.com).