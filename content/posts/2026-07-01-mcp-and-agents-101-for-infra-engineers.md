---
slug: "mcp-and-agents-101-for-infra-engineers"
translationKey: "mcp-e-agentes-101-para-engenheiros-de-infra"
title: "MCP and AI Agents 101 for Infrastructure Engineers"
description: "What MCP is, how AI agents work, and what changes operationally — explained for infra/SRE engineers with a real AKS example."
date: 2026-07-01T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - mcp
  - ai-agents
  - azure
  - aks
  - infrastructure
  - tool-calling
series:
  - "MCP Agents and Infrastructure"
---
# Chapter 1: MCP and AI Agents 101

At some point in the last few months, someone on your team showed up talking about an "AI agent" or an "MCP server" and asked you to grant access, ship a deployment, or explain to the CISO why there's a non-deterministic process with permission to touch the production cluster. This post is the mental model I wish I'd had before touching any of this for the first time: no hype, and with a real example running on Azure along the way.

## What an agent actually is

Forget the marketing definition. In practice, an agent is the combination of four things: a model that decides what to do next, a set of tools it can invoke, an execution loop that orchestrates the back-and-forth between the two, and some kind of memory that holds state through the process.

The difference between an agent and a traditional automation script is where the decision lives. In a script, you wrote the flow: "if X, do Y." In an agent, you describe the goal and the available tools, and the model decides the sequence of calls in real time, based on what each tool returns. The loop, in practice, is always this dance:

```
user prompt + available tools → model decides →
model requests a tool call → host executes the tool →
result goes back to the model → model decides again →
... until it returns final text or hits an iteration limit
```

Think of it as a runbook executed not by a human reading Confluence, but by an LLM reading the descriptions of the tools available to it. It's powerful because it generalizes: you don't need a script for every scenario. And it's risky for the same reason: the path it takes isn't 100% predictable.

## Tool calling: the mechanism behind everything

When you give a model the definition of a tool (name, description, parameter schema), it doesn't execute anything. It emits a data structure saying "I'd like to call `get_pod_logs` with `namespace=prod, pod=checkout-7f9c`." Whoever actually executes that is your code (the "host"), which takes that JSON, runs the real function, and hands the result back to the model to keep reasoning. The model never touches anything directly. It only suggests calls.

That detail sounds minor, but it's why a tool's **description** matters as much as the code behind it. A common scenario once you start testing this for real: you stand up an agent with a logs tool whose description doesn't mention a line limit or pagination. In production, a crash-looping pod generates 40,000 lines. The model calls the tool, gets back a payload too large to reason about properly, tries again with a different time window, then switches pods, then goes back to the first one. Ten calls later, a task that should have cost pennies turned into a double-digit API bill, and nobody is any closer to understanding why the pod crashed. The root cause wasn't the model "hallucinating"; it was an incomplete tool description. It's the kind of bug that doesn't show up in any tutorial, only in production.

## And this is where MCP comes in

MCP (Model Context Protocol) is an open protocol, created by Anthropic in November 2024 and donated in December 2025 to the Agentic AI Foundation, under the Linux Foundation umbrella, meaning it's now a neutral-governance standard, not a proprietary feature of a single vendor. It standardizes **how** an LLM-powered application connects to external data sources and tools, using JSON-RPC 2.0 under the hood.

The analogy that lands best for infra folks is LSP (the Language Server Protocol). Before LSP, every code editor needed its own integration for every language. LSP solved that by creating a common protocol: any editor that speaks LSP talks to any language server that speaks LSP. MCP does the same for agents: before it, every AI application that wanted to integrate with GitHub, a database, or Azure needed a proprietary integration. With MCP, you write **one** server, and any compatible host, including Claude, Copilot, Cursor, and VS Code, can talk to it without custom code.

The architecture has three pieces:

```
 ┌───────────────────────────────┐
 │             HOST               │   Claude, Copilot, Cursor, your agent
 │   ┌─────────────────────────┐ │
 │   │  MCP Client (1 per srv)  │ │
 │   └────────────┬─────────────┘ │
 └────────────────┼────────────────┘
                   │ stdio  /  HTTP + streaming
                   ▼
 ┌───────────────────────────────┐
 │           MCP SERVER           │   e.g. AKS-MCP, GitHub, Postgres
 │   tools  ·  resources  ·  prompts
 └────────────────┬────────────────┘
                   ▼
            real API / resource (Azure, K8s, database...)
```

- **Host**: the application that orchestrates the loop and shows the interface to the user.
- **MCP Client**: lives inside the host, keeps a 1-to-1 connection with each server.
- **MCP Server**: the process that exposes capabilities, local (via `stdio`) or remote (via HTTP with streaming and OAuth).

And what a server exposes are three kinds of primitives: **tools** (actions, verbs like `scale_deployment`), **resources** (data that can become context, nouns like a log or a document), and **prompts** (reusable templates the server suggests the model use for a specific task).

## A real example: an SRE agent talking to AKS via MCP

To leave theory behind: Microsoft itself maintains an open-source MCP server for AKS, `aks-mcp`, in the Azure GitHub organization. It exposes components you toggle individually: `az_cli`, `monitor`, `detectors`, `advisor`, `kubectl`, `helm`, `network`, `compute`, `fleet`, `cilium`, and `hubble`. You spin it up like this:

```
./aks-mcp --transport stdio \
  --access-level readonly \
  --enabled-components monitor,detectors,kubectl
```

From there, any MCP-compatible host, including the official AKS extension for VS Code, Claude, Copilot Chat, and Cursor, sees those capabilities as tools available to the model.

Scenario: 3 a.m., a crash-looping pod alert in production. Instead of opening five tabs (Azure Monitor, a terminal with `kubectl`, Resource Health, and Advisor), you ask the agent "why did the checkout pod crash again?" The model, seeing the available tools, decides the sequence on its own: it calls `detectors` to see if AKS has already flagged a known issue in the network mesh or control plane, calls `monitor` to pull CPU and memory metrics for the node, calls `kubectl` to grab the pod's recent events. You never wrote that script. It emerged from the combination of the question and the tools available at the time.

The detail that matters most on the operations side is `--access-level readonly`. It isn't just another parameter; it's the single most important guardrail on the whole server. Without it, this same agent could, in theory, decide to "fix" the problem by scaling the deployment or restarting a node on its own. With `readonly`, it can only look.

## Building an agent from scratch

Set aside, for a moment, which framework to use: the architecture is the same whether it's LangChain, an agent SDK, or raw code calling the API.

It starts with model choice, a trade-off between cost, latency, and reasoning quality. That matters more here than in a simple chatbot, because an agent makes multiple calls per task, not one. On top of that comes the system prompt, which defines the role, the limits of what the agent can do, and the expected response format. It's the onboarding document for your non-deterministic "employee."

The part that most decides whether the agent works well or poorly, though, is the tool definitions. Each tool's description is literally the instruction manual the model reads to decide whether and how to use it, as we saw in the giant-log example above. "Update resource" leads to misuse; "scale a Kubernetes deployment to N replicas, requires namespace and deployment name, do not use on StatefulSets" leads to correct use.

```python
# pip install mcp
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("k8s-ops")

@mcp.tool()
def scale_deployment(namespace: str, deployment: str, replicas: int) -> str:
    """Scales a Kubernetes Deployment to the given number of replicas.
    Do not use on StatefulSets. Requires the exact namespace and name."""
    # the real call to the K8s API goes here
    return result

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

That's the real pattern from the official Python SDK (`mcp.server.fastmcp.FastMCP`): the decorator pulls the function's name, type hints, and docstring automatically to generate the JSON schema the model reads, which is why the docstring isn't a comment but the interface. You register the function, pick a transport (`stdio` for local use, `streamable-http` for remote, multi-user use, with OAuth if exposed externally), and any compatible host automatically sees that capability.

On top of all that sits the execution loop itself: the orchestrator that sends the prompt and tools to the model, receives the intent to call something, executes it for real, returns the result, and repeats, always with an iteration limit, because without one a confused agent can loop calling the same tool over and over and every call is a billed API request. And finally, memory: how much of the conversation fits in the context window, whether you need to fetch outside information (RAG), whether you need to persist state across sessions.

## Building an MCP server

Building a server is simpler than it sounds, and in practice you'll rarely start from zero. Today there are official SDKs in Python, TypeScript, Java, Kotlin, C#, and Swift (plus community implementations in Rust and Go), and an ecosystem with 500+ public servers already built: databases, GitHub, Slack, and in your specific case, all of Azure through servers like `aks-mcp`. Before writing a single line of code, it's worth checking whether what you need already exists.

When it's genuinely worth building one yourself, the heart of a server looks close to this:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("k8s-ops")

@mcp.tool()
def scale_deployment(namespace: str, deployment: str, replicas: int) -> str:
    """Scales a Kubernetes Deployment to the given number of replicas.
    Do not use on StatefulSets. Requires the exact namespace and name."""
    # the real call to the K8s API goes here
    return result
```

You register the function, expose the schema, choose the transport, and any compatible host automatically sees that capability.

If you want to test this tonight without standing up a host at all, the fastest path is the MCP Inspector: `npx @modelcontextprotocol/inspector` points at any server, yours or a ready-made one like `aks-mcp`, and lets you browse its tools, call each one manually, and watch the raw JSON-RPC go back and forth. It's the most direct way to understand the protocol before you put a model in the loop.

## Agent teams (multi-agent systems)

A single agent starts to break down when the task is too big for one context window, or when it would benefit from specialization. Back to the crash-loop scenario: instead of one agent with access to everything, you can have an orchestrator that delegates to specialized sub-agents: one calling `aks-mcp` for cluster diagnosis, another checking Azure DevOps deployment history to see if a recent change lines up with the incident, a third just writing up the incident summary in the format your team uses. The orchestrator pulls the results together at the end.

The most honest analogy for your day job is microservices vs. monolith. Splitting into sub-agents gives you context isolation and a smaller blast radius per component, but it adds latency, cost (more API calls per task), and coordination complexity. Debugging "why did the agent team reach this conclusion" is harder than debugging a single agent, for the same reason debugging a chain of microservices is harder than debugging a monolith. The complexity is only worth it when the task genuinely benefits from parallelism or specialization that a single system prompt can't cover well; otherwise, it's overhead.

One side note: there's also A2A (the Agent-to-Agent Protocol), which solves a different problem from MCP: communication between agents, not between agent and tool. MCP gives an agent hands; A2A lets agents talk to each other without a central orchestrator. For the orchestrator-worker pattern described above, you don't even need it. An orchestrator calling sub-agents as functions already solves it. A2A comes into play when the agents belong to different systems or teams and need to negotiate without a shared hierarchy.

## What this changes operationally

The `aks-mcp` example already hinted at what changes on your side: an MCP server frequently carries real credentials, such as kubeconfig, API keys, and database tokens, and deserves exactly the same rigor as any other service with privileged access: secrets in a vault, rotation, minimum necessary scope per tool. The `--access-level readonly` and `--enabled-components` flags on the server are the literal application of that principle: you don't give the agent more capability than the task requires, the same way you wouldn't give a service principal more than it needs.

There's also an attack vector that doesn't exist in traditional automation: if a tool returns outside content, such as a log, an email, or the body of a web page, that content can contain instructions the model tries to follow as if they came from the user. Treat all external data as untrusted, the same way you'd treat user input in a web application. And any tool with the power to destroy something, like `delete_resource`, `scale_to_zero`, or restarting a node, shouldn't be autonomous; think of it as an approval gate in a pipeline, not a button the agent presses on its own.

Finally, cost is an operational metric, not just a financial one. Every loop iteration is a model call, and a model call is tokens, and tokens are money; without an iteration limit and a cost alert, the giant-log scenario described above stops being an exception and becomes routine. And none of this is debuggable unless you log every tool call with the same rigor you'd log any API call: who asked, what the model decided, what actually ran, what came back.

## Wrapping up

MCP is the protocol that standardizes how agents connect to tools and data: the LSP of the agent world, now under the Linux Foundation's neutral governance. An agent is model, tools, execution loop, and guardrails. It's not magic; it's an architecture with a non-deterministic component in the middle. An agent team is composition: several specialized agents coordinated, with the same trade-offs as any distributed system. And as `aks-mcp` shows, this isn't a lab experiment anymore. It's official tooling running against production clusters, with the same risks and the same demands as any other component that touches critical infrastructure: least privilege, observability, cost limits, and approval gates wherever the action is irreversible.

If you're into applied infrastructure content like this, I keep writing about Azure, AKS, and SRE at [rmmartins.com](https://rmmartins.com), and you'll find more hands-on Kubernetes material at [k8shackathon.com](https://k8shackathon.com) and [fromservertocluster.com](https://fromservertocluster.com).

*This series has a companion repo with the full Terraform used from post 2 through post 5; link at the end of post 5.*

---

*This is post 1 of the series "MCP, Agents, and Agent Teams for Infrastructure Engineers":*

1. **MCP and Agents 101**
2. [The Deterministic 429 Watchdog](/2026/07/08/deterministic-429-watchdog-azure-openai/)
3. [From Script to Agent](/2026/07/14/agentic-watchdog-decision-autonomy-guardrails/)
4. [Multi-Agent Orchestration](/2026/07/21/multi-agent-orchestration-aks-openai-correlation/)
5. [Governance on Microsoft Foundry](/2026/07/28/agent-governance-microsoft-foundry/)

*Companion repository: [agentic-infra-handbook](https://github.com/ricmmartins/agentic-infra-handbook)*

*Leia este post em [Português](https://ricardomartins.com.br/mcp-e-agentes-101-para-engenheiros-de-infra/).*
