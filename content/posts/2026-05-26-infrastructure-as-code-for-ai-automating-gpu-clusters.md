---
slug: "infrastructure-as-code-for-ai-automating-gpu-clusters"
translationKey: "infrastructure-as-code-para-ai-automatizando-gpu-clusters"
title: "Infrastructure as Code for AI: automating GPU clusters"
description: "A typo in a VM SKU cost $4,000 in three days. IaC isn't nice-to-have for AI infra. It's survival. Terraform, Bicep, and CI/CD for GPU clusters."
date: 2026-05-26T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - terraform
  - bicep
  - iac
  - aks
  - github-actions
series:
  - "AI for Infrastructure Engineers"
---

Fifth post in the series. In the [previous one](/gpu-deep-dive-what-happens-inside-the-silicon/), we dove inside the GPU. Now let's automate everything around it. Because understanding GPUs is half the battle; provisioning them consistently and at scale is where infrastructure engineering actually meets AI.

## The $4,000 typo

I started the week with a win. Manually provisioned a GPU cluster in East US 2 for an ML experiment: AKS with a `Standard_NC6s_v3` node pool, accelerated networking, NVIDIA drivers, correct taints. Took almost a full day, but it worked.

Three weeks later, the same team needs the identical setup in West US 3. No problem, I thought. Opened the portal, referencing a Slack thread for the SKU, a wiki page for the network config, and my memory for the rest.

Someone fat-fingered the SKU. Instead of `Standard_NC6s_v3` (a GPU VM at ~$3.80/hr), the node pool ended up running `Standard_D16s_v5` — a CPU VM with zero GPUs. The training job launched, couldn't find a CUDA device, fell back to CPU. Nobody noticed for three days because the job didn't fail — it just ran slow. By the time someone checked, the cluster had burned **$4,000** in compute that couldn't even do what it was supposed to.

That was the last time I provisioned AI infra manually.

## Why IaC is non-negotiable for AI

Traditional web application infra is forgiving. A misconfigured App Service costs you an extra $50/month. A misconfigured GPU cluster costs **thousands per day**.

| Reason | Why it matters for AI |
|--------|----------------------|
| **Complexity** | GPU quotas per region, driver versions, taints, InfiniBand, NVMe ephemeral storage, private endpoints. No human can keep all that in their head |
| **Cost** | ND A100 4-nodes = ~$350/day. Every minute of misconfiguration is money burning |
| **Reproducibility** | ML experiments need to be repeatable. Same SKU, driver, network topology |
| **Compliance** | Who changed what, when, why. Git gives you an audit trail for free |

**Infra ↔ AI translation:** When the ML engineer says "I need the same environment from last week," they want infrastructure reproducibility. When compliance asks "what changed," they want an audit trail. IaC answers both with the same artifact: a versioned configuration file.

## The IaC landscape for AI

| Criteria | Terraform | Bicep | Azure CLI | Pulumi |
|----------|-----------|-------|-----------|--------|
| **Paradigm** | Declarative | Declarative | Imperative | Declarative (code) |
| **Multi-cloud** | ✅ | ❌ Azure only | ❌ Azure only | ✅ |
| **State management** | Remote state file | None (ARM manages) | None | Remote state file |
| **Language** | HCL | Bicep DSL | Bash/PowerShell | Python, TS, Go, C# |
| **Learning curve** | Moderate | Low (Azure users) | Low | Moderate-High |
| **Best for** | Multi-cloud platforms | Azure-native teams | Quick automation, glue | Developer-first teams |

**When to use which:** Terraform when you need multi-cloud or platform engineering at scale. Bicep when you're 100% Azure and want the simplest path. Azure CLI for glue, prototyping, and ad-hoc operations. Many teams use more than one: Terraform/Bicep for provisioning, Azure CLI for operations, GitHub Actions to orchestrate it all.

## Terraform for AI infrastructure

### Variables with validation (prevents typos)

```hcl
variable "gpu_vm_size" {
  description = "VM SKU for GPU node pool"
  type        = string
  default     = "Standard_NC6s_v3"

  validation {
    condition     = can(regex("^Standard_N", var.gpu_vm_size))
    error_message = "GPU VM size must be an N-series SKU (e.g., Standard_NC6s_v3, Standard_NC24ads_A100_v4)."
  }
}

variable "gpu_max_nodes" {
  description = "Maximum number of GPU nodes for autoscaling"
  type        = number
  default     = 5
}
```

That `validation` block isn't decorative. It catches exactly the mistake from the opening story. Caught at `terraform plan`, not on the invoice.

### AKS with GPU node pool

```hcl
resource "azurerm_kubernetes_cluster" "ai" {
  name                = "aks-ai-${var.environment}"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  dns_prefix          = "aks-ai-${var.environment}"
  kubernetes_version  = "1.30"

  default_node_pool {
    name            = "system"
    vm_size         = "Standard_D4s_v5"
    node_count      = 2
    os_disk_size_gb = 128

    upgrade_settings {
      max_surge = "33%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    network_policy = "calico"
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.ai.id
  vm_size               = var.gpu_vm_size
  mode                  = "User"
  os_disk_size_gb       = 256
  auto_scaling_enabled  = true
  min_count             = 0
  max_count             = var.gpu_max_nodes

  node_taints = [
    "sku=gpu:NoSchedule"
  ]

  node_labels = {
    "hardware" = "gpu"
    "gpu-type" = "nvidia"
    "workload" = "ai"
  }
}
```

The `sku=gpu:NoSchedule` taint is essential. Without it, Kubernetes schedules monitoring DaemonSets and log collectors on your $3.80/hr GPU nodes.

### Remote state (mandatory)

Never store Terraform state locally for GPU infrastructure. Corrupted or lost state = Terraform can't track or destroy resources that cost real money every hour.

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate"
    container_name       = "tfstate"
    key                  = "ai-platform.terraform.tfstate"
  }
}
```

Storage setup (one-time):

```bash
az group create --name rg-terraform-state --location eastus2

az storage account create \
  --name stterraformstate \
  --resource-group rg-terraform-state \
  --sku Standard_LRS \
  --encryption-services blob

az storage container create \
  --name tfstate \
  --account-name stterraformstate
```

## Bicep for AI infrastructure

Bicep's advantage: no state file, no backend, no locking. ARM manages everything. For teams that are 100% Azure, this removes an entire category of operational complexity.

### GPU VM with NVIDIA Driver Extension

```bicep
@allowed([
  'Standard_NC6s_v3'
  'Standard_NC12s_v3'
  'Standard_NC24ads_A100_v4'
  'Standard_NC48ads_A100_v4'
  'Standard_NC96ads_A100_v4'
])
@description('GPU VM size — must be an N-series SKU')
param vmSize string = 'Standard_NC6s_v3'

param vmName string = 'vm-gpu-ai'
param location string = resourceGroup().location
param adminUsername string = 'azureuser'

@secure()
param sshPublicKey string

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [{
            path: '/home/${adminUsername}/.ssh/authorized_keys'
            keyData: sshPublicKey
          }]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'Premium_LRS' }
        diskSizeGB: 256
      }
    }
    networkProfile: {
      networkInterfaces: [{ id: nic.id }]
    }
  }
}

resource nvidiaExtension 'Microsoft.Compute/virtualMachines/extensions@2024-07-01' = {
  parent: vm
  name: 'NvidiaGpuDriverLinux'
  location: location
  properties: {
    publisher: 'Microsoft.HpcCompute'
    type: 'NvidiaGpuDriverLinux'
    typeHandlerVersion: '1.9'
    autoUpgradeMinorVersion: true
  }
}
```

The `@allowed` decorator serves the same purpose as Terraform's `validation`: it prevents non-GPU SKUs from ever making it into a deployment.

### Modular structure for production

```
infra/
├── main.bicep              # Orchestrator
├── modules/
│   ├── network.bicep       # VNet, subnets, NSGs, private endpoints
│   ├── aks.bicep           # AKS cluster with GPU node pool
│   ├── storage.bicep       # Storage account for models and data
│   ├── monitoring.bicep    # Log Analytics, alerts, dashboards
│   └── keyvault.bicep      # Key Vault for secrets
└── parameters/
    ├── dev.bicepparam
    ├── staging.bicepparam
    └── prod.bicepparam
```

A new team spins up a complete, compliant environment by creating a single parameter file.

## CI/CD: plan → approve → apply

AI infrastructure changes should never be applied from a laptop. The pipeline provides review gates, automated validation, and an audit trail.

### GitHub Actions with OIDC

```yaml
name: "AI Infrastructure — Plan & Apply"

on:
  push:
    branches: [main]
    paths: ["infra/**"]
  pull_request:
    branches: [main]
    paths: ["infra/**"]

permissions:
  id-token: write
  contents: read
  pull-requests: write

env:
  ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  ARM_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

jobs:
  plan:
    name: "Terraform Plan"
    runs-on: ubuntu-latest
    environment: ai-infrastructure
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: terraform init
        working-directory: infra
      - run: terraform plan -out=tfplan -input=false
        working-directory: infra

  apply:
    name: "Terraform Apply"
    runs-on: ubuntu-latest
    needs: plan
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment:
      name: ai-infrastructure-prod
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: terraform init
        working-directory: infra
      - run: terraform apply -auto-approve tfplan
        working-directory: infra
```

The flow: PR = `plan` only (shows what will change). Merge to main = `apply` with environment protection rule (reviewer must approve). The plan artifact is what executes — no drift between review and execution.

**Always pin action versions.** `@v4`, `@v3`, `@v2`. Using `@latest` in production pipelines means an upstream breaking change can take down your deploy when you need it most.

## Governance: guardrails for GPUs

Azure Policy can enforce rules at the subscription level. For AI infra, the highest-impact policy: block provisioning of GPU VMs without a `cost-center` tag:

```json
{
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        {
          "field": "type",
          "equals": "Microsoft.Compute/virtualMachines"
        },
        {
          "field": "Microsoft.Compute/virtualMachines/sku.name",
          "in": [
            "Standard_NC24ads_A100_v4",
            "Standard_NC48ads_A100_v4",
            "Standard_ND96asr_v4"
          ]
        },
        {
          "field": "tags['cost-center']",
          "exists": "false"
        }
      ]
    },
    "then": {
      "effect": "deny"
    }
  }
}
```

No cost-center tag = no GPU. Simple and effective.

## In the next post

Now that infrastructure is automated and governed, we'll cover the model lifecycle: **MLOps**. How a model goes from "works on my notebook" to "running in production with an SLA." What changes for infra engineers, and what the ML team expects from you in the process.
