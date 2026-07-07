---
slug: "from-prompt-engineering-to-frontier-company"
translationKey: "da-prompt-engineering-a-frontier-company"
title: "From prompt engineering to frontier company: why the model is no longer the differentiator"
description: "Models became a commodity. The real differentiator is the system around them: harness engineering, context engineering, governance. How the conversation evolved in 3 years and where we are today."
date: 2026-07-02T18:00:00-04:00
categories:
  - AI
  - Architecture
tags:
  - ai-engineering
  - harness-engineering
  - context-engineering
  - frontier-company
  - ai-agents
  - azure
---

Three years ago, the question I heard most was: "what's the best prompt?"

Two years ago, it shifted to: "how do I do RAG?"

Last year: "how do I build an agent?"

This year, the conversation is different. People are asking how to transform an entire organization to operate with agents. Not a chatbot on the website. Dozens of agents embedded in business processes, with governance, observability, granular permissions.

That progression tells a story, and we often discuss each phase as if it appeared out of nowhere.

## The timeline

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 520" style="width:100%;height:auto" role="img" aria-label="Evolution of AI engineering: from Prompt Engineering to Frontier Company, showing each discipline as a step in a vertical timeline">
<defs>
<marker id="arr-blue" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#6c8ebf"/>
</marker>
<marker id="arr-purple" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#9673a6"/>
</marker>
<marker id="arr-green" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#82b366"/>
</marker>
</defs>
<g font-family="Segoe UI, Arial, sans-serif">
<rect x="250" y="10" width="280" height="42" rx="8" fill="#dae8fc" stroke="#6c8ebf" stroke-width="2"/>
<text x="390" y="36" text-anchor="middle" font-size="13" font-weight="bold" fill="#1a3a5c">Prompt Engineering</text>
<line x1="390" y1="52" x2="390" y2="78" stroke="#6c8ebf" stroke-width="2" marker-end="url(#arr-blue)"/>
<rect x="250" y="80" width="280" height="42" rx="8" fill="#dae8fc" stroke="#6c8ebf" stroke-width="2"/>
<text x="390" y="106" text-anchor="middle" font-size="13" font-weight="bold" fill="#1a3a5c">Context Engineering</text>
<line x1="390" y1="122" x2="390" y2="148" stroke="#6c8ebf" stroke-width="2" marker-end="url(#arr-blue)"/>
<rect x="250" y="150" width="280" height="42" rx="8" fill="#dae8fc" stroke="#6c8ebf" stroke-width="2"/>
<text x="390" y="176" text-anchor="middle" font-size="13" font-weight="bold" fill="#1a3a5c">RAG + Tool Calling</text>
<line x1="390" y1="192" x2="390" y2="218" stroke="#6c8ebf" stroke-width="2" marker-end="url(#arr-purple)"/>
<rect x="250" y="220" width="280" height="42" rx="8" fill="#e1d5e7" stroke="#9673a6" stroke-width="2"/>
<text x="390" y="246" text-anchor="middle" font-size="13" font-weight="bold" fill="#4a235a">Agent Engineering</text>
<line x1="390" y1="262" x2="390" y2="288" stroke="#9673a6" stroke-width="2" marker-end="url(#arr-purple)"/>
<rect x="250" y="290" width="280" height="42" rx="8" fill="#e1d5e7" stroke="#9673a6" stroke-width="2"/>
<text x="390" y="316" text-anchor="middle" font-size="13" font-weight="bold" fill="#4a235a">Harness Engineering</text>
<line x1="390" y1="332" x2="390" y2="358" stroke="#9673a6" stroke-width="2" marker-end="url(#arr-purple)"/>
<rect x="250" y="360" width="280" height="42" rx="8" fill="#e1d5e7" stroke="#9673a6" stroke-width="2"/>
<text x="390" y="386" text-anchor="middle" font-size="13" font-weight="bold" fill="#4a235a">Multi-Agent Systems</text>
<line x1="390" y1="402" x2="390" y2="428" stroke="#82b366" stroke-width="2" marker-end="url(#arr-green)"/>
<rect x="250" y="430" width="280" height="48" rx="8" fill="#d5e8d4" stroke="#82b366" stroke-width="2.5"/>
<text x="390" y="459" text-anchor="middle" font-size="14" font-weight="bold" fill="#1b5e20">Frontier Company</text>
<text x="60" y="36" font-size="11" fill="#888">2023</text>
<text x="60" y="106" font-size="11" fill="#888">2024</text>
<text x="60" y="176" font-size="11" fill="#888">2024</text>
<text x="60" y="246" font-size="11" fill="#888">2025</text>
<text x="60" y="316" font-size="11" fill="#888">2026</text>
<text x="60" y="386" font-size="11" fill="#888">2026</text>
<text x="60" y="459" font-size="11" fill="#888">2026+</text>
<text x="620" y="36" font-size="10" fill="#666">how to talk to the model</text>
<text x="620" y="106" font-size="10" fill="#666">what the model can see</text>
<text x="620" y="176" font-size="10" fill="#666">give it memory and action</text>
<text x="620" y="246" font-size="10" fill="#666">decision autonomy</text>
<text x="620" y="316" font-size="10" fill="#666">production reliability</text>
<text x="620" y="386" font-size="10" fill="#666">agent coordination</text>
<text x="620" y="459" font-size="10" fill="#666">entire org operates with agents</text>
</g>
</svg>

Each step solved a real problem the previous one didn't cover. Prompt engineering taught us how to talk to the model. Context engineering taught us how to feed it the right information. RAG and tool calling gave it memory and the ability to act. Agents gave it autonomy. And then we realized that autonomy without control is chaos in production.

## The model became a commodity

I'll be direct: the model is no longer the competitive differentiator.

In 2023, having access to GPT-4 was a real advantage. Today there's GPT-5, Claude, Gemini, Llama, DeepSeek, Mistral, Qwen. All excellent. All capable of writing code, interpreting images, calling tools, solving complex problems.

Are there still differences between them? Yes. But the gap between the best and the fifth best has shrunk so much that it rarely determines a project's success.

Think of it this way: two companies using the exact same model. The first connects that model to their CRM, ERP, monitoring, internal docs, pipelines, security policies, and business workflows. The second opens a chat window.

Same model. Completely different results.

The value was never just in the brain. It was always in the system around it.

## Harness engineering: the name of the game now

One formula that captures the mood this year is:

```
Agent = Model + Harness
```

The model is the "brain." The harness is everything that turns that brain into an agent that works in production. The analogy I keep coming back to is motorsport. The driver is the LLM. The car, radio, telemetry, pit crew, and race rules are the harness. Put the best driver in a bad car and you still lose.

In practice, the harness of a corporate agent includes:

| Component | What it does | Azure service |
|-----------|-------------|---------------|
| System prompts | Defines personality and constraints | Azure AI Foundry |
| Tools (MCP/APIs) | Gives the ability to act | Azure Functions, Logic Apps |
| RAG | Retrieves relevant knowledge | Azure AI Search |
| Memory | Maintains state across sessions | Cosmos DB |
| Permissions | Controls who accesses what | Microsoft Entra ID |
| Human approval | Critical decisions go through people | Logic Apps, Service Bus |
| Evaluation | Measures response quality | Azure AI Foundry evals |
| Observability | Logs, traces, metrics | Azure Monitor, App Insights |
| Guardrails | Prevents unwanted behavior | Azure AI Content Safety |
| Orchestration | Coordinates multiple agents | Azure Container Apps, AKS |

Notice the pattern? Almost nothing on this list is AI. It's software engineering. Infrastructure. The kind of thing we've been doing for years, applied to a new context.

## A concrete example

Imagine an agent that answers questions about your Azure infrastructure. Someone asks:

> "Which VM has been consuming the most CPU in the last 24 hours?"

The model alone doesn't know the answer. It has no access to your environment.

With a well-built harness, the actual flow is:

1. The agent identifies the intent (VM metrics query)
2. Validates whether the user has permission to access this data (Entra ID)
3. Queries Azure Resource Graph to list VMs
4. Calls Azure Monitor to pull CPU metrics
5. Compares results and identifies the worst case
6. Builds the response with real data
7. Optionally suggests action (resize, alert, runbook)

This entire flow has nothing to do with "which model to use." It's system design. Integrations. Permissions. Observability.

In code, the agent's call to Azure Resource Graph would look something like:

```bash
az graph query -q "
  Resources
  | where type == 'microsoft.compute/virtualmachines'
  | project name, resourceGroup, location, properties.hardwareProfile.vmSize
" --output table
```

And the CPU metrics would come from Monitor:

```bash
az monitor metrics list \
  --resource "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm}" \
  --metric "Percentage CPU" \
  --aggregation Average \
  --interval PT1H \
  --start-time 2026-07-02T00:00:00Z \
  --end-time 2026-07-03T00:00:00Z \
  --output table
```

The model only comes in to decide the sequence of calls and format the final response. The harness does the heavy lifting.

## Context engineering: the agent's operating system

Context is not just "dump documents into the prompt."

Context engineering is deciding:

- What the agent can see (and what it can't)
- When it can see it (temporal context)
- How long it retains information (short-term vs long-term memory)
- In what format it receives data (structured vs unstructured)
- How much space each piece takes in the token budget

I wrote about this in detail in [the context engineering post](/2026/07/05/context-engineering-the-art-of-feeding-llms/). The short version: well-crafted context is 80% of the result. A mediocre model with excellent context beats a top model with poor context.

## MCP: the USB-C of agents

Another harness component that exploded in 2026: the Model Context Protocol. I've written about it [here](/2026/07/01/mcp-and-agents-101-for-infra-engineers/) and [here](/2026/07/29/how-mcp-works-the-protocol-connecting-agents-to-the-world/), but in the context of this post the point is simple.

Before MCP, every tool needed a custom integration. Now there's a standardized protocol that connects any model to any system. That's what allowed harness engineering to scale. Instead of building one-off integrations, you expose your systems as MCP servers and any agent can consume them.

## Frontier company: when the harness becomes the business

Microsoft started using the term "frontier company" to describe something beyond "company that uses AI."

A frontier company is not a company where some employees use Copilot. It's a company where:

- Agents are part of business processes
- Humans supervise and decide, agents research and execute
- There's real governance over what agents can do
- Productivity is measured at the organizational level
- Data and systems are connected in a way agents can navigate

The difference seems subtle. But it changes the entire business architecture.

## The parallel with what we've already lived through

In the 2000s, we learned to build for physical servers. Then virtualization. Then cloud. Then containers. Then Kubernetes.

Each of those changes seemed to be "just a new technology." In reality, each one completely changed how we think about software. Cloud wasn't "run a VM somewhere else." It was a new mental model for how to build, operate, and scale systems.

I have the feeling we're living through the same thing again. Applications whose behavior is defined by agents already exist in production. And they require different practices, different architectures, different ways of testing and monitoring.

If the previous era was "cloud native," maybe this one is "agent native."

## The real differentiator

A few years from now, I doubt anyone will care much which model your company uses. Nobody asks which hypervisor runs your environment unless something is already on fire.

The differentiator will be elsewhere:

- In the quality of context your agents receive
- In the engineering of the harness (security, observability, governance)
- In the integration between agents and people
- In the ability to turn artificial intelligence into organizational intelligence

Companies do not compete on models alone. They compete on how well they turn knowledge, permissions, and systems into better decisions. That system is the harness.

---

*This post is also available in [Portuguese](https://ricardomartins.com.br/da-prompt-engineering-a-frontier-company/). If you want to dive deeper into the technical concepts mentioned here, check out the posts on [context engineering](/2026/07/05/context-engineering-the-art-of-feeding-llms/), [RAG](/2026/07/02/how-rag-works-from-theory-to-pipeline/), and [MCP](/2026/07/01/mcp-and-agents-101-for-infra-engineers/).*
