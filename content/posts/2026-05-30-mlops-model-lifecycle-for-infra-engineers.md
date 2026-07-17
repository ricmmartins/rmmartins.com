---
slug: "mlops-model-lifecycle-for-infra-engineers"
aliases:
  - "/2026/05/30/mlops-model-lifecycle-for-infra-engineers/"
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

Sixth post in the series. In the [previous one](/2026/05/26/infrastructure-as-code-for-ai-automating-gpu-clusters/), we automated GPU cluster provisioning. Next comes what happens **after** the hardware is ready: how a model goes from "works on my notebook" to "running in production with an SLA."

**tl;dr**

- Models need the same artifact, promotion, and rollback discipline as application builds.
- Use a real registry with metadata and controlled deployments.
- Prefer MLflow aliases over deprecated stages when describing promotions.

## The model with no birth certificate

A data scientist drops a message in the team channel with a link to a shared drive: *"Here's the model. It's a 15 GB PyTorch checkpoint. We need it in production by Friday."*

You open the folder and find a single file: `model_final_v2_FIXED.pt`.

You start asking questions. Which version? Trained on what data? Rollback plan if predictions go wrong? Latency and throughput SLAs? Framework and CUDA version? The answers are vague. *"It's the latest one. Works on my machine. Just put it behind an API."*

You've seen this movie before, just with different actors. Developers used to hand you a compiled binary and say "deploy this." That chaos gave us container registries, CI/CD pipelines, semantic versioning, and automated rollback. Models are no different. They are artifacts: large, versioned, and environment-dependent. They need the same lifecycle management.

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

# View the job that registered this model
az ml model show \
  --name sentiment-classifier \
  --version 3 \
  --resource-group ml-prod-rg \
  --workspace-name ml-prod-ws \
  --query "{job_name:job_name, created_at:creation_context.created_at}" \
  --output json
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

# Point the production alias to version 3
mlflow models set-alias \
  -n sentiment-classifier \
  -v 3 \
  -a production
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
| **Versioning** | Built-in, immutable | Built-in with aliases | Image tags |
| **Lineage tracking** | Deep (jobs, data, env) | Run-level | Dockerfile only |
| **Infra overhead** | Managed | Self-hosted or Azure ML | Managed (ACR) |
| **When to avoid** | Need multi-cloud | Need deep Azure integration | Models without containers |

> **Watch out:** Never use shared file systems or blob storage as a "registry." Without immutable versions and metadata APIs, you end up with `model_final_v2_FIXED_actually_final.pt`.

## CI/CD for models: the promotion pipeline

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 320" role="img" aria-labelledby="mlops-pipeline-title mlops-pipeline-desc">
<title id="mlops-pipeline-title">Model promotion pipeline</title>
<desc id="mlops-pipeline-desc">Diagram showing DEV, STAGING and PRODUCTION stages with responsibilities and infrastructure for each stage.</desc>
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#666666" />
</marker>
</defs>
<style>
.title { font-family:"Segoe UI", Arial, sans-serif; font-size:14px; font-weight:bold; fill:#222; }
.label { font-family:"Segoe UI", Arial, sans-serif; font-size:12px; font-weight:bold; fill:#222; }
.desc { font-family:"Segoe UI", Arial, sans-serif; font-size:10px; fill:#555; }
.primary { fill:#dae8fc; stroke:#6c8ebf; stroke-width:1.5; }
.success { fill:#d5e8d4; stroke:#82b366; stroke-width:1.5; }
.warning { fill:#fff2cc; stroke:#d6b656; stroke-width:1.5; }
.neutral { fill:#f5f5f5; stroke:#666666; stroke-width:1.5; }
.arrow { stroke:#666666; stroke-width:1.5; fill:none; marker-end:url(#arrow); }
.link { stroke:#666666; stroke-width:1.5; fill:none; }
</style>
<g>
<rect class="primary" x="40" y="30" width="240" height="118" rx="8" />
<text class="title" x="160" y="70.5" text-anchor="middle">DEV</text>
<text class="label" x="160" y="85.5" text-anchor="middle">Train</text>
<text class="label" x="160" y="100.5" text-anchor="middle">Track</text>
<text class="label" x="160" y="115.5" text-anchor="middle">Version</text>
<line class="link" x1="160" y1="154" x2="160" y2="196" />
<rect class="neutral" x="40" y="190" width="240" height="98" rx="6" />
<text class="label" x="160" y="220.5" text-anchor="middle">Infra</text>
<text class="desc" x="160" y="235.5" text-anchor="middle">GPU Compute</text>
<text class="desc" x="160" y="250.5" text-anchor="middle">Blob Storage</text>
<text class="desc" x="160" y="265.5" text-anchor="middle">Experiment Tracking</text>
</g>
<g>
<path class="arrow" d="M 286 89 L 376 89" />
<rect class="warning" x="370" y="30" width="240" height="118" rx="8" />
<text class="title" x="490" y="70.5" text-anchor="middle">STAGING</text>
<text class="label" x="490" y="85.5" text-anchor="middle">Validate</text>
<text class="label" x="490" y="100.5" text-anchor="middle">Benchmark</text>
<text class="label" x="490" y="115.5" text-anchor="middle">Security</text>
<line class="link" x1="490" y1="154" x2="490" y2="196" />
<rect class="neutral" x="370" y="190" width="240" height="98" rx="6" />
<text class="label" x="490" y="220.5" text-anchor="middle">Infra</text>
<text class="desc" x="490" y="235.5" text-anchor="middle">Inference Infra</text>
<text class="desc" x="490" y="250.5" text-anchor="middle">Test Data Access</text>
<text class="desc" x="490" y="265.5" text-anchor="middle">Isolated Network</text>
</g>
<g>
<path class="arrow" d="M 616 89 L 706 89" />
<rect class="success" x="700" y="30" width="240" height="118" rx="8" />
<text class="title" x="820" y="70.5" text-anchor="middle">PRODUCTION</text>
<text class="label" x="820" y="85.5" text-anchor="middle">Serve</text>
<text class="label" x="820" y="100.5" text-anchor="middle">Monitor</text>
<text class="label" x="820" y="115.5" text-anchor="middle">Auto-rollback</text>
<line class="link" x1="820" y1="154" x2="820" y2="196" />
<rect class="neutral" x="700" y="190" width="240" height="98" rx="6" />
<text class="label" x="820" y="213" text-anchor="middle">Infra</text>
<text class="desc" x="820" y="228" text-anchor="middle">Load Balanced</text>
<text class="desc" x="820" y="243" text-anchor="middle">Multi-replica</text>
<text class="desc" x="820" y="258" text-anchor="middle">Prod Network</text>
<text class="desc" x="820" y="273" text-anchor="middle">SLA-bound</text>
</g>
</svg>

### Validation gates between stages

| Gate | What it checks | Infra required |
|------|---------------|----------------|
| **Accuracy threshold** | Metrics ≥ baseline (e.g., F1 > 0.92) | Storage for test dataset, compute for evaluation |
| **Latency benchmark** | P95 ≤ SLA (e.g., < 200ms) | Load testing infra |
| **Throughput test** | Requests/sec ≥ target under load | Load generator (k6, Locust) |
| **Security scan** | No vulnerable deps, signed artifact | Container scanning (Defender) |
| **Cost estimate** | Projected cost within budget | Cost modeling based on SKU |

### GitHub Actions workflow for model deployment

Azure ML online deployments are YAML-driven, so the workflow below assumes the deployment specs live in the repo and the pipeline only swaps in the model version and instance sizing.

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
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Deploy to staging endpoint
        run: |
          az ml online-deployment create \
            --file deployments/staging.yml \
            --name staging-${{ inputs.model_version }} \
            --endpoint-name sentiment-staging \
            --set model=azureml:${{ inputs.model_name }}:${{ inputs.model_version }} \
                  instance_type=Standard_NC4as_T4_v3 \
                  instance_count=1 \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Deploy canary (10% traffic)
        run: |
          az ml online-deployment create \
            --file deployments/production.yml \
            --name prod-${{ inputs.model_version }} \
            --endpoint-name sentiment-prod \
            --set model=azureml:${{ inputs.model_name }}:${{ inputs.model_version }} \
                  instance_type=Standard_NC4as_T4_v3 \
                  instance_count=2 \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}

          az ml online-endpoint update \
            --name sentiment-prod \
            --traffic "prod-stable=90 prod-${{ inputs.model_version }}=10" \
            --resource-group ${{ env.AZURE_RG }} \
            --workspace-name ${{ env.AZURE_ML_WS }}
```

**Infra ↔ AI translation:** This is the same blue/green habit you already use for app releases, except the thing you shift is model traffic. The `--traffic` flag does weighted routing while the old deployment keeps serving.

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

## Closing the loop

The `model_final_v2_FIXED.pt` story stops being chaos once the file enters a registry, gets metadata, and moves through controlled promotion gates. That is the real point of MLOps for infrastructure engineers.

## Further reading

- [Register and work with models in Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models?view=azureml-api-2)
- [Deploy machine learning models to online endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-online-endpoints?view=azureml-api-2)
- [Safe rollout for online endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-safely-rollout-online-endpoints?view=azureml-api-2)

## In the next post

Models are deployed and serving traffic. The next post covers **monitoring and observability for AI**, including model drift, GPU metrics, and how to detect degradation before users notice.