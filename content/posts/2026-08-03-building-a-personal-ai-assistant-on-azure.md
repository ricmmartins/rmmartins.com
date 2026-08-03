---
slug: "building-a-personal-ai-assistant-on-azure"
aliases:
  - "/2026/08/03/building-a-personal-ai-assistant-on-azure/"
translationKey: "personal-ai-assistant-on-azure"
title: "Building a personal AI assistant on Azure, step by step"
description: "A complete personal AI assistant vertical slice with FastAPI, Azure OpenAI, Azure AI Search, managed identity, approval-gated tools, Container Apps, and Application Insights."
date: 2026-08-03T10:00:00-04:00
categories:
  - AI
  - Azure
tags:
  - ai-agents
  - ai-engineering
  - azure-openai
  - azure-ai-search
  - container-apps
  - managed-identity
  - rag
  - fastapi
---

Architecture diagrams are useful, but they eventually have to become files that run together. In this tutorial I build one complete vertical slice of a personal operations assistant, first on a Windows workstation with no Azure dependency, then on Azure Container Apps with Azure OpenAI and Azure AI Search.

The companion implementation is in [`labs/personal-assistant`](https://github.com/ricmmartins/agentic-infra-handbook/tree/master/labs/personal-assistant) in my `agentic-infra-handbook` repository. The commands and snippets below match that lab. The lab's README also has its own [step-by-step Azure deployment walkthrough](https://github.com/ricmmartins/agentic-infra-handbook/tree/master/labs/personal-assistant#deploy-to-azure-step-by-step), covering App Registration, the AZD environment, callback registration, validation, and cleanup as a standalone reference.

## What I am building

The finished slice has:

- a FastAPI chat API and browser interface;
- retrieval over Markdown runbooks;
- hybrid vector, lexical, and semantic search in Azure AI Search;
- Azure OpenAI authenticated through Microsoft Entra ID;
- one deterministic read tool;
- one write-like tool that creates a pending action;
- an actor-bound confirmation endpoint that performs the write;
- Container Apps Easy Auth in front of the application;
- Application Insights telemetry;
- an image built remotely in Azure Container Registry;
- infrastructure and deployment through Bicep and Azure Developer CLI.

I deliberately left two storage layers out of the first deployment. Short-term memory stays in the process, and long-term memory sits behind an interface without a production implementation. That lets me prove the request, retrieval, tool, approval, identity, and deployment paths before adding Azure Managed Redis and Cosmos DB.

The incident integration is also a mock adapter. The authorization and approval controls are real, but the final mutation does not open a ServiceNow or Jira ticket. I would rather test idempotency and audit behavior against an in-memory adapter than create real incidents while debugging the control plane.

| Path | Included in this slice |
|------|------------------------|
| Local execution without Azure | Yes |
| FastAPI and agent loop | Yes |
| Local RAG | Yes |
| Azure OpenAI | Yes |
| Azure AI Search | Yes |
| Deterministic read tool | Yes |
| Actor-bound approval for writes | Yes |
| Real ITSM integration | No, the adapter is mocked |
| Azure Managed Redis | Interface and design notes only |
| Cosmos DB long-term memory | Interface and design notes only |

This narrower scope makes failures easier to isolate. If the first deployment includes five new data services, a failed answer does not tell me which boundary broke.

![Validated personal assistant interface returning a RAG answer with runbook citations](/img/personal-assistant-rag-citations.gif)

*The validated interface returns a grounded answer and displays the runbooks used as sources. The recorded UI is a real deployment demo, and some text in the GIF is in Portuguese.*

## Repository layout and prerequisites

```text
labs/personal-assistant/
├── docs/runbooks/
├── infra/
│   ├── app.bicep
│   ├── main.bicep
│   └── main.parameters.json
├── src/personal_assistant/
│   ├── actions.py
│   ├── agent.py
│   ├── app.py
│   ├── audit.py
│   ├── bootstrap.py
│   ├── config.py
│   ├── identity.py
│   ├── incidents.py
│   ├── llm.py
│   ├── memory.py
│   ├── models.py
│   ├── observability.py
│   ├── rag.py
│   └── tools.py
├── tests/
├── .env.example
├── azure.yaml
├── Dockerfile
└── pyproject.toml
```

The project requires Python 3.12. For the Azure deployment, install:

- Git;
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli);
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd);
- permission to create resources and role assignments in the target subscription;
- quota for the chat and embedding model deployments in the selected region.

Local Docker is optional. `azure.yaml` sets `remoteBuild: true`, so Azure Container Registry builds the image for the Azure deployment.

## 1. Run the fake mode before creating Azure resources

The local mode is not a collection of disconnected mocks. It runs the same API, agent loop, tool registry, approval service, and memory interfaces used by the Azure mode. Only the model and retrieval adapters change.

On Windows PowerShell:

```powershell
git clone https://github.com/ricmmartins/agentic-infra-handbook.git
Set-Location agentic-infra-handbook\labs\personal-assistant

Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

The relevant defaults in `.env.example` are:

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
MODEL_BACKEND=fake
RAG_BACKEND=local
MEMORY_BACKEND=in_memory
LOCAL_DEV_USER_ID=00000000-0000-0000-0000-000000000001
LOCAL_DEV_USER_NAME=ricardo@example.local
```

These values prevent the application from reaching Azure. The chat model behaves deterministically, RAG reads `docs/runbooks`, metrics derive from a stable hash of the resource name, and the local identity is fixed. A request for the same resource therefore returns the same test data.

Start the API:

```powershell
personal-assistant-api
```

Open a second PowerShell window, activate the virtual environment there, and send a request:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/chat `
  -ContentType 'application/json' `
  -Body '{"session_id":"demo-1","message":"Which identity headers does the app read in Azure?"}'
```

The response contains an answer, citations, and, when a sensitive operation is requested, a `pending_action`.

Run the test suite before changing any cloud setting:

```powershell
pytest -q
```

The current lab has 12 tests. They verify:

1. chat answers include citations;
2. the root route serves the authenticated browser UI;
3. `/me` returns the authenticated actor;
4. confirmation must be explicit;
5. no incident is created before confirmation;
6. only the requesting actor can confirm;
7. the Search index contains the expected semantic fields and `en.microsoft` analyzer;
8. an HTTP `207` ingestion response with a failed document is rejected;
9. Azure mode refuses incomplete configuration;
10. tool arguments are validated before an action is created;
11. concurrent and repeated confirmation remains idempotent;
12. an authenticated service principal can use its principal ID when no user name exists.

The actor ownership test matters more than the UUID used for `action_id`. An identifier that is difficult to guess is not authorization.

## 2. Make credential selection deterministic

`DefaultAzureCredential` is convenient on a development machine because it can reuse the Azure CLI session. In a Container App, I prefer an explicit managed identity credential.

```python
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


def build_token_credential(config):
    if config.is_development:
        return DefaultAzureCredential()

    return ManagedIdentityCredential(
        client_id=config.managed_identity_client_id
    )
```

For a system-assigned identity, `managed_identity_client_id` is empty. If the runtime uses a user-assigned identity, set `MANAGED_IDENTITY_CLIENT_ID` to that identity's client ID.

This split keeps production from walking a long credential chain intended for developer workstations. It also makes a missing identity fail where I expect it to fail.

## 3. Connect Azure OpenAI without an API key

The implementation uses the OpenAI Python client against Azure OpenAI's v1 base URL:

```python
from azure.identity import get_bearer_token_provider
from openai import OpenAI


token_provider = get_bearer_token_provider(
    build_token_credential(config),
    "https://ai.azure.com/.default",
)

client = OpenAI(
    base_url=f"{config.azure_openai_endpoint.rstrip('/')}/openai/v1/",
    api_key=token_provider,
)
```

The token provider is passed through the client's `api_key` parameter because that parameter accepts a callable. No static OpenAI key is stored in the application.

### A precise note about the v1 endpoint and the Responses API

The `/openai/v1/` base URL is Azure OpenAI's v1 API surface. That name is sometimes confused with the OpenAI Responses API. They are not the same thing.

The companion revision used for this tutorial calls `client.chat.completions.create()` for chat and tool calls:

```python
response = client.chat.completions.create(
    model=config.azure_openai_chat_deployment,
    messages=messages,
    tools=tools,
    tool_choice="auto",
)
```

So this implementation uses the Azure OpenAI v1 endpoint, but its agent adapter uses the Chat Completions operation, not `client.responses.create()`. I am calling that out because describing the snippet as Responses API code would be technically wrong. The `ChatModel` protocol isolates this choice, so a later Responses API adapter can replace it without changing retrieval, approvals, or the FastAPI routes.

In both APIs, the value supplied as `model` is the Azure deployment name, not necessarily the public model name.

The validated chat deployment is `assistant-chat`, backed by `gpt-5-mini` version `2025-08-07`. The sample does not send `temperature` because this model deployment does not accept it in the tested configuration.

Embeddings use `text-embedding-3-small` with 1536 dimensions:

```python
response = client.embeddings.create(
    model=config.azure_openai_embedding_deployment,
    input=text,
    dimensions=1536,
)
```

The model can return fewer dimensions than its maximum, but the index definition, ingestion vectors, and query vectors must agree. Treat a dimension change as an index migration.

## 4. Build the Azure AI Search index

The Azure adapter uses the stable Search REST API version `2026-04-01` and creates the index idempotently. The vector field is:

```python
{
    "name": "content_vector",
    "type": "Collection(Edm.Single)",
    "searchable": True,
    "retrievable": False,
    "stored": False,
    "dimensions": 1536,
    "vectorSearchProfile": "content-vector-profile",
}
```

There is no reason to return the vector to the model. Search results select the fields that a response can quote:

```text
id,title,source,content
```

The full index also defines an HNSW algorithm and a semantic configuration:

```python
"vectorSearch": {
    "algorithms": [{"name": "content-hnsw", "kind": "hnsw"}],
    "profiles": [
        {
            "name": "content-vector-profile",
            "algorithm": "content-hnsw",
        }
    ],
},
"semantic": {
    "configurations": [
        {
            "name": "runbook-semantic",
            "prioritizedFields": {
                "titleField": {"fieldName": "title"},
                "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": [{"fieldName": "source"}],
            },
        }
    ]
},
```

The runbooks that ship in `docs/runbooks/` are English, so the `content` field uses `en.microsoft`. The analyzer choice follows the language of the indexed documents, not the language of the UI or the queries sent against it. If I localized the corpus to another language, the correct fix would be to change the analyzer and rebuild the index, not to leave an English analyzer running against non-English text.

The query combines lexical and vector retrieval, then asks for semantic ranking:

```python
payload = {
    "search": query,
    "queryType": "semantic",
    "semanticConfiguration": "runbook-semantic",
    "select": "id,title,source,content",
    "top": 3,
    "vectorQueries": [
        {
            "kind": "vector",
            "vector": query_vector,
            "fields": "content_vector",
            "k": 50,
            "weight": 2,
        }
    ],
}
```

Search runs lexical and vector retrieval in parallel, combines the rankings with Reciprocal Rank Fusion, and applies the semantic ranker. `top=3` limits the documents sent to the prompt. `k=50` gives the reranker a larger vector candidate set.

### Validate HTTP 207 at the document level

Azure AI Search can return HTTP `207 Multi-Status` when a batch contains a mix of successful and failed document operations. Treating every 2xx response as success would leave the index partially populated.

The adapter parses the response body, collects successful document keys, and rejects failures or missing keys:

```python
indexed_ids = {
    str(result.get("key"))
    for result in results
    if result.get("status") is True and result.get("key")
}

failures = [
    {
        "key": str(result.get("key", "")),
        "statusCode": str(result.get("statusCode", "")),
        "errorMessage": str(result.get("errorMessage", "")),
    }
    for result in results
    if result.get("status") is not True
]

missing_ids = sorted(expected_document_ids - indexed_ids)
if failures or missing_ids:
    raise RuntimeError(
        "Azure AI Search document ingestion was incomplete. "
        f"Failures: {failures}; missing document IDs: {missing_ids}."
    )
```

One of the 12 tests constructs a `207` response with one valid document and one invalid document, then confirms that bootstrap fails instead of accepting an incomplete knowledge base.

### Split ingestion from query permissions in production

I would use separate identities outside this lab:

| Identity | Azure AI Search roles |
|----------|-----------------------|
| Ingestion pipeline | Search Service Contributor and Search Index Data Contributor |
| Assistant API | Search Index Data Reader |

The API needs to query. The pipeline needs to alter the index and upload documents. Giving the chat runtime both permissions turns an application vulnerability into an unnecessary indexing path.

For the first deployment, `BOOTSTRAP_RAG_ON_STARTUP=true` keeps setup simple. The Container App therefore receives Search Service Contributor and Search Index Data Contributor. Move ingestion to a job or pipeline, set bootstrap to false, and reduce the API identity to Search Index Data Reader before production.

## 5. Assemble the agent loop

Each chat request starts with the authenticated actor, the caller's `session_id`, and the new message. The memory key includes both actor and session:

```python
memory_session_id = f"{actor.actor_id}:{session_id}"
documents = self.knowledge_base.search(message)
citations = [document.to_citation() for document in documents]
history = self.memory_store.get_history(memory_session_id)
```

Two people can now choose `session_id="demo"` without sharing history.

The model gets the system prompt, retrieved runbooks, prior messages, and current user message. The loop allows at most three model rounds:

```python
for _ in range(3):
    turn = self.model.complete(
        messages=messages,
        tools=self.tool_registry.schemas,
    )

    if turn.tool_calls:
        messages.append(turn.as_assistant_message())
        for tool_call in turn.tool_calls:
            result = self.tool_registry.execute(
                session_id=session_id,
                actor=actor,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )
            messages.append(result.as_tool_message(tool_call.id))
        continue

    return ChatResponse(
        answer=turn.content,
        citations=citations,
        pending_action=pending_action,
    )
```

The actual implementation also catches invalid tool arguments and feeds a structured error back to the model. If no final answer appears after three rounds, it raises an error rather than allowing an unbounded tool loop.

In production I would record the termination reason: final answer, tool error, timeout, or maximum rounds. That is much more useful than a single generic failure count.

## 6. Treat read and write tools differently

`get_resource_metrics` is read-only. Its schema limits the window to 5 through 60 minutes:

```python
{
    "type": "function",
    "function": {
        "name": "get_resource_metrics",
        "description": "Return deterministic mock metrics for a named resource.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_name": {"type": "string"},
                "window_minutes": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 60,
                },
            },
            "required": ["resource_name"],
        },
    },
}
```

The local adapter hashes the resource name and derives stable CPU, memory, and error-rate values. Replacing it with a narrowly scoped Azure Monitor adapter does not require changes to the agent loop.

`create_incident` takes a different path. A model tool call only creates a pending record:

```python
record = pending_action_service.create_incident_request(
    session_id=session_id,
    actor=actor,
    title=arguments["title"],
    summary=arguments["summary"],
    severity=arguments["severity"],
)
```

The response gives the user an `action_id` and preview. The incident adapter has not run.

![Validated personal assistant interface requesting explicit confirmation before creating an incident](/img/personal-assistant-confirmation-flow.gif)

*The model prepares a pending action. The backend performs the write only after the requesting user confirms it. This GIF shows the validated interface, with some UI text in Portuguese.*

Test the flow locally:

```powershell
$chat = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/chat `
  -ContentType 'application/json' `
  -Body '{"session_id":"demo-2","message":"Create an incident for high CPU on payments-api"}'

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/actions/$($chat.pending_action.action_id)/confirm" `
  -ContentType 'application/json' `
  -Body '{"confirm":true}'
```

The confirmation service checks that:

1. confirmation is explicit;
2. the action is still pending;
3. the authenticated actor owns the request.

The store changes the record from `pending` to `executing` while holding a lock. That claim prevents two concurrent confirmations from executing the adapter twice. A completed action returns its saved result, so a retry gets the same `incident_id`.

Only after a successful claim does the mock adapter create `INC-0001`. For a real ITSM integration, I would keep this order and add:

- durable pending-action storage;
- the `action_id` as an idempotency key;
- bounded timeouts and retries;
- stricter ownership, severity, and routing validation;
- an audit sink outside the application process.

## 7. Use the identity already validated by Container Apps

Azure Container Apps has built-in authentication, commonly called Easy Auth. After Microsoft Entra ID validates the request, the platform injects identity headers such as:

- `X-MS-CLIENT-PRINCIPAL-ID`;
- `X-MS-CLIENT-PRINCIPAL-NAME`.

The API resolves its actor from those headers:

```python
actor_id = request.headers.get("X-MS-CLIENT-PRINCIPAL-ID")
actor_name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME")

if actor_id:
    return ActorContext(
        actor_id=actor_id,
        actor_name=actor_name or actor_id,
        used_local_fallback=False,
    )
```

An app-only token may not have a user name. The code then uses the principal ID as the audit name. The fixed local identity is allowed only when `APP_ENV=development`. In any other environment, a missing principal ID returns `401`.

This design depends on Easy Auth rejecting anonymous access. Header-reading code does not secure a publicly anonymous API by itself.

`/healthz` is intentionally excluded from authentication so Container Apps probes can reach it. The root page, `/me`, `/chat`, and `/actions/{action_id}/confirm` require an authenticated session or valid bearer token.

## 8. Understand the Bicep deployment

`infra/main.bicep` runs at subscription scope, creates an isolated resource group, and calls `infra/app.bicep`. The module provisions:

- Log Analytics and Application Insights;
- Azure Container Registry Basic with the admin user disabled;
- a user-assigned identity for image pull;
- Azure OpenAI with `gpt-5-mini` and `text-embedding-3-small`;
- Azure AI Search Basic with local key authentication disabled;
- a Container Apps environment;
- a Container App with a system-assigned runtime identity;
- ACR, OpenAI, and Search role assignments;
- Microsoft Entra authentication for the Container App;
- startup, liveness, and readiness probes.

Search has a separate region parameter. In the environment I used to validate the tutorial, East US 2 did not have capacity for another Basic Search service. Keeping the application in East US 2 and placing Search in East US solved that specific capacity problem. Use one region when capacity allows.

The tested deployments are:

| Purpose | Deployment | Model |
|---------|------------|-------|
| Chat and tools | `assistant-chat` | `gpt-5-mini`, version `2025-08-07` |
| Embeddings | `assistant-embedding` | `text-embedding-3-small`, version `1`, 1536 dimensions |

Model versions and regional quota change. Check both before deployment. If your subscription cannot create these versions, update the Bicep and rerun the tests rather than changing only the portal deployment.

The Bicep fixes `minReplicas` and `maxReplicas` at one. Session history and pending actions still live in memory, so two replicas could create an action on one process and send its confirmation to another. Shared state comes before horizontal scaling.

## 9. Create the Microsoft Entra App Registration

Bicep configures Container Apps authentication, but it expects the client ID and credential of an existing App Registration. Create it in the tenant associated with the target subscription.

The following is Windows PowerShell. Backticks are PowerShell line continuations:

```powershell
az login --tenant <tenant-id>

$app = az ad app create `
  --display-name personal-assistant-reference `
  --sign-in-audience AzureADMyOrg | ConvertFrom-Json

$clientId = $app.appId
az ad app update `
  --id $clientId `
  --identifier-uris "api://$clientId"

$scopeId = [guid]::NewGuid().Guid
$body = @{
  api = @{
    requestedAccessTokenVersion = 2
    oauth2PermissionScopes = @(
      @{
        adminConsentDescription = "Access the personal assistant API"
        adminConsentDisplayName = "Access the personal assistant API"
        id = $scopeId
        isEnabled = $true
        type = "User"
        userConsentDescription = "Access the personal assistant API"
        userConsentDisplayName = "Access the personal assistant API"
        value = "user_impersonation"
      }
    )
  }
  web = @{
    implicitGrantSettings = @{
      enableIdTokenIssuance = $true
      enableAccessTokenIssuance = $false
    }
  }
} | ConvertTo-Json -Depth 6 -Compress

$graphToken = (
  az account get-access-token --resource-type ms-graph |
    ConvertFrom-Json
).accessToken

Invoke-RestMethod `
  -Method Patch `
  -Uri "https://graph.microsoft.com/v1.0/applications/$($app.id)" `
  -Headers @{ Authorization = "Bearer $graphToken" } `
  -ContentType "application/json" `
  -Body $body | Out-Null
```

The delegated scope is `api://<client-id>/user_impersonation`. `enableIdTokenIssuance` supports the hybrid flow used by Easy Auth. Without it, the callback can fail with `AADSTS700054`.

Create a short-lived credential for the authentication provider. Keep its lifetime within the policy of your tenant:

```powershell
$endDate = (Get-Date).ToUniversalTime().AddDays(30).ToString(
  "yyyy-MM-ddTHH:mm:ssZ"
)

$credential = az ad app credential reset `
  --id $clientId `
  --append `
  --display-name container-app-easy-auth `
  --end-date $endDate | ConvertFrom-Json
```

Some tenants require administrator consent. Follow that policy. The client secret is an operational credential, so schedule rotation before it expires.

## 10. Configure an isolated AZD environment

Authenticate both command-line tools and select the correct subscription:

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>
azd auth login
```

Create an environment and set its parameters:

```powershell
azd env new personal-assistant-dev
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION eastus2
azd env set AZURE_SEARCH_LOCATION eastus
azd env set AUTH_CLIENT_ID $clientId
azd env set AUTH_CLIENT_SECRET $credential.password

$credential = $null
```

Set `AZURE_LOCATION` and `AZURE_SEARCH_LOCATION` to the same region when possible. The two-region example is a capacity workaround, not the default architecture.

`azure.yaml` contains:

```yaml
services:
  api:
    project: .
    host: containerapp
    language: docker
    docker:
      path: Dockerfile
      context: .
      remoteBuild: true
```

AZD sends the build context to ACR and injects the resulting `SERVICE_API_IMAGE_NAME` into Bicep. This removes the local Docker requirement and prevents a later `azd provision` from restoring a placeholder image.

### Do not forget AZD's local secret state

`AUTH_CLIENT_SECRET` is a secure Bicep parameter and becomes a Container App secret. It is not committed to the repository.

There is still a local copy to manage. `azd env set` writes values to `.azure/<environment>/.env` as unencrypted text. The lab ignores `.azure/` in Git, but `.gitignore` is not encryption. Restrict access to that directory and clear the value after provisioning:

```powershell
azd env set AUTH_CLIENT_SECRET ''
```

AZD 1.24.1 has no `env unset` command. Setting an empty string clears the sensitive value while leaving the key. Before a later Easy Auth update, create a new credential, set it in the environment, run `azd provision`, and clear the local value again.

## 11. Validate before provisioning

Compile the Bicep and run all 12 tests:

```powershell
az bicep build --file infra\main.bicep --stdout | Out-Null
pytest -q
```

Then inspect and package the deployment:

```powershell
azd provision --preview --no-prompt
azd package --no-prompt
```

A preview validates the template but does not reserve Search capacity or model quota. Either resource can still fail during deployment if regional availability changes.

## 12. Deploy with a remote ACR build

With the environment validated:

```powershell
azd up
```

This provisions the resources, builds the container image remotely in ACR, and deploys the API. The `API_URL` output already includes `https://`.

Register the callback URL after the first deployment:

```powershell
$appUrl = azd env get-value API_URL

az ad app update `
  --id $clientId `
  --web-redirect-uris "$appUrl/.auth/login/aad/callback"

Start-Process $appUrl
```

The browser redirects to Microsoft sign-in and returns to the chat interface. The page displays RAG sources, can call the metrics tool, and shows a confirmation button for a pending action.

For later code-only changes:

```powershell
azd deploy api
```

At startup, the lab creates the Search index and ingests Markdown files from `/app/docs/runbooks`. The `Dockerfile` sets `DOCS_PATH` explicitly because the installed Python package and copied runbooks live in different paths.

The first startup may take time while the app creates embeddings and waits for role assignments to propagate. The startup probe allows up to 30 checks at 10-second intervals. Bootstrap failures still appear in the logs instead of being hidden behind a misleading health response.

## 13. Check RBAC and keyless authentication

The system-assigned Container App identity receives:

| Resource | Role |
|----------|------|
| Azure OpenAI | Cognitive Services OpenAI User |
| Azure AI Search | Search Service Contributor |
| Azure AI Search | Search Index Data Contributor |

The user-assigned pull identity receives `AcrPull`. ACR has `adminUserEnabled=false` and enables Microsoft Entra authentication for ARM.

These Search permissions support startup bootstrap in the lab. After moving ingestion out of the API, replace them with Search Index Data Reader for the runtime identity.

Azure AI Search and Azure OpenAI both set `disableLocalAuth=true`. The code and Container App environment contain no service API keys. Development uses the Azure CLI through `DefaultAzureCredential`; Azure uses `ManagedIdentityCredential`.

Easy Auth accepts these audiences:

```text
<client-id>
api://<client-id>
```

The configuration also restricts app-only tokens to the authorized client ID. The provider secret remains in the Container App secret store and must be rotated. User assignment and consent rules still come from your tenant.

## 14. Trace the flow in Application Insights

The Bicep passes `APPLICATIONINSIGHTS_CONNECTION_STRING` to the container. The Azure Monitor OpenTelemetry distribution configures itself only when that setting exists:

```python
from azure.monitor.opentelemetry import configure_azure_monitor


if config.applicationinsights_connection_string:
    configure_azure_monitor(
        connection_string=config.applicationinsights_connection_string
    )
```

The application creates spans around chat, RAG, and tool execution. It records counts, backend names, session ID length, and whether a pending action exists. It does not put the user's message body into telemetry attributes.

That avoids turning Application Insights into a prompt archive. The action audit trail is intentionally different. It records actor, action type, severity, title, and result. Resource names may appear there, so retention and access controls must match the sensitivity of operational data.

In the smoke test, `chat.request`, `rag.search`, and `tool.execute` appeared in `dependencies`. The incident flow emitted `pending_action_created`, `pending_action_confirmed`, and `pending_action_result`.

Useful KQL queries:

```kusto
dependencies
| where name in ("chat.request", "rag.search", "tool.execute")
| summarize calls=count(), failures=countif(success == false) by name
| order by failures desc
```

```kusto
traces
| where message startswith "audit_event=pending_action"
| project timestamp, message
| order by timestamp desc
```

## 15. Run the end-to-end validation

Get the deployed URL and check the anonymous health endpoint:

```powershell
$appUrl = azd env get-value API_URL

Invoke-RestMethod "$appUrl/healthz"
```

Open `$appUrl` in a browser window with no existing session. Microsoft sign-in should appear, then return to the chat UI. An unauthenticated API request to `/chat` should receive an authentication challenge. In the validated environment, `curl` received `401`.

For automated calls, obtain a token issued for the App Registration. Do not put a client secret in the repository or leave it in shell history. Also remember that `.azure/<environment>/.env` retains the value until you run:

```powershell
azd env set AUTH_CLIENT_SECRET ''
```

Test the deployed behavior in this order:

1. ask a runbook-only question and inspect its citations;
2. ask for resource metrics and verify the read tool result;
3. request an incident and verify that `/chat` returns a pending action;
4. confirm there is no completed incident result or `pending_action_result` audit event before approval;
5. try to confirm as another actor and expect `403`;
6. confirm as the requesting actor;
7. repeat confirmation and verify the same `incident_id`;
8. inspect Application Insights for request, confirmation, and result events.

In my validation environment, interactive sign-in returned to the UI, RAG returned three citations, and the metrics tool answered. The incident request displayed a confirmation control and created the mock incident only after the click. The Container App ran in single-revision mode with one replica and 100 percent of traffic.

## Where Redis and Cosmos DB fit

[Azure Cache for Redis is being retired](https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq). For a new implementation, plan for [Azure Managed Redis](https://learn.microsoft.com/azure/redis/overview).

Azure Managed Redis uses Microsoft Entra ID by default. Its token scope is:

```text
https://redis.azure.com/.default
```

The client uses the managed identity object ID as the user name and an access token as the password. That token expires. A production client has to renew it and deal with pooled connections rather than obtaining one token at startup and keeping it forever.

The agent already depends on a protocol:

```python
class ConversationMemoryStore(Protocol):
    def append(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None: ...

    def get_history(
        self,
        session_id: str,
    ) -> list[dict[str, str]]: ...
```

An Azure Managed Redis implementation can replace the in-memory store without changing the agent. Pending actions also need shared, durable storage before scaling to more than one replica.

Cosmos DB vector search is a reasonable option for long-term memory, but the container design needs explicit decisions:

- partition key;
- vector policy;
- embedding dimensions;
- vector index type;
- time to live and deletion policy;
- consent for storing preferences;
- user or tenant isolation.

Vector policies and vector indexes cannot be changed in place after a Cosmos DB container is created. Decide them before loading data. I would add long-term memory only after measuring which facts users retrieve often enough to justify storing.

## Changes I would make before production

This slice proves the boundaries, not production readiness. My next changes would be:

- persist conversations and pending actions outside the process;
- move Search ingestion to a separate job or pipeline;
- enforce document-level access control in Search;
- replace mock metrics with a tightly scoped Azure Monitor adapter;
- connect an ITSM system with durable idempotency;
- add private endpoints where network isolation requires them;
- add retrieval, groundedness, and tool-selection evaluations;
- define per-user retention and deletion for memory;
- apply rate limits by authenticated identity;
- rotate the Easy Auth credential automatically.

The useful outcome is a precise list of what remains. Three successful chat answers do not make a system production ready.

## Clean up

When you are finished, retrieve the resource group created by AZD and delete it:

```powershell
$resourceGroup = azd env get-value AZURE_RESOURCE_GROUP

az group delete `
  --name $resourceGroup `
  --yes `
  --no-wait
```

Check the resource group first and make sure it contains nothing you need to keep. Removing the resource group does not remove the App Registration. Delete that separately when you no longer need it, and revoke any remaining credential.

## References

- [Companion personal assistant implementation](https://github.com/ricmmartins/agentic-infra-handbook/tree/master/labs/personal-assistant)
- [Lab README: deploy to Azure step by step](https://github.com/ricmmartins/agentic-infra-handbook/tree/master/labs/personal-assistant#deploy-to-azure-step-by-step)
- [Azure OpenAI with Microsoft Entra ID](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/managed-identity)
- [Azure OpenAI v1 API](https://learn.microsoft.com/azure/ai-foundry/openai/api-version-lifecycle)
- [Responses API](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses)
- [Deploy Container Apps with Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/container-apps-workflows)
- [Create a vector index in Azure AI Search](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index)
- [Hybrid search in Azure AI Search](https://learn.microsoft.com/azure/search/hybrid-search-how-to-query)
- [Semantic ranking in Azure AI Search](https://learn.microsoft.com/azure/search/semantic-how-to-configure)
- [Azure AI Search roles](https://learn.microsoft.com/azure/search/search-security-rbac)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity)
- [Container Apps authentication with Microsoft Entra ID](https://learn.microsoft.com/azure/container-apps/authentication-entra)
- [Pull from ACR with managed identity](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull)
- [Azure Managed Redis](https://learn.microsoft.com/azure/redis/overview)
- [Microsoft Entra authentication for Azure Managed Redis](https://learn.microsoft.com/azure/redis/entra-for-authentication)
- [Vector search in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/vector-search)
- [OpenTelemetry in Application Insights](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable)
