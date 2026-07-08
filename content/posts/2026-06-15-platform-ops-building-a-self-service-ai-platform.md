---
slug: "platform-ops-building-a-self-service-ai-platform"
aliases:
  - "/2026/06/15/platform-ops-building-a-self-service-ai-platform/"
translationKey: "platform-ops-construindo-uma-plataforma-ai-self-service"
title: "Platform ops: building a self-service AI platform"
description: "You've become the bottleneck. Multi-tenancy, GPU scheduling, Kueue, quotas, priority classes, and how to stop being a help desk and become a platform engineer."
date: 2026-06-15T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - platform-engineering
  - kubernetes
  - kueue
  - multi-tenancy
  - gpu-scheduling
series:
  - "AI for Infrastructure Engineers"
---

Tenth post in the series. In the [previous one](/2026/06/11/cost-engineering-for-ai-when-idle-gpus-cost-more-than-your-car/), we controlled costs with Spot VMs, right-sizing, and FinOps. Now for the next problem: how to stop being a human help desk for GPU access.

## The Slack channel that ate your calendar

Six months ago, you provisioned a single GPU VM for the ML team. Configured drivers, mounted storage, closed the ticket. Felt like any other infrastructure request.

Today, you have four teams, three AKS clusters, dozens of GPU node pools, and a growing collection of Azure OpenAI endpoints. Each team wants their own resources, their own quotas, and their own SLAs. Your DMs have turned into a help desk: "Can we get more GPUs?" "Why is my training job Pending?" "Who's using all the A100s?"

This is the inflection point. You're no longer "supporting AI projects." You are the bottleneck of an AI platform. The fix isn't working harder. It's building the systems, policies, and automation that let teams self-serve without turning the place into chaos.

## From AI project to AI platform

Platform engineering isn't new. You've been doing it for years with web apps, databases, and CI/CD. It means reusable, self-service infrastructure that teams can consume without filing tickets. Golden paths. Opinionated workflows that are tested end to end.

AI infra follows the same principle. Instead of provisioning GPU VMs ad hoc, you build templates. Instead of creating namespaces manually, you offer a self-service portal. Instead of answering "how do I deploy a model?", you offer a pipeline that does it.

**Infra ↔ AI translation:** Platform engineering is the same discipline you already know, now applied to GPU compute, model registries, and inference endpoints instead of web apps and SQL databases. The abstraction layers change; the reasoning doesn't.

## What to automate vs. what to gate

| Category | Self-service | Requires approval |
|----------|:---:|:---:|
| Dev/test namespaces | ✅ | |
| Small GPU allocations (1-2 GPUs) | ✅ | |
| Production inference endpoints | | ✅ |
| Large training jobs (8+ GPUs) | | ✅ |
| New cluster provisioning | | ✅ |
| Jupyter notebook environments | ✅ | |
| Azure OpenAI endpoint creation | | ✅ |
| Storage volumes for datasets | ✅ | |

**Rule:** If a mistake costs less than a few hundred dollars and can be reverted in minutes, make it self-service. If it involves expensive resources, production traffic, or cross-team impact, put a gate on it.

## Multi-tenancy: isolation vs. efficiency

| Isolation level | Cost efficiency | Security boundary | Operational overhead | Best for |
|----------------|----------------|-------------------|---------------------|----------|
| **Namespace** | ⭐⭐⭐⭐⭐ | Low | Low | Trusted teams sharing a cluster |
| **Node pool** | ⭐⭐⭐⭐ | Medium | Medium | Teams needing dedicated GPU types |
| **Cluster** | ⭐⭐⭐ | High | High | Teams with different compliance requirements |
| **Subscription** | ⭐⭐ | Very high | Very high | Regulated workloads, separate billing |

Most organizations land on a hybrid: one or two shared clusters with per-team namespaces and dedicated GPU node pools, plus separate clusters for production inference and regulated workloads.

### RBAC scoping by namespace

```yaml
# team-data-science-role.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: team-data-science
  name: gpu-workload-role
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps", "persistentvolumeclaims"]
    verbs: ["get", "list", "create", "delete", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "create", "update", "delete"]
```

Bind this role to the team's Entra ID group. They deploy workloads in their namespace, but can't touch other teams' resources or cluster-level objects.

### Resource quotas (without this, one team eats all the GPUs)

```yaml
# team-data-science-quota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  namespace: team-data-science
  name: gpu-quota
spec:
  hard:
    requests.cpu: "64"
    requests.memory: 256Gi
    requests.nvidia.com/gpu: "8"
    limits.cpu: "128"
    limits.memory: 512Gi
    limits.nvidia.com/gpu: "8"
    pods: "50"
```

This limits the team to 8 GPUs, 64 CPU cores, and 256 GiB of memory. They can distribute across pods however they want (one job with 8 GPUs or eight jobs with 1 GPU each), but can't exceed the total.

> **Watch out:** ResourceQuotas only enforce at scheduling time. If you lower a quota below current usage, existing pods aren't evicted. New pods will be rejected. Plan quota changes during maintenance windows.

### Network isolation between namespaces

```yaml
# deny-cross-namespace.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  namespace: team-data-science
  name: deny-other-namespaces
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector: {}
```

Pods within the namespace talk to each other; traffic from other namespaces is blocked. Add explicit rules for shared services (model registries, monitoring).

## GPU scheduling and queues

### The fundamental problem

GPU is finite and expensive. A single A100 node can run about $10/hour on Azure. With 20 nodes and 4 teams, first-come-first-served scheduling creates friction fast. Training jobs monopolize GPUs for hours. Inference gets starved. Scientists submit 10 jobs at once and wonder why only 2 are running.

### Priority classes

```yaml
# priority-classes.yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: production-inference
value: 1000000
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: "Production inference - never preempted by training."
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: scheduled-training
value: 100000
globalDefault: false
preemptionPolicy: PreemptLowerPriority
description: "Training jobs with deadlines."
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: exploratory
value: 1000
globalDefault: true
preemptionPolicy: Never
description: "Notebooks, experiments - can be preempted."
```

With this hierarchy: production inference preempts training if GPUs are scarce. Training preempts exploratory notebooks. But exploratory workloads never preempt anything; they wait in line.

> **Tip:** Use `preemptionPolicy: Never` for exploratory workloads. This prevents a stampede where 50 notebook pods try to preempt each other.

### Kueue: fair scheduling for batch AI

Native Kubernetes doesn't understand job queuing. If you submit 100 jobs and have capacity for 10, Kubernetes creates 100 pending pods. Kueue adds a queue layer that admits jobs based on available capacity and fair-share.

```yaml
# cluster-queue.yaml
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: gpu-cluster-queue
spec:
  namespaceSelector: {}
  resourceGroups:
    - coveredResources: ["cpu", "memory", "nvidia.com/gpu"]
      flavors:
        - name: a100-spot
          resources:
            - name: "cpu"
              nominalQuota: 128
            - name: "memory"
              nominalQuota: 512Gi
            - name: "nvidia.com/gpu"
              nominalQuota: 16
        - name: a100-ondemand
          resources:
            - name: "cpu"
              nominalQuota: 64
            - name: "memory"
              nominalQuota: 256Gi
            - name: "nvidia.com/gpu"
              nominalQuota: 8
  preemption:
    withinClusterQueue: LowerPriority
---
# local-queue.yaml
apiVersion: kueue.x-k8s.io/v1beta1
kind: LocalQueue
metadata:
  namespace: team-nlp
  name: team-nlp-queue
spec:
  clusterQueue: gpu-cluster-queue
```

Teams submit jobs to their LocalQueue; the ClusterQueue enforces global capacity. Jobs stay queued (not scheduled) until there's space. Eliminates the "100 pending pods" problem.

### Volcano: gang scheduling for distributed training

Distributed training needs multiple GPUs across multiple nodes starting simultaneously. Default Kubernetes scheduling may place 3 of 4 required pods, leaving all of them waiting for the fourth.

Volcano guarantees: all pods in a job start together, or none start.

```yaml
# distributed-training-volcano.yaml
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: distributed-llm-training
  namespace: team-nlp
spec:
  minAvailable: 4
  schedulerName: volcano
  tasks:
    - replicas: 4
      name: worker
      template:
        spec:
          containers:
            - name: trainer
              image: myregistry.azurecr.io/llm-trainer:v1.0
              resources:
                requests:
                  nvidia.com/gpu: "4"
                limits:
                  nvidia.com/gpu: "4"
          restartPolicy: OnFailure
```

`minAvailable: 4` tells Volcano: don't schedule any worker unless you can schedule all four. This prevents partial allocation, the most common source of wasted GPU-hours in distributed training.

> **GPU requests = limits, always.** Unlike CPU and memory, GPUs cannot be overcommitted. A pod requesting 1 GPU will exclusively own that GPU regardless of the limit value. Different values only cause confusion.

## Quota and capacity management

### The quota stack

| Layer | Mechanism | Who manages |
|-------|-----------|-------------|
| Azure subscription | Regional vCPU quotas | Cloud admin (portal or support request) |
| AKS cluster | Node pool scaling limits | Platform team |
| Kubernetes namespace | ResourceQuota objects | Platform team |
| Kueue | ClusterQueue nominal quotas | Platform team |
| Team-level | LocalQueue admission | Self-service within limits |

### Capacity reservation for production

```bash
# Reserve guaranteed capacity for inference
az capacity reservation group create \
  --resource-group rg-ai-platform \
  --name crg-inference-prod \
  --location eastus

az capacity reservation create \
  --resource-group rg-ai-platform \
  --capacity-reservation-group crg-inference-prod \
  --name cr-a100-inference \
  --sku Standard_NC24ads_A100_v4 \
  --capacity 4
```

You pay for reserved capacity whether you're using it or not, but it guarantees the VMs exist when you need them. For production inference serving real-time traffic, this tradeoff is almost always worth it.

### Quota monitoring

```bash
# Check N-series quota usage in the region
az vm list-usage \
  --location eastus \
  --query "[?contains(name.value, 'standardN')].{Family:localName, Used:currentValue, Limit:limit}" \
  --output table
```

## In the next post

Once the platform is self-service, the next failure mode moves up the stack. Next, we dive into **Azure OpenAI in production**: deployments, rate limiting, multi-region failover, content filtering, and production-readiness patterns.