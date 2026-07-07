---
slug: "monitoring-and-observability-for-ai"
translationKey: "monitoramento-e-observabilidade-para-ai"
title: "Monitoring and observability for AI: when the green dashboard lies"
description: "Healthy infra doesn't mean a working model. Model drift, GPU metrics, Azure OpenAI throttling, and the 6 dimensions of observability you need to cover."
date: 2026-06-03T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - infrastructure
  - azure
  - monitoring
  - prometheus
  - grafana
  - opentelemetry
  - azure-openai
series:
  - "AI for Infrastructure Engineers"
---

Seventh post in the series. In the [previous one](/2026/05/30/mlops-model-lifecycle-for-infra-engineers/), we put models into production with CI/CD pipelines. Now: how do you know they're actually healthy?

## The silent failure

Your Azure OpenAI endpoint returns 200 OK on every request. Latency is normal, P95 under 800ms. CPU and memory within thresholds. Kubernetes shows healthy pods, no restarts. By every infra metric you trust, the system is perfect.

But the support tickets keep coming. Users report the chatbot "gives worse answers." Fluent but factually incorrect responses. Hallucinations are up, summarizations miss key points, code suggestions introduce subtle bugs.

You open the monitoring stack. Azure Monitor: green. Application Insights: green. Grafana: green. Every dashboard says "healthy" while the users are telling you the opposite.

The problem? **Model drift**. A recent fine-tuning introduced a quality regression. Outputs degraded gradually over two weeks, but no alert fired because you're monitoring **infrastructure** metrics, not **AI** metrics. Your observability stack was built for traditional workloads where "the server is up and responding" = "the system is working." In AI, a model can be running perfectly and still be **wrong**.

## The 6 dimensions of AI observability

Traditional monitoring covers compute, network, and storage. Necessary but insufficient for AI.

| # | Dimension | What to monitor | Priority |
|---|-----------|----------------|----------|
| 1 | **Compute (GPU)** | Utilization, memory, temperature, ECC errors | P0 |
| 2 | **Cost** | GPU spend, tokens consumed, cost per inference | P0 |
| 3 | **Model** | Accuracy, drift, latency, error rates | P1 |
| 4 | **Security** | Prompt injection, data exfiltration, anomalous consumption | P1 |
| 5 | **Network** | InfiniBand health, cross-node latency, throughput | P2 |
| 6 | **Data** | Pipeline freshness, quality, ingestion failures | P2 |

**Infra ↔ AI translation:** Monitoring a web server means tracking CPU, memory, disk, and network. Monitoring an AI workload means doing that and watching output quality, spend, and abuse patterns at the same time. The model doesn't just consume resources. It can be wrong while every host metric looks fine.

## GPU monitoring: the foundation

### DCGM Exporter on AKS

NVIDIA DCGM Exporter runs as a DaemonSet (one pod per GPU node) and exposes metrics in Prometheus format:

```bash
# Add NVIDIA Helm repo
helm repo add nvidia https://nvidia.github.io/dcgm-exporter/helm-charts
helm repo update

# Install DCGM Exporter as DaemonSet on GPU nodes
helm install dcgm-exporter nvidia/dcgm-exporter \
  --namespace gpu-monitoring \
  --create-namespace \
  --set nodeSelector."agentpool"="gpu"
```

### Azure Managed Prometheus

This gives you the managed backend. It does not scrape every custom exporter you install.

```bash
# Enable Azure Monitor managed Prometheus
az aks update \
  --resource-group myResourceGroup \
  --name myAKSCluster \
  --enable-azure-monitor-metrics

# Verify it's enabled
az aks show \
  --resource-group myResourceGroup \
  --name myAKSCluster \
  --query "azureMonitorProfile.metrics.enabled"
```

For custom exporters such as DCGM, add a `PodMonitor` or `ServiceMonitor` so Azure Monitor knows what to scrape:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: dcgm-exporter
  namespace: gpu-monitoring
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: dcgm-exporter
  podMetricsEndpoints:
    - port: metrics
      path: /metrics
      interval: 30s
```

Adjust the selector to match the labels your Helm release actually uses.

### GPU metrics and alert thresholds

| Metric | DCGM Name | Warning | Critical | Meaning |
|--------|-----------|---------|----------|---------|
| GPU Utilization | `DCGM_FI_DEV_GPU_UTIL` | < 30% sustained | < 10% sustained | Wasted spend |
| GPU Memory Used | `DCGM_FI_DEV_FB_USED` | > 85% | > 95% | OOM risk |
| GPU Temperature | `DCGM_FI_DEV_GPU_TEMP` | > 78°C | > 83°C | Thermal throttling |
| ECC Errors | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL` | > 0 | > 0 | Degrading hardware |

> **Nuance:** Low GPU utilization isn't always a problem. Latency-sensitive inference workloads intentionally keep utilization low to maintain fast responses. Check whether the workload optimizes for throughput (training: high utilization expected) or latency (inference: moderate is OK).

## Azure OpenAI monitoring

### Key metrics

| Metric | What it is | When to investigate |
|--------|-----------|---------------------|
| **TPM** (Tokens Per Minute) | Throughput against allocated capacity | > 80% sustained of limit |
| **RPM** (Requests Per Minute) | Individual calls regardless of tokens | Many small requests saturating before TPM |
| **TTFT** (Time to First Token) | Perceived latency for streaming | > 2 seconds (feels slow to the user) |
| **HTTP 429 Rate** | Throttling signal | > 1% sustained |

**Infra ↔ AI translation:** TPM limits are like bandwidth throttling. RPM limits are like connection-rate limiting. Token budgets are the AI equivalent of data transfer quotas.

### Enable diagnostic logging

```bash
az monitor diagnostic-settings create \
  --resource "/subscriptions/<sub-id>/resourceGroups/myRG/providers/Microsoft.CognitiveServices/accounts/myAOAI" \
  --name "aoai-diagnostics" \
  --workspace "/subscriptions/<sub-id>/resourceGroups/myRG/providers/Microsoft.OperationalInsights/workspaces/myWorkspace" \
  --logs '[{"category":"RequestResponse","enabled":true},{"category":"Audit","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'
```

> **Watch the volume:** A deployment processing 1,000 RPM generates ~1.4 million log entries per day. Configure retention policies in Log Analytics: 30 days for operational debugging, longer for compliance.

## Application-level observability

### OpenTelemetry for distributed tracing

Modern AI applications involve multiple services: API gateway, preprocessing, embedding, vector search, LLM inference, post-processing. OpenTelemetry follows a request through the entire pipeline:

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

configure_azure_monitor()
tracer = trace.get_tracer("inference-pipeline")

def process_request(user_query):
    with tracer.start_as_current_span("inference-pipeline") as span:
        with tracer.start_as_current_span("generate-embedding"):
            embedding = embed(user_query)

        with tracer.start_as_current_span("vector-search"):
            context = search(embedding, top_k=5)

        with tracer.start_as_current_span("llm-inference") as llm_span:
            response = generate(user_query, context)
            llm_span.set_attribute("tokens.prompt", response.usage.prompt_tokens)
            llm_span.set_attribute("tokens.completion", response.usage.completion_tokens)

        return response
```

### Custom metrics for AI

- **Inference latency percentiles** (P50, P95, P99): P50 = typical experience, P95/P99 = tail latency
- **Tokens per second**: LLM inference throughput. Dropping = memory pressure or degradation
- **Queue depth**: requests waiting for GPU. Growing with stable throughput = need to scale out
- **Cache hit rate**: for semantic caching. High hit rate = less latency and cost

### Structured logging (mandatory)

```python
import logging
import json

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": getattr(record, "service", "inference-api"),
            "model_version": getattr(record, "model_version", "unknown"),
            "request_id": getattr(record, "request_id", None),
            "tokens_used": getattr(record, "tokens_used", None),
            "latency_ms": getattr(record, "latency_ms", None),
        }
        return json.dumps(log_entry)
```

Always log model version and deployment name with every trace and metric. When latency spikes 40% after a rollout, you need that correlation immediately.

## In the next post

With monitoring covering all 6 dimensions, we'll cover **security for AI**: prompt injection, data leakage, managed identities, private endpoints, and the threats your WAF won't catch.