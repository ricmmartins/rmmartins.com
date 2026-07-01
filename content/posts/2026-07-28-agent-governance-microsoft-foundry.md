---
slug: "agent-governance-microsoft-foundry"
translationKey: "governanca-agentes-microsoft-foundry"
title: "Agent Governance on Microsoft Foundry"
description: "How Microsoft Foundry handles identity, RBAC, tool catalogs, and policy enforcement for AI agents at organizational scale."
date: 2026-07-28T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - microsoft-foundry
  - governance
  - rbac
  - azure-policy
  - ai-agents
  - entra-id
series:
  - "MCP Agents and Infrastructure"
---
# Chapter 5: Governance on Microsoft Foundry

The four previous posts built agents I designed myself, where I know exactly what each tool does and remember off the top of my head which flag restricts what. That works right up until another team, without having read this series, stands up their own agent on the same platform, and at that point the question stops being "is this tool safe" and becomes "how do I know, at the organizational level, what's running and with what permissions." That's the moment governance stops being a good practice and becomes a prerequisite.

Microsoft's platform for this, now called **Microsoft Foundry** (the name that came after "Azure AI Foundry," worth checking which one still shows up in your subscription, the rename is still rolling out in some places), already covers a good chunk of what I applied by hand in the earlier posts. This post is about where the platform solves this for you and where it doesn't, because both matter to whoever is going to sign off on this governance.

## Hubs and projects as the unit of isolation

Foundry's structure has two layers: the hub is a shared workspace with centralized compute, storage, Key Vault, and Container Registry; the project is the isolated unit within it, typically per team. Data, whether files, conversation history, or search indexes, doesn't leak from one project to another, even when both live under the same hub.

Applying this to the series' agents: the token watchdog and the AKS diagnoser could perfectly well live in the same project, since they belong to the same SRE team. But if the data team decides to build its own agent on top of the same hub, it lands in a separate project by default, without anyone having to remember to configure isolation manually every time.

## Granular RBAC: who creates isn't who publishes

Foundry separates, through native Azure roles, who can create an agent from who can publish it to production: the minimum role to publish is `Foundry Project Manager`, distinct from `Foundry User`, which only operates within what already exists. This is exactly the control that's missing when an agent is born from a personal script: in the earlier posts, I was simultaneously the one who wrote, tested, and "published" every agent. In a real organization, those need to be different roles, with approval between one and the other. That's what Foundry's RBAC enforces natively instead of relying on informal process.

## Identity per agent, not a shared credential

This is the point that most directly resolves a pain I dragged through the whole series: every published agent version on Foundry gets its own short-lived managed identity, the Entra Agent Identity. In posts 1 through 4, I kept insisting on least privilege and never sharing credentials between agents as a practice you have to remember to apply. On Foundry, it's structural: there's no shared credential to forget to rotate, because every agent is born with its own identity, scoped to the published version.

## A governed tool/MCP catalog, not flags stitched together

Foundry has an "Add Tools" catalog where you register MCP servers, including remote ones like the Azure DevOps server already available in the catalog, and explicitly choose which subset of tools each agent is allowed to use from that server. It's the platform-level application of the same principle I applied via `--access-level readonly` on `aks-mcp` back in post 1, except now it's centralized and auditable in a catalog, instead of a command-line flag that only whoever did the original deploy knows exists. If someone asks six months from now "can this agent scale a deployment?", the answer is in the catalog, not in the memory of whoever configured it.

## Policy as a deploy gate, not a manual review

Azure Policy can automatically block the deploy of an agent that violates a model access, data handling, or content safety rule, before the agent even starts running, not as an after-the-fact audit. That's an important shift in posture: in the earlier posts, every guardrail I built was my own code, reviewable only by me. Policy is platform-level enforcement that applies to any agent published by any team, whether or not they ever read this blog series.

## Native observability instead of hand-rolled logging

In post 3, the guardrail I proposed for the watchdog was logging the reasoning behind every decision by hand, so you could later audit why something became `info` instead of `urgent`. Foundry already offers this out of the box: OpenTelemetry-based tracing that captures every agent interaction in production, with built-in evaluators for coherence, relevance, groundedness, and safety. It's still worth doing your own logging for cases very specific to your domain, but for general auditing, it's better to use what the platform already gives you than to rebuild it.

## CI/CD with real versioning

RBAC per environment (dev, test, production), only a pipeline service principal with an audited OIDC token promoting between them, and rollback that's just pointing the active-version pointer back, with no re-deploy. This closes a question none of the earlier posts covered: who changed this agent, when, and how do I get back to the previous version without rebuilding anything by hand.

## Provisioning hub and project via Terraform

Foundry's hub and project have native resources in the `azurerm` provider: `azurerm_ai_foundry` (the hub) and `azurerm_ai_foundry_project` (the project), confirmed in the Terraform Registry:

```hcl
resource "azurerm_ai_foundry" "hub" {
  name                = "hub-sre-ai"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  storage_account_id  = azurerm_storage_account.ai.id
  key_vault_id        = azurerm_key_vault.ai.id

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_ai_foundry_project" "watchdog" {
  name               = "project-watchdog-429"
  location           = azurerm_ai_foundry.hub.location
  ai_services_hub_id = azurerm_ai_foundry.hub.id

  identity {
    type = "SystemAssigned"
  }
}
```

That gives you per-project isolation right in Terraform state: every new team that needs a project is one more block, reviewable in a pull request, instead of someone clicking around the portal that nobody remembers later.

## What the platform still doesn't solve on its own

There are limits, though, and "the platform handles that" is the phrase that most reliably generates a false sense of security. Defender for Cloud's AI workload protection plan (in preview as of early 2026) covers prompt injection detection, anomalous inference volume, and access from unexpected geolocations, but it doesn't cover grounding data integrity (writes to RAG containers) or managed identity lateral movement between hub and Key Vault. Platform governance centralizes and formalizes what you should already be doing. It doesn't think for you about which tools a specific agent actually needs. That's still your design work, the same tool-by-tool exercise we did across the previous four posts.

To close with something practical: you can monitor changes to content safety or RAI policy directly via Log Analytics, treating it as a security configuration change, not a routine ML operation:

```kql
AzureActivity
| where OperationNameValue contains "contentFilters" or OperationNameValue contains "raiPolicies"
| where ResourceId contains "MachineLearningServices"
| where ActivityStatus == "Succeeded"
| project TimeGenerated, Caller, OperationNameValue, ResourceId, ActivityStatus
| order by TimeGenerated desc
```

## Wrapping up the series

Five posts, from concept to governance: what MCP is and how an agent decides the sequence of calls on its own; a watchdog that started as a deterministic script and only later gained reasoning, with the guardrail of never gaining the power to act; an orchestrator that correlates two agents without creating a new attack surface; and now the platform layer that formalizes all of it beyond what fits in the memory of whoever wrote the code.

The thread connecting all five is always the same: decision autonomy, yes; autonomy to act on production, no, unless it's an explicit, auditable, reviewed choice rather than a configuration accident. That holds for the `--access-level readonly` on a command-line flag, and it holds for the tool catalog of an entire Microsoft platform, at a completely different scale.

If your company is at that point, with several teams standing up agents with no coordination and nobody yet knowing how to look at this centrally, that's exactly the kind of design I help work through. Happy to talk if that's useful.

**Companion repo**: I've put together all the Terraform used from post 2 through post 5, covering Cognitive Account/Deployment, Action Group, Metric Alert, managed identity with RBAC, and Foundry hub and project, in a single, per-post-commented file, in `infra/terraform/main.tf`.

---

*This is post 5 of the series "MCP, Agents, and Agent Teams for Infrastructure Engineers":*

1. [MCP and Agents 101](/2026/07/01/mcp-and-agents-101-for-infra-engineers/)
2. [The Deterministic 429 Watchdog](/2026/07/08/deterministic-429-watchdog-azure-openai/)
3. [From Script to Agent](/2026/07/14/agentic-watchdog-decision-autonomy-guardrails/)
4. [Multi-Agent Orchestration](/2026/07/21/multi-agent-orchestration-aks-openai-correlation/)
5. **Governance on Microsoft Foundry**

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/governanca-agentes-microsoft-foundry/).*
