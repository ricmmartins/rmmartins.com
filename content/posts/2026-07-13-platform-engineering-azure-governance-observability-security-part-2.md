---
slug: "platform-engineering-azure-governance-observability-security-part-2"
aliases:
  - "/2026/07/13/platform-engineering-azure-governance-observability-security-part-2/"
translationKey: "platform-engineering-azure-governanca-observabilidade-seguranca-parte-2"
title: "Platform Engineering on Azure: governance, observability and security for your IDP (Part 2)"
description: "Azure Policy as guardrails, out-of-the-box observability with Managed Grafana, Workload Identity for zero secrets, and golden paths with GitHub Actions."
date: 2026-07-13T11:30:00-04:00
categories:
  - Azure
  - DevOps
tags:
  - platform-engineering
  - azure-policy
  - managed-grafana
  - workload-identity
  - github-actions
  - kubernetes
  - security
  - observability
series:
  - "Azure SRE"
---

Second post in the Azure Platform Engineering series. In [Part 1](/platform-engineering-azure-internal-developer-platform-part-1/), we built the provisioning layer of the Internal Developer Platform: Dev Center, Azure Deployment Environments, Bicep templates, and shared AKS runtime patterns. That is necessary, but it is not sufficient.

An Internal Developer Platform becomes trustworthy when it enforces standards without turning into a bureaucratic cage. That is where governance, observability, and security enter the picture. The platform must make the right path easy, the risky path difficult, and the unsupported path visible.

## tl;dr

- Use Azure Policy for guardrails instead of tribal knowledge.
- Ship observability by default so teams are not wiring dashboards on day one.
- Remove long-lived secrets with Workload Identity and make the golden path the easy path.

## Governance: Azure Policy as guardrails

Guardrails are one of the biggest differences between a real platform and a loose collection of scripts. Azure Policy gives you a way to codify those guardrails so they do not depend on tribal knowledge or manual reviews.

### Essential policies for an IDP

```bash
# 1. Require mandatory tags on all resources
az policy assignment create \
  --name "require-platform-tags" \
  --policy "/providers/Microsoft.Authorization/policyDefinitions/1e30110a-5ceb-460c-a204-c1c3969c6d62" \
  --params '{"tagName": {"value": "managedBy"}, "tagValue": {"value": "deployment-environments"}}' \
  --scope "/subscriptions/<sub-id>"

# 2. Restrict VM SKUs in dev subscriptions
az policy assignment create \
  --name "restrict-vm-skus-dev" \
  --policy "/providers/Microsoft.Authorization/policyDefinitions/cccc23c7-8427-4f53-ad12-b6a63eb452b3" \
  --params '{"listOfAllowedSKUs": {"value": ["Standard_B1ms", "Standard_B2ms", "Standard_B4ms", "Standard_D2ds_v4"]}}' \
  --scope "/subscriptions/<dev-sub-id>"

# 3. Enforce HTTPS on all App Services
az policy assignment create \
  --name "enforce-https" \
  --policy "/providers/Microsoft.Authorization/policyDefinitions/a4af4a39-4135-47fb-b175-47fbdf85311d" \
  --scope "/subscriptions/<sub-id>"
```

Those three alone eliminate a surprising amount of drift: missing tags, cost surprises in dev, and basic web security regressions.

### Custom policy for development environment expiration

The most common platform cost leak is not bad architecture. It is abandoned environments. A simple custom policy can tag old dev environments for cleanup.

```jsonc
{
  // Azure Policy does not support utcNow() in policyRule; for rolling expiration, pass a cutoff date from scheduled automation (Function/Logic App).
  "parameters": {
    "expirationCutoff": {
      "type": "String",
      "metadata": {
        "description": "ISO 8601 cutoff date injected by scheduled automation."
      }
    }
  },
  "mode": "All",
  "policyRule": {
    "if": {
      "allOf": [
        {
          "field": "tags['platform']",
          "equals": "idp-platform"
        },
        {
          "field": "tags['tier']",
          "equals": "dev"
        },
        {
          "field": "tags['createdAt']",
          "less": "[parameters('expirationCutoff')]"
        }
      ]
    },
    "then": {
      "effect": "modify",
      "details": {
        "operations": [
          {
            "operation": "addOrReplace",
            "field": "tags['scheduled-deletion']",
            "value": "true"
          }
        ],
        "roleDefinitionIds": [
          "/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c"
        ]
      }
    }
  }
}
```

Pair that with a daily cleanup job or Azure Function and you stop treating cost hygiene as a manual chore.

## Out-of-the-box observability

Developers should not need a second project just to make their first project observable. A mature IDP creates every environment with baseline telemetry, alerts, and dashboards from day one.

### `modules/observability.bicep`

```bicep
param serviceName string
param tier string
param location string
param tags object

// Shared Log Analytics workspace reference
var sharedWorkspaceId = resourceId('rg-platform-shared', 'Microsoft.OperationalInsights/workspaces', 'law-platform-shared')

// Application Insights for the service
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${serviceName}-${tier}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: sharedWorkspaceId
    RetentionInDays: tier == 'prod' ? 90 : 30
  }
}

// Alert: P95 latency above threshold
resource latencyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-latency-${serviceName}-${tier}'
  location: 'global'
  tags: tags
  properties: {
    severity: tier == 'prod' ? 2 : 3
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsights.id]
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'high-latency'
          metricName: 'requests/duration'
          metricNamespace: 'microsoft.insights/components'
          operator: 'GreaterThan'
          threshold: tier == 'prod' ? 500 : 2000
          timeAggregation: 'Average'
        }
      ]
    }
  }
}

// Alert: error rate above threshold
resource errorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-errors-${serviceName}-${tier}'
  location: 'global'
  tags: tags
  properties: {
    severity: tier == 'prod' ? 1 : 3
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    scopes: [appInsights.id]
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'high-error-rate'
          metricName: 'requests/failed'
          metricNamespace: 'microsoft.insights/components'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Total'
        }
      ]
    }
  }
}

output connectionString string = appInsights.properties.ConnectionString
// The final dashboard URL depends on the actual Managed Grafana endpoint and the imported dashboard UID.
output dashboardUrl string = 'Resolve from the Managed Grafana endpoint and imported dashboard UID'
```

This module gives developers a default setup: telemetry retention, latency monitoring, and error monitoring without making them memorize Azure Monitor internals.

## Pre-configured Grafana dashboards

Managed Grafana is the fastest way to give every service team a usable default dashboard.

```bash
# Create Managed Grafana once for the platform team
az grafana create \
  --name "grafana-platform" \
  --resource-group "rg-platform-shared" \
  --location $LOCATION \
  --sku-tier Standard

# Import a dashboard template for new services
az grafana dashboard import \
  --name "grafana-platform" \
  --resource-group "rg-platform-shared" \
  --definition @dashboards/microservice-golden-signals.json \
  --overwrite true
```

A default dashboard should show the four golden signals right away: latency, traffic, errors, and saturation. When developers land in a new environment, they should know where to look before something breaks.

## Advanced scenario: Golden Path with GitHub Actions

Provisioning alone is not enough. The strongest platform experience goes end to end: create the environment, get the pipeline, ship safely.

### `deploy.yml`

```yaml
name: Deploy to AKS

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  ACR_NAME: acrplatform
  AKS_CLUSTER: aks-platform-shared
  AKS_RESOURCE_GROUP: rg-platform-engineering

permissions:
  id-token: write
  contents: read

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.ref == 'refs/heads/main' && 'production' || 'development' }}

    steps:
      - uses: actions/checkout@v4

      - name: Azure Login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Build and push to ACR
        run: |
          az acr login --name ${{ env.ACR_NAME }}
          docker build -t ${{ env.ACR_NAME }}.azurecr.io/${{ github.event.repository.name }}:${{ github.sha }} .
          docker push ${{ env.ACR_NAME }}.azurecr.io/${{ github.event.repository.name }}:${{ github.sha }}

      - name: Set AKS context
        uses: azure/aks-set-context@v4
        with:
          resource-group: ${{ env.AKS_RESOURCE_GROUP }}
          cluster-name: ${{ env.AKS_CLUSTER }}

      - name: Deploy to namespace
        run: |
          kubectl set image deployment/${{ github.event.repository.name }} \
            app=${{ env.ACR_NAME }}.azurecr.io/${{ github.event.repository.name }}:${{ github.sha }} \
            -n ${{ vars.KUBE_NAMESPACE }}

          kubectl rollout status deployment/${{ github.event.repository.name }} \
            -n ${{ vars.KUBE_NAMESPACE }} \
            --timeout=300s
```

That is what a golden path should feel like: the approved path is easier than inventing your own.

## Security: Workload Identity and zero secrets in code

One of the most important platform promises is that developers do not have to manage long-lived credentials manually. On AKS, Workload Identity is the cleanest pattern for that.

```bash
# Create a managed identity for the service
az identity create \
  --name "id-payment-svc" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Create a federated credential for the AKS namespace
az identity federated-credential create \
  --name "fc-payment-svc-aks" \
  --identity-name "id-payment-svc" \
  --resource-group $RESOURCE_GROUP \
  --issuer "$(az aks show -n $AKS_NAME -g $RESOURCE_GROUP --query oidcIssuerProfile.issuerUrl -o tsv)" \
  --subject "system:serviceaccount:payment-svc:payment-svc-sa" \
  --audiences "api://AzureADTokenExchange"

# Grant PostgreSQL access via Entra Authentication
# 1. Enable Entra auth on PostgreSQL Flexible Server
az postgres flexible-server update \
  --name "psql-payment-svc-dev" \
  --resource-group $RESOURCE_GROUP \
  --microsoft-entra-auth Enabled

# 2. Add Managed Identity as Entra administrator
az postgres flexible-server ad-admin create \
  --server-name "psql-payment-svc-dev" \
  --resource-group $RESOURCE_GROUP \
  --display-name "id-payment-svc" \
  --object-id "$(az identity show -n id-payment-svc -g $RESOURCE_GROUP --query principalId -o tsv)" \
  --type ServicePrincipal
```

And the Kubernetes service account becomes:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: payment-svc-sa
  namespace: payment-svc
  annotations:
    azure.workload.identity/client-id: "<managed-identity-client-id>"
---
# In your Deployment, add to the pod template:
# spec.template.metadata.labels:
#   azure.workload.identity/use: "true"
# spec.template.spec.serviceAccountName: payment-svc-sa
```

That removes the usual mess: no secret mounted into the pod, no credential committed into Git, and no rotation ceremony pushed onto every app team.

## Troubleshooting common issues

Good platforms do not just automate the happy path. They also make failure understandable.

### Problem: template provisioning fails

**Symptom:** the developer creates an environment and the deployment fails.

**Diagnosis:**

```bash
# Check the environment status
az devcenter dev environment show \
  --name "my-payment-svc" \
  --project-name "proj-payments-team" \
  --dev-center-name $DEVCENTER_NAME \
  --query "provisioningState"

# Inspect the deployment error details
az deployment group show \
  --name "deploy-db-payment-svc" \
  --resource-group "rg-proj-payments-team-dev" \
  --query "properties.error"
```

**Common causes:**

- Dev Center managed identity lacks permission in the target subscription.
- A globally unique resource name is already taken.
- The subscription hit a quota limit.

### Problem: namespace in AKS has no connectivity

**Symptom:** pods start, but they cannot reach the database or another internal dependency.

**Diagnosis:**

```bash
# Check Network Policy objects
kubectl get networkpolicy -n payment-svc

# Test connectivity from a pod
kubectl exec -it deploy/payment-svc -n payment-svc -- \
  nc -zv psql-payment-svc-dev.postgres.database.azure.com 5432

# Validate DNS resolution
kubectl exec -it deploy/payment-svc -n payment-svc -- \
  nslookup psql-payment-svc-dev.postgres.database.azure.com
```

**Typical fix:** update egress NetworkPolicy rules or Private Endpoint DNS configuration.

### Problem: development environments keep accumulating cost

**Symptom:** the dev subscription cost curve keeps climbing even when delivery activity is flat.

**Query the likely stale environments:**

```kusto
// Identify dev environments created more than 14 days ago
AzureActivity
| where OperationNameValue == "Microsoft.Resources/deployments/write"
| where Properties has "idp-platform"
| where Properties has "tier\":\"dev"
| where TimeGenerated < ago(14d)
| extend envName = extract("\"name\":\"([^\"]+)\"", 1, Properties)
| summarize CreatedAt = min(TimeGenerated) by envName
| where CreatedAt < ago(14d)
| order by CreatedAt asc
```

Combine that with Cost Management:

```bash
# Query costs via REST API
az rest --method post \
  --url "https://management.azure.com/subscriptions/<dev-sub-id>/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body '{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"None","filter":{"tags":{"name":"tier","operator":"In","values":["dev"]}}}}'
```

## IDP success metrics

If you cannot measure whether the platform is helping, you are still operating on belief.

| Metric | How to measure it | Target |
|--------|-------------------|--------|
| **Time to first deploy** | Time between onboarding and first production deploy | < 1 day |
| **Provisioning time** | Time to create a complete environment | < 10 minutes |
| **Adoption rate** | % of teams using the platform vs. manual provisioning | > 80% |
| **Developer satisfaction** | Quarterly survey or NPS-style score | > 40 |
| **Abandoned environments** | Dev environments with no activity for >14 days | < 10% |
| **Infra-misconfiguration incidents** | Correlated production incidents from platform drift | Down month over month |
| **Self-service ratio** | Requests solved without tickets / total requests | > 90% |

## Anti-patterns to avoid

The fastest way to fail at Platform Engineering is to ship a platform nobody wants to use.

| Anti-pattern | What happens | How to avoid it |
|-------------|--------------|-----------------|
| **Platform without customers** | The team builds features no product team asked for | Start with a real pilot team and iterate from feedback |
| **Too much abstraction** | Developers cannot debug because the platform hides everything | Keep escape hatches such as read-only cluster access and easy log access |
| **Golden cage** | The platform is so rigid teams flee to shadow IT | Make golden paths the easiest path, not the only path |
| **Big-bang launch** | The platform takes too long to deliver value | Ship incrementally: dev first, then staging, then prod |
| **Ignoring developer experience** | Confusing portal, verbose CLI, vague errors | Treat the platform as a product with UX standards |
| **Copying hyperscaler case studies blindly** | The platform becomes more complex than the organization needs | Match platform complexity to team and service complexity |

The golden rule is simple: **if the platform path is harder than doing it by hand, developers will do it by hand**.

## Evolution roadmap

An IDP is not a one-time project. It is an internal product that should mature in phases.

### Phase 2: Developer portal maturity

Add a richer portal experience with service catalog, ownership metadata, documentation, and environment status in one place.

### Phase 3: Continuous scorecards and compliance

Measure service health continuously: observability enabled, SLOs defined, runbooks present, backup posture validated, security exceptions tracked.

### Phase 4: Integrated FinOps

Expose cost by team, environment, and service directly in the platform so optimization becomes part of the daily engineering workflow.

### Phase 5: AI-assisted operations

Introduce platform-aware assistants for incident triage, dependency mapping, and documentation lookup, but keep final operational decisions owned by engineers.

## Conclusion

The first half of Platform Engineering is self-service. The second half is trust. Guardrails, visibility, sane identity, and repeatable delivery are how you earn it. Azure Policy, built-in observability, Workload Identity, and GitHub Actions help put those pieces in place.

When those pieces are wired together, the Internal Developer Platform stops being a provisioning shortcut and becomes part of how the organization ships software.

## Further reading

- [Azure Deployment Environments documentation](https://learn.microsoft.com/en-us/azure/deployment-environments/)
- [Microsoft Dev Center](https://learn.microsoft.com/en-us/azure/dev-box/how-to-manage-dev-center)
- [Platform Engineering on Azure](https://learn.microsoft.com/en-us/platform-engineering/)
- [AKS Workload Identity overview](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [Azure Managed Grafana overview](https://learn.microsoft.com/en-us/azure/managed-grafana/overview)
- [Bicep documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/)
- [Azure Policy documentation](https://learn.microsoft.com/en-us/azure/governance/policy/overview)
