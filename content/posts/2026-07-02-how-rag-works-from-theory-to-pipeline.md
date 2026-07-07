---
slug: "how-rag-works-from-theory-to-pipeline"
translationKey: "como-rag-funciona-da-teoria-ao-pipeline"
title: "How RAG works: from theory to pipeline"
description: "RAG is search plus an LLM. Here’s how retrieval, chunking, embeddings, hybrid search, and Azure AI Search fit together in a practical production pipeline."
date: 2026-07-02T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai
  - rag
  - azure-ai-search
  - azure-openai
  - vector-database
  - infrastructure
---

The VP of Product walks into the daily standup: "I want the chatbot to answer questions about our internal documentation. We have 2,000 pages of runbooks, policies, and procedures. ChatGPT doesn't know any of that."

The ML team says: "We'll implement RAG."

Everyone nods. You get the job of provisioning the infrastructure. Before you start creating resources, it's worth understanding what RAG is actually doing under the hood.

## The map for infra engineers

| RAG concept | What it does | Infra equivalent |
|---|---|---|
| **Retrieval** | Finds relevant documents | Search engine query |
| **Augmentation** | Adds docs to the LLM prompt | Build the request payload |
| **Generation** | LLM produces an answer using the context | The model response |
| **Chunking** | Splits documents into smaller pieces | Data partitioning, sharding |
| **Indexing pipeline** | Processes docs and generates embeddings | ETL/data pipeline |
| **Hybrid search** | Combines semantic search + keyword search | Using CDN + origin server together |

## The problem RAG solves

LLMs have two fundamental limitations:

1. **Knowledge cutoff**: the model only knows what it saw during training. Your internal runbooks are not in there.
2. **Finite context window**: even if you could paste 2,000 pages into the prompt, it would not fit (and it would be absurdly expensive in tokens).

RAG solves both. It retrieves only the relevant passages and injects them into the prompt. The model "sees" the information it needs without having to be trained on it.

```
Without RAG:
User: "What's the database failover procedure?"
LLM: "In general, failover involves..." (generic answer, may be wrong)

With RAG:
User: "What's the database failover procedure?"
[System searches the runbooks → finds the doc "DR-003: PostgreSQL Failover"]
LLM receives: prompt + content from doc DR-003
LLM: "According to procedure DR-003, execute: 1. Verify replication..." (specific answer)
```

## The full pipeline

RAG has two phases: **indexing** (offline, periodic) and **query** (online, for every question).

### Phase 1: Indexing (offline)

Documents (source) → Chunking (split into 500-1000 token pieces) → Embedding (model generates a vector for each piece) → Vector DB (index)

**Documents**: PDFs, wikis, runbooks, tickets, code. Anything with text.

**Chunking**: split documents into pieces that fit inside the context window. Typically 500-1000 tokens per chunk, with 100-200 tokens of overlap so you don't lose context at the boundaries.

**Embedding**: each chunk becomes a vector using an embedding model (`text-embedding-3-small`, for example).

**Vector DB**: vectors are stored in the index for later retrieval.

### Phase 2: Query (online)

User question → Embedding (query) → Vector DB (search) → Top K chunks → Prompt: system + chunks + question → LLM → Response

1. The user's question is turned into an embedding
2. The vector database searches for the most similar K chunks (typically 3-10)
3. Those chunks are inserted into the prompt alongside the question
4. The LLM generates an answer based on the supplied context

## Practical implementation with Azure AI Search

Let's build a basic RAG pipeline. Azure AI Search is the most complete managed option because it supports **hybrid search** (vector + keyword), which significantly improves result quality.

### Step 1: Create the resources

```bash
# Create resource group
az group create --name rg-rag-demo --location eastus2

# Create Azure AI Search
az search service create \
  --name rag-demo-search \
  --resource-group rg-rag-demo \
  --sku standard \
  --partition-count 1 \
  --replica-count 1

# Create Azure OpenAI (for embeddings and chat)
az cognitiveservices account create \
  --name rag-demo-openai \
  --resource-group rg-rag-demo \
  --kind OpenAI \
  --sku S0 \
  --location eastus2

# Deploy embedding model
az cognitiveservices account deployment create \
  --name rag-demo-openai \
  --resource-group rg-rag-demo \
  --deployment-name text-embedding-3-small \
  --model-name text-embedding-3-small \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 1 \
  --sku-name Standard

# Deploy chat model
az cognitiveservices account deployment create \
  --name rag-demo-openai \
  --resource-group rg-rag-demo \
  --deployment-name gpt-4o \
  --model-name gpt-4o \
  --model-version "2024-08-06" \
  --model-format OpenAI \
  --sku-capacity 1 \
  --sku-name Standard
```

### Step 2: Create the index with vector + text support

```bash
# Create index via REST API
az rest --method PUT \
  --url "https://rag-demo-search.search.windows.net/indexes/runbooks?api-version=2024-07-01" \
  --headers "Content-Type=application/json" "api-key=<admin-key>" \
  --body '{
    "name": "runbooks",
    "fields": [
      {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
      {"name": "title", "type": "Edm.String", "searchable": true},
      {"name": "content", "type": "Edm.String", "searchable": true},
      {"name": "source_file", "type": "Edm.String", "filterable": true},
      {"name": "chunk_index", "type": "Edm.Int32", "filterable": true},
      {"name": "embedding", "type": "Collection(Edm.Single)", 
       "searchable": true, "retrievable": false, "stored": false,
       "dimensions": 1536, "vectorSearchProfile": "rag-profile"}
    ],
    "vectorSearch": {
      "algorithms": [{"name": "hnsw-config", "kind": "hnsw", 
        "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}],
      "profiles": [{"name": "rag-profile", "algorithm": "hnsw-config"}]
    }
  }'
```

### Step 3: Chunking and indexing (Python)

```python
import os
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# Configuration
search_client = SearchClient(
    endpoint="https://rag-demo-search.search.windows.net",
    index_name="runbooks",
    credential=AzureKeyCredential(os.environ["SEARCH_KEY"])
)

openai_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version="2024-06-01"
)

def chunk_text(text, chunk_size=800, overlap=200):
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks

def get_embedding(text):
    """Generate embedding via Azure OpenAI."""
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def index_document(file_path, title):
    """Process and index a document."""
    with open(file_path, "r") as f:
        content = f.read()
    
    chunks = chunk_text(content)
    documents = []
    for i, chunk in enumerate(chunks):
        doc = {
            "id": f"{os.path.basename(file_path)}-{i}",
            "title": title,
            "content": chunk,
            "source_file": file_path,
            "chunk_index": i,
            "embedding": get_embedding(chunk)
        }
        documents.append(doc)
    
    search_client.upload_documents(documents=documents)
    print(f"Indexado: {title} ({len(chunks)} chunks)")
```

### Step 4: Query with hybrid search

```python
from azure.search.documents.models import VectorizedQuery

def rag_query(question, top_k=5):
    """Retrieve relevant documents and generate an answer."""
    question_vector = get_embedding(question)
    
    # Hybrid search: vector + keyword
    results = search_client.search(
        search_text=question,  # keyword search
        vector_queries=[
            VectorizedQuery(
                vector=question_vector,
                k_nearest_neighbors=top_k,
                fields="embedding",
                kind="vector"
            )
        ],
        top=top_k
    )
    
    # Build context from the retrieved chunks
    context_parts = []
    for result in results:
        context_parts.append(f"[{result['title']}]\n{result['content']}")
    context = "\n\n---\n\n".join(context_parts)
    
    # Generate answer with the LLM
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": 
             "Responda a pergunta usando APENAS o contexto fornecido. "
             "Se a informação não estiver no contexto, diga que não encontrou."},
            {"role": "user", "content": f"Contexto:\n{context}\n\nPergunta: {question}"}
        ],
        temperature=0.1
    )
    
    return response.choices[0].message.content
```

## Chunking: the most underestimated decision

Chunking looks simple ("split the text into pieces"), but your chunking strategy directly affects answer quality.

| Strategy | How it works | Pros | Cons |
|---|---|---|---|
| **Fixed size** | Split every N tokens | Simple, predictable | Can cut in the middle of a sentence |
| **Sentence-based** | Split on full sentences | Preserves coherence | Variable chunk sizes |
| **Semantic** | Groups by topic/section | Better context | More complex, needs a model |
| **Document structure** | Uses document headers/sections | Respects the original structure | Depends on well-formatted docs |
| **Overlap** | Chunks share N tokens at the edges | Preserves boundary context | More storage, more indexed tokens |

Practical rule: start with fixed size (800 tokens) + overlap (200 tokens). Refine later based on results.

## Hybrid search: why keyword + vector beats vector alone

Pure vector search has a weakness: specific technical terms (service names, error codes, IDs) are not always captured well by embeddings. `ERR_AKS_NODEPOOL_SCALE_FAILED` may end up close to any AKS error, but what you really want is the document that contains that exact code.

Hybrid search combines:
- **Vector search**: finds semantically related documents
- **Keyword search (BM25)**: finds documents with exact terms

Azure AI Search does this natively and merges the scores with **Reciprocal Rank Fusion (RRF)**.

## Production costs

| Component | Approximate cost | Scales with |
|---|---|---|
| Azure AI Search (Standard S1) | ~$250/month per search unit | Number of documents and queries |
| Embedding generation (indexing) | ~$0.02 per 1M input tokens | Document volume |
| Embedding generation (query) | Negligible | Queries are short |
| LLM (GPT-4o Global Standard) | ~$2.50/1M input, ~$7.50/1M output | Number of queries |
| Storage (embeddings) | Included in Search | Dimension × quantity |

For 10,000 documents (~50MB of text), indexing costs about ~$5 in embeddings. Serving 1,000 queries/day with 5 chunks each costs about ~$15/day in LLM tokens.

## Common problems and how to fix them

**"The model is hallucinating even with RAG"**
- Retrieved chunks are not relevant (this is a retrieval problem, not a generation problem)
- Temperature is too high (drop it to 0-0.2 for factual tasks)
- Weak system prompt (explicitly instruct it: "answer ONLY from the provided context")

**"The answers are too generic"**
- Chunks are too large (you lose specificity)
- Top-K is too high (too many irrelevant chunks dilute the signal)
- Missing metadata filtering (you're not filtering by category/date)

**"Indexing takes too long"**
- Batch embedding calls (Azure OpenAI accepts up to 2048 inputs per request)
- Parallelize carefully around rate limits
- Consider smaller embedding models for prototyping (`text-embedding-3-small` vs `large`)

## What to take into Monday

- **RAG is not magic.** It's search + LLM. If search returns garbage, the LLM gives you well-phrased garbage.
- **Chunking matters more than it looks.** Spend time testing different strategies for your document type.
- **Hybrid search > vector-only.** Always. Especially with technical documentation full of specific terms.
- **Monitor retrieval separately from generation.** If the model gets it wrong, first check whether the right chunks are being retrieved.
- **Cost scales with queries, not documents.** Indexing is cheap. Serving thousands of GPT-4o requests is where the real cost lives.

In a future post, I'll talk about **Context Engineering**. Now that you know how to retrieve information with RAG, the next step is learning how to assemble the prompt so the model gets the most out of it.

## Further reading

*This post is also available in [Portuguese](https://ricardomartins.com.br/como-rag-funciona-da-teoria-ao-pipeline/).*
