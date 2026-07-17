---
slug: "agent-governance-microsoft-foundry"
aliases:
  - "/2026/07/28/agent-governance-microsoft-foundry/"
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

The previous four posts built agents I designed myself, so I could still keep the whole thing in my head. That arrangement lasts right up until another team stands up its own agent on the same platform. Then the question stops being "is this tool safe" and becomes "how do I know what is running, where, and with which permissions?" That is the point where governance stops being a nice habit and becomes table stakes.

Microsoft's platform for this, now called **Microsoft Foundry**, already covers a good chunk of what I applied by hand in the earlier posts. You may still see the older Azure AI Foundry naming in parts of the portal and in older docs while the rename finishes rolling out. This post is about what the platform handles for you and what it still leaves on your desk, because both matter to whoever has to sign off on the design.

**tl;dr**
- Use Foundry projects as isolation boundaries so teams do not share state and tools by accident.
- Split creator and publisher permissions with RBAC instead of relying on process alone.
- Give each published agent its own identity and a governed MCP/tool catalog.
- Use policy, tracing, and deployment pipelines to make agent releases reviewable and reversible.

## Foundry resource and project as the unit of isolation

In the current Foundry model, the top-level resource is the Foundry account itself and projects sit underneath it as isolated workspaces for teams. If you still have older hub-based setups in your subscription, you may still see that vocabulary, but new Terraform examples and the newer control plane center on the Foundry resource plus projects. Files, conversation state, and indexes stay scoped to the project unless you choose to share something explicitly.

Applied to the agents from this series, the token watchdog and the AKS diagnoser could live in the same project because they belong to the same SRE team. If the data team builds its own agent under the same Foundry resource, it should land in a different project by default. That separation should not depend on anyone remembering a portal checkbox on a Friday afternoon.

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

## Provisioning a Foundry resource and project via Terraform

This part changed quickly enough that it is worth being precise. The current Microsoft Learn guidance for new deployments uses `azurerm_cognitive_account` for the Foundry resource and `azurerm_cognitive_account_project` for the project. The older `azurerm_ai_foundry` resources still exist for classic hub-based setups, but they are not where I would start for a new build. A minimal AzureRM example now looks like this:

```hcl
resource "azurerm_cognitive_account" "foundry" {
  name                = "foundry-sre-ai"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  kind                = "AIServices"
  sku_name            = "S0"

  identity {
    type = "SystemAssigned"
  }

  custom_subdomain_name      = "foundry-sre-ai"
  project_management_enabled = true
}

resource "azurerm_cognitive_account_project" "watchdog" {
  name                 = "project-watchdog-429"
  location             = azurerm_resource_group.ai.location
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  identity {
    type = "SystemAssigned"
  }
}
```

That gets you per-project isolation in Terraform state. Every new team becomes one more reviewable block in a pull request instead of another half-remembered click path in the portal.

## What the platform still doesn't solve on its own

There are limits, and "the platform handles that" is still one of the more dangerous sentences in architecture work. Foundry and the surrounding Azure controls help with policy, identity, tracing, and central visibility. They do not magically solve data integrity for your grounding sources or least-privilege design between Foundry, Key Vault, Search, storage, and whatever else your agent touches. Platform governance formalizes what you should already be doing. It does not do the tool-by-tool thinking for you.

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

If your company is already at the point where several teams are standing up agents with no shared view, do this design work early. Untangling it later is slower and usually more political.

That answers the opening governance question. You get a place to see what is running, where it lives, and which permissions it carries, without relying on tribal memory.

## Further reading

- [Microsoft Foundry documentation](https://learn.microsoft.com/en-us/azure/foundry/)
- [Create a project in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/create-projects)
- [Role-based access control for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry)
- [Overview of Azure Policy](https://learn.microsoft.com/en-us/azure/governance/policy/overview)
- [What is Azure role-based access control (Azure RBAC)?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)

**Companion repo**: I put together the Terraform used from post 2 through post 5, covering Cognitive Account and deployment resources, Action Group, Metric Alert, managed identity with RBAC, and the Foundry resource plus project, in a single per-post-commented file at `infra/terraform/main.tf`.

*Leia este post em [Português](https://ricardomartins.com.br/governanca-agentes-microsoft-foundry/).*
