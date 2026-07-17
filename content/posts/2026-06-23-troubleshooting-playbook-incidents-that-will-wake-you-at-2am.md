---
slug: "troubleshooting-playbook-incidents-that-will-wake-you-at-2am"
aliases:
  - "/2026/06/23/troubleshooting-playbook-incidents-that-will-wake-you-at-2am/"
translationKey: "troubleshooting-playbook-os-incidentes-que-vao-te-acordar-as-2am"
title: "Troubleshooting playbook: incidents that will wake you at 2AM"
description: "NVIDIA driver crash, CUDA OOM, pods stuck in Pending, 429 storm, and latency spikes. Symptoms, diagnosis, root cause, and prevention for each real-world scenario."
date: 2026-06-23T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - troubleshooting
  - kubernetes
  - gpu
  - azure-openai
series:
  - "AI for Infrastructure Engineers"
---

Twelfth post in the series. In the [previous one](/2026/06/19/azure-openai-in-production-tokens-throughput-and-high-availability/), we ran Azure OpenAI with HA and sane retry patterns. This one is for when the nice diagram meets real life.

This post is organized as real-world failure scenarios. Each follows: **Symptoms → Diagnosis → Root Cause → Resolution → Prevention**. Read it once for pattern recognition. Then bookmark it. You will need it again.

**tl;dr**

- Most late-night AI infra incidents come down to driver drift, memory pressure, scheduler mismatch, throttling, or cold starts.
- Start with the first check that rules out the biggest class of failure.

## Scenario 1: NVIDIA driver crash after kernel update

### Symptoms

Monday morning. The ML team reports that all GPU workloads failed over the weekend. Nobody deployed anything. You SSH in:

```bash
$ nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
Make sure that the latest NVIDIA driver is installed and running.
```

GPU containers won't start. Training jobs dead. The VM itself is fine, CPU workloads run normally.

### Diagnosis

```bash
# Check whether the driver module exists for the running kernel
modinfo nvidia
# modinfo: ERROR: Module nvidia not found.

# Current kernel
uname -r
# 6.5.0-44-generic

# Check DKMS build status
dkms status | grep nvidia
# nvidia/535.183.01: added

# What happened
grep -A 5 "linux-image" /var/log/apt/history.log
# unattended-upgrade installed new kernel
```

### Root cause

Ubuntu's `unattended-upgrades` installed a new kernel automatically. The NVIDIA kernel module has to exist for the running kernel version. If DKMS or the driver extension does not rebuild cleanly, the VM comes back on the new kernel without a matching NVIDIA module.

### Resolution

```bash
# Option A: reinstall driver extension (Azure VMs)
az vm extension set \
  --resource-group myRG \
  --vm-name myGPUVM \
  --name NvidiaGpuDriverLinux \
  --publisher Microsoft.HpcCompute \
  --version 1.9

# Option B: pin kernel version and reinstall driver
sudo apt-mark hold linux-image-$(uname -r) linux-headers-$(uname -r)
sudo apt install --reinstall nvidia-driver-535
sudo reboot
```

### Prevention

Disable automatic kernel upgrades on all GPU VMs. Add to `/etc/apt/apt.conf.d/50unattended-upgrades`:

```
Unattended-Upgrade::Package-Blacklist {
    "linux-image";
    "linux-headers";
    "linux-modules";
};
```

Use the Azure NVIDIA GPU Driver Extension for driver lifecycle. Treat kernel upgrades as planned maintenance.

> **This failure is silent.** The VM boots normally, passes health checks, responds to SSH. Only GPU workloads fail. If you don't monitor `nvidia-smi` output, you only find out when users complain.

## Scenario 2: CUDA Out of Memory during fine-tuning

### Symptoms

A fine-tuning job starts well, runs for 10-30 minutes, then crashes:

```
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
(GPU 0; 79.15 GiB total capacity; 77.42 GiB already allocated;
1.08 GiB free; 78.50 GiB reserved in total by PyTorch)
```

"But it worked for the first 500 steps."

### Diagnosis

```bash
# Continuous GPU memory monitoring
watch -n 1 nvidia-smi

# Memory log for analysis
nvidia-smi --query-gpu=timestamp,memory.used,memory.free,utilization.gpu \
  --format=csv -l 5 > gpu_memory.csv
```

Calculate expected memory (7B model with Adam in BF16):

| Component | Memory |
|-----------|--------|
| Parameters (BF16) | ~14 GB |
| Gradients (BF16) | ~14 GB |
| Optimizer States (FP32, Adam) | ~56 GB |
| Activations (varies with batch) | Variable |
| **Minimum total** | **~84 GB + activations** |

### Root cause

Batch size = 8. At the start of training, short sequences in the dataset produced small activation tensors. As the data loader reached longer sequences, activation memory grew until it exceeded what was left on the GPU. OOM didn't happen at step 1 because the first batches fit.

### Resolution

```python
# Immediate fix: reduce batch size, maintain effective batch with accumulation
training_args = TrainingArguments(
    per_device_train_batch_size=2,       # Reduced from 8
    gradient_accumulation_steps=4,        # Maintains effective batch = 8
)

# Better fix: gradient checkpointing (trades extra compute for lower activation memory)
model.gradient_checkpointing_enable()

# For larger models: LoRA (trains <1% of parameters)
from peft import LoraConfig, get_peft_model

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# trainable params: 6.5M || all params: 6.74B || trainable%: 0.096%
```

### Prevention

- Always calculate required memory before starting
- Set `max_seq_length` explicitly to cap activation memory
- Use `gradient_accumulation_steps` to maintain effective batch with a small per-GPU batch

> If OOM happens at random steps (not consistently at step N), suspect variable-length sequences. Set `max_seq_length` and pad/truncate.

## Scenario 3: AKS GPU pods stuck in Pending

### Symptoms

```bash
$ kubectl get pods -n ml-team
NAME                        READY   STATUS    RESTARTS   AGE
training-job-7b-xyz         0/1     Pending   0          20m
```

### Diagnosis

```bash
$ kubectl describe pod training-job-7b-xyz -n ml-team
Events:
  Warning  FailedScheduling  18m   0/12 nodes are available:
    3 node(s) had untolerated taint {sku=gpu:NoSchedule},
    9 node(s) didn't match Pod's node affinity/selector.
```

The taint message is the key. AKS GPU node pools apply `sku=gpu:NoSchedule` by default. The pod needs a matching toleration.

```bash
# Check if it's a quota issue
az vm list-usage --location eastus -o table | grep -i "Standard NC\|Standard ND"

# Check node pool scaling limits
az aks nodepool show --cluster-name myAKS --resource-group myRG \
  --name gpunp --query '{min:minCount, max:maxCount, current:count}'
```

### Root cause

Pod spec missing the required toleration. The scheduler sees GPU nodes as ineligible.

Other common causes:
- GPU quota exhausted (cluster autoscaler can't provision new nodes)
- Node pool at `maxCount` (autoscaler wants to scale but can't)

### Resolution

```yaml
# Add toleration to the pod spec
spec:
  tolerations:
    - key: "sku"
      operator: "Equal"
      value: "gpu"
      effect: "NoSchedule"
  containers:
    - name: training
      resources:
        limits:
          nvidia.com/gpu: 1
```

If quota is the issue:

```bash
az extension add --name quota

az quota create-or-update \
  --scope "/subscriptions/{sub-id}/providers/Microsoft.Compute/locations/eastus" \
  --resource-name "standardNDSv2Family" \
  --limit 48 \
  --unit Count
```

### Prevention

- Template all GPU pod specs with pre-configured tolerations
- Alert at 80% GPU quota usage
- Configure cluster autoscaler with headroom in `maxCount`

> A pod stuck in Pending produces no logs, because no container exists. Always check `kubectl describe pod` for events, not `kubectl logs`.

## Scenario 4: Azure OpenAI 429 storm

### Symptoms

30%+ of requests returning HTTP 429. Users report slowness or timeouts.

```json
{
  "error": {
    "code": "429",
    "message": "Requests to the ChatCompletions_Create Operation under Azure OpenAI API have exceeded the token rate limit..."
  }
}
```

### Diagnosis

Check the `Retry-After` header:
- `Retry-After: 1` = slightly over the limit
- `Retry-After: 30` = dramatically above the limit

Some SDKs expose the same signal as `retry-after-ms`. Use either one. They are telling you the same thing: back off.

```bash
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}" \
  --metrics "TokenTransaction" \
  --interval PT1M \
  --aggregation Total \
  --filter "ModelDeploymentName eq 'gpt-4o-prod'"
```

### Root cause

Standard deployment with 80K TPM. Product launch generated a burst of 200K+ TPM. Standard enforces hard rate limits; every request above gets 429.

### Resolution

1. **Immediate:** Implement exponential backoff with jitter (code in the previous post)
2. **Short-term:** Second deployment in another region for overflow
3. **Long-term:** Evaluate PTU for predictable, high-volume workloads

### Prevention

- Multi-deployment architecture with APIM load balancing
- Alerts at 80% of provisioned TPM
- Token-aware queue on the client (estimate tokens before sending)
- Log token count per request to forecast before launches

## Scenario 5: Inference latency spike

### Symptoms

P99 latency jumps from 200ms to 3 seconds. No deployment, no config change. "The AI is slow."

### Diagnosis

```bash
# GPU busy?
nvidia-smi --query-gpu=utilization.gpu,utilization.memory,temperature.gpu \
  --format=csv -l 2

# Container restarted?
kubectl get pods -n inference -w
kubectl describe pod model-serve-abc -n inference | grep -A 5 "Last State"

# Cold start? (model being reloaded)
kubectl logs model-serve-abc -n inference | grep -i "model loaded\|loading model"
# [2024-07-15 08:14:47] Model loaded in 164.2 seconds
```

164 seconds of model loading is not a latency blip. It is a restart wearing a latency costume.

If `Last State` shows `OOMKilled`, the restart is probably your root cause. If the pod falls into `CrashLoopBackOff`, Kubernetes is telling you the container keeps dying faster than the platform can stabilize it.

### Root cause (usually a combination)

1. **Container cold start:** Pod evicted (OOM, node drain, spot reclaim), model reloading from Blob Storage (14+ GB over network)
2. **GPU thermal throttling:** Sustained 100% utilization pushes the card toward its thermal limit, clocks drop, latency follows
3. **Noisy neighbor:** Another pod on the same node consuming CPU/memory/network needed for pre/post-processing

### Resolution

**For cold starts:** Use an init container that downloads model weights to local NVMe before the serving container starts. Set a readiness probe that only marks ready after the model is loaded.

**For thermal throttling:** Monitor `DCGM_FI_DEV_GPU_TEMP` and alert above 78°C. Reduce batch size to lower sustained utilization.

**For noisy neighbor:** Use `nodeSelector` or dedicated taints to isolate inference pods on exclusive nodes.

### Prevention

- Readiness probe that checks model loaded (not just container up)
- Model cache on local NVMe (not downloading from Blob on every start)
- GPU temperature monitoring with proactive alerts
- Inference pods on dedicated nodes without sharing

## Further reading

- [Install NVIDIA GPU drivers on N-series VMs](https://learn.microsoft.com/azure/virtual-machines/linux/n-series-driver-setup)
- [Use NVIDIA GPUs on AKS](https://learn.microsoft.com/azure/aks/use-nvidia-gpu)
- [Azure OpenAI quotas and limits](https://learn.microsoft.com/azure/ai-foundry/openai/quotas-limits)
- [Monitor Azure OpenAI](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/monitor-openai)

## In the next post

That covers the failure modes that ruin a quiet night. Next up: **AI use cases for infra teams**. Not AI as the workload this time, but AI as a tool for your own operations, from AIOps to log analysis and capacity planning.