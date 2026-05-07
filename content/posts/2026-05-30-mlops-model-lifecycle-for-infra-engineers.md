---
slug: "mlops-model-lifecycle-for-infra-engineers"
translationKey: "mlops-ciclo-de-vida-do-modelo-pra-quem-e-de-infra"
title: "MLOps: model lifecycle for infra engineers"
description: "A data scientist sends you model_final_v2_FIXED.pt and says 'put it in production'. Sound familiar? MLOps is the same CI/CD you already know, applied to ML models."
date: 2026-05-30T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - mlops
  - azure-ml
  - mlflow
  - cicd
  - github-actions
series:
  - "AI for Infrastructure Engineers"
---

Sixth post in the series. In the [previous one](/infrastructure-as-code-for-ai-automating-gpu-clusters/), we automated GPU cluster provisioning. Now let's talk about what happens **after** the hardware is ready: how a model goes from "works on my notebook" to "running in production with an SLA."

## The model with no birth certificate

A data scientist drops a message in the team channel with a link to a shared drive: *"Here's the model. It's a 15 GB PyTorch checkpoint. We need it in production by Friday."*

You open the folder and find a single file: `model_final_v2_FIXED.pt`.

You start asking questions. Which version? Trained on what data? Rollback plan if predictions go wrong? Latency and throughput SLAs? Framework and CUDA version? The answers are vague. *"It's the latest one. Works on my machine. Just put it behind an API."*

You've seen this movie before — just with different actors. Developers used to hand you a compiled binary and say "deploy this." That chaos drove the industry to build container registries, CI/CD pipelines, semantic versioning, and automated rollback. Models are no different. They're artifacts: large, versioned, environment-dependent. They deserve the same lifecycle management.

## Models are artifacts: treat them like it

If you've ever pulled an image from a container registry, tagged a release in Git, or promoted a build from staging to production, you already understand the core concepts of model lifecycle.

| Infra Concept | ML Equivalent |
|---------------|---------------|
| Container image | Model checkpoint (weights file) |
| Container registry (ACR) | Model registry (Azure ML, MLflow) |
| CI build | Training run |
| CD release pipeline | Model deployment pipeline |
| Dockerfile (build manifest) | Training config (hyperparameters, data version, framework version) |
| Artifact signature | Model provenance and lineage |
| Blue/green deployment | A/B testing with traffic splitting |

A model file without metadata is like a container image without a tag. You can deploy it, but you can't reproduce, audit, or safely roll it back.

## Model registries

The registry is the single source of truth for the organization's models. It stores artifacts with metadata: version, training metrics, lineage, and deployment status.

### Azure Machine Learning Model Registry

```bash
# Register model from local file
az ml model create \
  --name sentiment-classifier \
  --version 3 \
  --path ./outputs/model.pt \
  --type custom_model \
  --tags task=sentiment framework=pytorch \
  --resource-group ml-prod-rg \
  --workspace-name ml-prod-ws

# List model versions
az ml model list \
  --name sentiment-classifier \
  --resource-group ml-prod-rg \
  --workspace-name ml-prod-ws \
  --output table

# View lineage: which run produced this model
az ml model show \
  --name sentiment-classifier \
  --version 3 \
  --resource-group ml-prod-rg \
  --workspace-name ml-prod-ws \
  --query "jobs"
```

### MLflow (open-source, multi-framework)

MLflow is the open-source standard for experiment tracking and model management. Framework-agnostic, it wraps PyTorch, TensorFlow, and scikit-learn. Azure ML integrates natively with MLflow.

```bash
# Local MLflow server (dev/test)
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlruns \
  --host 0.0.0.0 --port 5000

# Register model via CLI
mlflow models register \
  --model-uri runs:/<run-id>/model \
  --name sentiment-classifier

# Promote to production
mlflow models transition-stage \
  --name sentiment-classifier \
  --version 3 \
  --stage Production
```

### Container Registry for model serving

When models are served via containers (Triton, TorchServe, FastAPI wrapper), the image becomes the deployable artifact:

```bash
# Build and push the serving container
az acr build \
  --registry mlmodelsacr \
  --image sentiment-classifier:v3 \
  --file Dockerfile.serve .

# Verify image
az acr repository show-tags \
  --name mlmodelsacr \
  --repository sentiment-classifier \
  --output table
```

### Which registry to use?

| Criteria | Azure ML Registry | MLflow Registry | ACR (Container) |
|----------|-------------------|-----------------|-----------------|
| **Best for** | Azure-native teams | Multi-cloud / OSS | Containerized serving |
| **Versioning** | Built-in, immutable | Built-in with stages | Image tags |
| **Lineage tracking** | Deep (jobs, data, env) | Run-level | Dockerfile only |
| **Infra overhead** | Managed | Self-hosted or Azure ML | Managed (ACR) |
| **When to avoid** | Need multi-cloud | Need deep Azure integration | Models without containers |

> **Watch out:** Never use shared file systems or blob storage as a "registry." Without immutable versions and metadata APIs, you end up with `model_final_v2_FIXED_actually_final.pt`.

## CI/CD for models: the promotion pipeline

```
┌─────────┐     ┌─────────────┐     ┌──────────────┐
│   DEV   │────▶│   STAGING   │────▶│  PRODUCTION  │
│         │     │             │     │              │
│ Train   │     │ Validate    │     │ Serve        │
│ Track   │     │ Benchmark   │     │ Monitor      │
│ Version │     │ Security    │     │ Auto-rollback│
└─────────┘     └─────────────┘     └──────────────┘
     │               │                    │
  GPU Compute    Inference Infra      Load Balanced
  Blob Storage   Test Data Access     Multi-replica
  Experiment     Isolated Network     Prod Network
  Tracking                            SLA-bound
```

### Validation gates between stages

| Gate | What it checks | Infra required |
|------|---------------|----------------|
| **Accuracy threshold** | Metrics ≥ baseline (e.g., F1 > 0.92) | Storage for test dataset, compute for evaluation |
| **Latency benchmark** | P95 ≤ SLA (e.g., < 200ms) | Load testing infra |
| **Throughput test** | Requests/sec ≥ target under load | Load generator (k6, Locust) |
| **Security scan** | No vulnerable deps, signed artifact | Container scanning (Defender) |
| **Cost estimate** | Projected cost within budget | Cost modeling based on SKU |

### GitHub Actions workflow for model deployment

```yaml
name: Model Deployment Pipeline

on:
  workflow_dispatch:
    inputs:
      model_name:
        description: 'Model name in registry'
        required: true
      model_version:
        description: 'Model version to deploy'
        required: true

env:
  AZURE_RG: ml-prod-rg
  AZURE_ML_WS: ml-prod-ws

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Download model from registry
        run: |
          az ml model download \
            --name ${{ inputs.model_name }} \
            --version ${{ inputs.model_version }} \
            --download-path ./model \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}
      - name: Run accuracy validation
        run: |
          python scripts/validate_model.py \
            --model-path ./model \
            --test-data ./data/holdout.csv \
            --min-accuracy 0.92

  deploy-staging:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging endpoint
        run: |
          az ml online-deployment create \
            --name staging-${{ inputs.model_version }} \
            --endpoint-name sentiment-staging \
            --model azureml:${{ inputs.model_name }}:${{ inputs.model_version }} \
            --instance-type Standard_NC4as_T4_v3 \
            --instance-count 1 \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy canary (10% traffic)
        run: |
          az ml online-deployment create \
            --name prod-${{ inputs.model_version }} \
            --endpoint-name sentiment-prod \
            --model azureml:${{ inputs.model_name }}:${{ inputs.model_version }} \
            --instance-type Standard_NC4as_T4_v3 \
            --instance-count 2 \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}

          az ml online-endpoint update \
            --name sentiment-prod \
            --traffic "prod-stable=90 prod-${{ inputs.model_version }}=10" \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}
```

**Infra ↔ AI translation:** This is your blue/green pipeline, but for model weights instead of container images. The `--traffic` flag works exactly like weighted routing in Azure Front Door: you shift a percentage of requests to the new model while the old one keeps serving.

## Your responsibilities at each stage

As an infrastructure engineer, your ownership spans the entire pipeline:

- **Compute provisioning**: GPU node pools for training (Dev), inference VMs for validation (Staging), GPU clusters with autoscaling for serving (Prod)
- **Networking**: Isolated VNets for staging, private endpoints for the model registry, load balancer for traffic splitting
- **Storage**: High-throughput blob for training data, low-latency for model artifacts, retention policies for old versions
- **Secrets management**: Key Vault for API keys, managed identity for pipeline auth, RBAC for the model registry
- **Monitoring**: Deployment health dashboards, latency alerting, automated rollback triggers

## Traffic splitting: canary and blue/green for models

Deploying a model isn't a binary event. You shift traffic gradually:

| Pattern | How it works | When to use |
|---------|-------------|-------------|
| **Canary** | 5-10% of traffic goes to the new model, increase gradually | Default for most deployments |
| **Blue/Green** | Full parallel environment, instant switch | When you need instant rollback |
| **Shadow** | New model receives real traffic but responses are discarded | When you want to test without impacting users |

```bash
# Promote canary to 100% after validation
az ml online-endpoint update \
  --name sentiment-prod \
  --traffic "prod-v3=100" \
  --resource-group ml-prod-rg \
  --workspace-name ml-prod-ws
```

## In the next post

Now that models are deployed and serving traffic, how do you know they're healthy? Next up: **monitoring and observability for AI**, including model drift, GPU metrics, and how to detect degradation before users notice.
