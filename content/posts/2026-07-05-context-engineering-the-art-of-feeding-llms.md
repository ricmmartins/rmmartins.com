---
slug: "context-engineering-the-art-of-feeding-llms"
aliases:
  - "/2026/07/05/context-engineering-the-art-of-feeding-llms/"
translationKey: "context-engineering-a-arte-de-alimentar-llms"
title: "Context engineering: the art of feeding LLMs"
description: "Most of an LLM application's quality comes from how you assemble the input. Here's how to design context, prompts, tools, and token budgets like an infrastructure engineer."
date: 2026-07-05T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - context-engineering
  - prompt-engineering
  - azure-openai
  - llm
  - infrastructure
---

You build a RAG pipeline, connect it to Azure OpenAI, and the answers come back... meh. Generic. Sometimes it ignores the context you sent. Sometimes it makes things up. The model is powerful, but input quality usually determines most of the result.

Context engineering is the discipline of assembling that input so the model gives you what you actually need. It is not just "prompt engineering" with a fresher label. It is engineering: structure, constraints, and trade-offs.

**tl;dr**
- Context engineering is the work of deciding what the model sees, in what format, and within what token budget.
- Good results usually come from better structure, better examples, and tighter tool definitions, not from bigger prompts.
- Treat tokens like capacity: limited, billable, and worth budgeting.

## The map for infra engineers

| Concept | What it does | Infra equivalent |
|---|---|---|
| **System prompt** | Persistent instructions for the model | Service configuration file |
| **User message** | User input | The HTTP request |
| **Context window** | Total space available for input + output | Process RAM |
| **Few-shot examples** | Examples of the desired format | Response templates |
| **Tool definitions** | Functions the model can call | API contracts/OpenAPI specs |
| **Retrieval context** | Docs fetched through RAG | Database data in the response |
| **Token budget** | How much space each part uses | Capacity planning |

## The anatomy of an LLM request

Every request to a chat LLM is an array of messages. Each message has a role and content. The order matters.

```json
{
  "messages": [
    {"role": "system", "content": "...system instructions..."},
    {"role": "user", "content": "first user message"},
    {"role": "assistant", "content": "previous model response"},
    {"role": "user", "content": "second user message"},
    {"role": "user", "content": "...with injected RAG context..."}
  ],
  "temperature": 0.1,
  "max_tokens": 2000
}
```

Think of this like building the body of a POST request. The payload structure determines what the service returns.

## Token budget: capacity planning for context

The context window is finite. GPT-4o has 128K tokens (as of mid-2026; check [current model documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models) for updated limits), but that does not mean you should use all of them. Input tokens cost money and increase latency. In the common dense-attention case, the cost of paying attention to long context still grows fast enough that sloppy prompts hurt.

A typical split:

```text
Context Window (128K tokens)
├── System prompt:    500-2000 tokens
├── History:          variable
├── RAG docs:         2K-10K tokens
└── Output reserved:  2K-4K tokens
```

In practice, most applications use 5-15% of the context window. Using more than that gets expensive, and quality does not improve proportionally (the model can get "lost" in very large contexts).

### Doing capacity planning

```python
import tiktoken

def calculate_budget(system_prompt, history, rag_chunks, max_output=2000):
    """Calculate context window usage."""
    enc = tiktoken.encoding_for_model("gpt-4o")
    
    tokens_system = len(enc.encode(system_prompt))
    tokens_history = sum(len(enc.encode(m["content"])) for m in history)
    tokens_rag = sum(len(enc.encode(c)) for c in rag_chunks)
    tokens_output = max_output
    
    total = tokens_system + tokens_history + tokens_rag + tokens_output
    limit = 128000
    
    print(f"System prompt: {tokens_system:,} tokens ({tokens_system/limit*100:.1f}%)")
    print(f"History:       {tokens_history:,} tokens ({tokens_history/limit*100:.1f}%)")
    print(f"RAG context:   {tokens_rag:,} tokens ({tokens_rag/limit*100:.1f}%)")
    print(f"Output buffer: {tokens_output:,} tokens ({tokens_output/limit*100:.1f}%)")
    print(f"─────────────────────────────")
    print(f"Total:         {total:,} / {limit:,} ({total/limit*100:.1f}%)")
    
    if total > limit:
        print("⚠️  OVERFLOW: you need to reduce the context!")
    
    return total
```

## System prompt: the service configuration

The system prompt is the most important and most neglected part. It is where you define persona, constraints, output format, and safety rules.

### Principles of a good system prompt

**1. Be specific about the role**

```
Bad:  "You are a helpful assistant."
Good: "You are a technical assistant for infrastructure engineers
       at Acme. Answer questions about our runbooks and
       operating procedures. If the information is not in the
       provided documents, say clearly that you could not find it."
```

**2. Define explicit constraints**

```
- Answer ONLY based on the documents provided in the context.
- If you cannot find the information, reply: "I could not find that information in the available runbooks."
- Never invent procedures or commands.
- Include the source document name in the answer.
- Format: direct answer first, then the steps if applicable.
```

**3. Give examples of the desired format (few-shot)**

```
Example:
Question: "How do I restart the DNS service?"
Answer: According to runbook NET-007 (DNS Management), the procedure is:
1. Connect to server ns1.acme.corp via SSH
2. Run: sudo systemctl restart named
3. Verify: dig @localhost acme.corp

If the service does not come back up, escalate to L3 according to SOP-001.
```

**4. Handle edge cases**

```
If the user requests something involving root access or production changes:
- Confirm that they have change management approval
- Include the warning: "This procedure requires an approved change request"
```

## Few-shot examples: showing instead of explaining

Instead of describing the output format in words, show examples. The model learns patterns very well that way.

```json
{
  "messages": [
    {"role": "system", "content": "Classify support tickets into categories."},
    {"role": "user", "content": "I can't access the VPN since yesterday"},
    {"role": "assistant", "content": "{\"category\": \"network\", \"priority\": \"high\", \"component\": \"vpn\"}"},
    {"role": "user", "content": "I need more space in my home directory"},
    {"role": "assistant", "content": "{\"category\": \"storage\", \"priority\": \"low\", \"component\": \"nfs\"}"},
    {"role": "user", "content": "Jenkins is not building, permission error on the Docker socket"}
  ]
}
```

Three examples are usually enough. More than five rarely improves the result and just burns tokens.

## Retrieval context: what to send and how

When you implement RAG (as in the previous post), the retrieved chunks become part of the context. How you format those chunks matters.

### Bad format

```
Context: postgresql failover verify replication run select pg_last_wal_receive_lsn execute pg_promote on standby update dns to point to new primary verify application connections
```

### Good format

```
--- Document: DR-003 - PostgreSQL Failover (updated: 2024-11-15) ---

Prerequisites:
- Streaming replication active (check with pg_stat_replication)
- Standby lag < 1MB

Procedure:
1. Verify that the primary is truly unavailable (not just a network issue)
2. On the standby: SELECT pg_promote();
3. Update DNS: db-primary.acme.corp → IP of the new primary
4. Verify connections: SELECT count(*) FROM pg_stat_activity;

Rollback: if the original primary comes back, it rejoins as a standby via pg_rewind.
---
```

Clear structure, metadata (doc name, date), and formatting the model can parse. The model understands the context better when it is well organized.

## Tool definitions: giving the model hands

Function calling (or tool use) lets the model "call functions" instead of only generating text. You define the available tools, and the model decides when and how to use them.

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_server_status",
        "description": "Returns the current status of a server by hostname",
        "parameters": {
          "type": "object",
          "properties": {
            "hostname": {"type": "string", "description": "Server name (for example: web-prod-01)"}
          },
          "required": ["hostname"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_incident",
        "description": "Creates an incident in PagerDuty",
        "parameters": {
          "type": "object",
          "properties": {
            "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
            "title": {"type": "string"},
            "service": {"type": "string"}
          },
          "required": ["severity", "title", "service"]
        }
      }
    }
  ]
}
```

Each tool definition consumes tokens from the context window. A typical definition uses 100-300 tokens. With 20 tools, that is 2,000-6,000 tokens just for definitions. That is capacity planning: the more tools you give the model, the less space remains for context and output.

## Advanced techniques

### Chain of Thought (CoT)

For problems that need reasoning, ask for a stepwise analysis or a structured diagnosis instead of a one-shot answer. That usually improves accuracy, especially in troubleshooting flows.

```
System prompt:
"When analyzing infrastructure problems, first list the possible causes,
then eliminate them one by one based on the symptoms, and only then give the recommendation."
```

### Structured output (JSON mode)

When you need to parse the response programmatically:

```bash
curl -X POST "$AZURE_OPENAI_ENDPOINT/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21" \
  -H "Content-Type: application/json" \
  -H "api-key: $AZURE_OPENAI_KEY" \
  -d '{
    "messages": [
      {"role": "system", "content": "Analyze the log and return JSON with: severity, component, root_cause, action"},
      {"role": "user", "content": "Error: OOMKilled pod api-server-7f8d9 in namespace production. Memory limit 512Mi exceeded."}
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0
  }'
```

Response:

```json
{
  "severity": "high",
  "component": "api-server",
  "root_cause": "Pod exceeded the 512Mi memory limit",
  "action": "Increase the memory limit or investigate a memory leak"
}
```

### Prompt caching

Some Azure OpenAI deployments support prompt caching, but availability depends on the model family, deployment type, and region. Check the current Azure documentation for your exact deployment before you assume cache hits.

When prompt caching is available, stable prompt prefixes can reduce both latency and cost. If the system prompt and tool definitions stay the same across requests, the service can reuse that work.

```
Request 1: [system_prompt + tools + user_msg_1] → cache miss (process everything)
Request 2: [system_prompt + tools + user_msg_2] → prefix cache hit (process only user_msg_2)
```

The more stable the beginning of your prompt is, the more cache hits you get. Put the static parts first and keep timestamps, IDs, and other per-request noise later in the prompt.

## Anti-patterns: what not to do

**Huge prompt with everything mixed together**
```
Bad: one 5,000-token system prompt covering every possible scenario
Good: lean system prompt (500-1000 tokens) + RAG to bring relevant context on demand
```

**Ignoring max_tokens**
```
Bad: not setting max_tokens (the model may generate huge responses)
Good: max_tokens: 1000-2000 for typical responses, 4000 for long responses
```

**Trusting that "the model will understand"**
```
Bad: "Answer well."
Good: "Answer in no more than 3 paragraphs. Include the exact command.
       Indicate the risk (low/medium/high)."
```

**Not versioning system prompts**
```
Bad: editing the prompt directly in the code
Good: versioned system prompt files, with changelog
```

## Monitoring context quality

After you put it in production, monitor:

- **Context utilization**: % of the context window used per request (if too low, you may be underusing it; if too high, you may truncate)
- **RAG retrieval score**: relevance of the retrieved chunks (sample manually on a regular basis)
- **Hallucination rate**: responses that contain information not present in the context
- **Token cost per query**: growth trend (conversation history keeps getting larger)

## What to take into Monday

- **Context engineering is the biggest quality lever** you have without retraining the model. Before moving to a bigger or more expensive model, optimize the input.
- **System prompt is configuration, not code.** Version it, test it, A/B test it. Changes to the system prompt change behavior as much as code changes do.
- **Token budget is capacity planning.** Treat the context window like RAM: finite, expensive, and in need of management.
- **Few-shot > description.** Showing examples works better than explaining in words what you want.
- **Tools cost tokens.** Every tool definition takes space. Only expose the tools that are relevant to the current context.

The natural next step is **LLM Evals**: measuring whether the model is actually responding well. Without metrics, context engineering turns into educated superstition.

## What can go wrong

1. **System prompt bloat** — As the product evolves, the system prompt accumulates instructions, constraints, and edge-case patches until it consumes a significant fraction of the context window. Regularly audit and prune system prompts; treat them with the same rigor as code.
2. **Few-shot examples that anchor the wrong pattern** — If your examples are biased toward a specific format or domain, the model may refuse to generalize beyond them. Test with adversarial inputs that differ from the examples to ensure flexibility.
3. **RAG retrieval poisoning the context** — If the retrieval step returns irrelevant or outdated chunks, the model treats them as ground truth and generates confidently wrong answers. Monitor retrieval quality separately from generation quality.
4. **Token budget underestimation** — Developers focus on prompt tokens and forget that tool definitions, conversation history, and retrieval chunks all compete for the same window. Track total context usage per request, not just the user message size.
5. **Prompt caching invalidation** — Azure OpenAI's prompt caching only works when the prefix is identical. A single changed character in the system prompt invalidates the cache for all requests. Be deliberate about when and how often you modify the cached prefix.

## Related posts

- [How RAG works: from theory to pipeline](/2026/07/02/how-rag-works-from-theory-to-pipeline/) — the retrieval side of context engineering
- [Visual glossary: your Rosetta Stone for infra and AI](/2026/07/05/visual-glossary-infra-ai-your-rosetta-stone/) — terminology reference for the concepts in this post
- [MCP and agents 101 for infra engineers](/2026/07/01/mcp-and-agents-101-for-infra-engineers/) — how agents use tools, which consume context window tokens

## Further reading

- [Work with chat completion models - Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/chatgpt)
- [Prompt caching with Azure OpenAI in Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching)
- [How RAG works: from theory to pipeline](/2026/07/02/how-rag-works-from-theory-to-pipeline/)
- *This post is also available in [Portuguese](https://ricardomartins.com.br/context-engineering-a-arte-de-alimentar-llms/).*
