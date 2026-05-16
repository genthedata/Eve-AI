# Azure AI Foundry–style catering architecture (in-repo)

This document maps the **Azure AI Foundry hub** diagram to concrete modules in this repository: input, orchestrator, specialist agents, tools, shared context, monitoring, and platform hooks.

## Layer mapping

### 1. Input layer

- **Customer / organiser**: JSON file ([sample_input.json](c:\Users\gen.david\test\cwb\sample_input.json)), `POST /invocations`, or `POST /a2a/messages` with `start_catering_flow`.
- **Thread id**: Optional `thread_id` on [InvocationRequest](c:\Users\gen.david\test\cwb\app\contracts.py); otherwise the server generates a UUID. Returned as `thread_id` and `correlation_id` in [InvocationResponse](c:\Users\gen.david\test\cwb\app\contracts.py).

### 2. Orchestration layer

- **Orchestrator agent**: [app/orchestrator.py](c:\Users\gen.david\test\cwb\app\orchestrator.py) — fixed DAG for MVP: decompose (declared steps) → route specialists → persist context after each step → assemble `final_report`.
- **Optional plan narrative**: When `USE_LLM=true`, the orchestrator may call [app/providers/azure_openai.py](c:\Users\gen.david\test\cwb\app\providers\azure_openai.py) for a short client-facing summary. Core numbers remain deterministic from tools.

### 3. Agents layer

| Agent | Module | Role |
|--------|--------|------|
| Customer | [app/agents/customer_agent.py](c:\Users\gen.david\test\cwb\app\agents\customer_agent.py) | Intake and parse |
| Menu | [app/agents/menu_agent.py](c:\Users\gen.david\test\cwb\app\agents\menu_agent.py) | Dishes and portions (via recipe tool) |
| Inventory | [app/agents/inventory_agent.py](c:\Users\gen.david\test\cwb\app\agents\inventory_agent.py) | Stock and procurement (via inventory DB tool) |
| Logistics | [app/agents/logistics_agent.py](c:\Users\gen.david\test\cwb\app\agents\logistics_agent.py) | Timeline and staff (via scheduler tool) |
| Pricing | [app/agents/pricing_agent.py](c:\Users\gen.david\test\cwb\app\agents\pricing_agent.py) | Cost and quote (via pricing engine tool) |
| Monitoring | [app/agents/monitoring_agent.py](c:\Users\gen.david\test\cwb\app\agents\monitoring_agent.py) | Aggregates risks and escalations from context |

### 4. Tools layer

| Tool | Module | Diagram analogue |
|------|--------|------------------|
| Recipe catalogue | [app/tools/recipe_catalogue.py](c:\Users\gen.david\test\cwb\app\tools\recipe_catalogue.py) + [app/tools/data/recipes.json](c:\Users\gen.david\test\cwb\app\tools\data\recipes.json) | Menu knowledge base |
| Inventory DB | [app/tools/inventory_db.py](c:\Users\gen.david\test\cwb\app\tools\inventory_db.py) | Inventory DB |
| Scheduler API | [app/tools/scheduler_api.py](c:\Users\gen.david\test\cwb\app\tools\scheduler_api.py) | Scheduler API |
| Pricing engine | [app/tools/pricing_engine.py](c:\Users\gen.david\test\cwb\app\tools\pricing_engine.py) | Pricing engine |
| Registry | [app/tools/registry.py](c:\Users\gen.david\test\cwb\app\tools\registry.py) | Bundles tools for injection |

### 5. Shared context (thread storage / Cosmos)

- **In-memory default**: [app/context/memory_store.py](c:\Users\gen.david\test\cwb\app\context\memory_store.py).
- **Cosmos placeholder**: [app/context/cosmos_store.py](c:\Users\gen.david\test\cwb\app\context\cosmos_store.py) — when `AZURE_COSMOS_ENDPOINT` is set, the store class is selected by [app/orchestrator.py](c:\Users\gen.david\test\cwb\app\orchestrator.py) `default_context_store()`; persistence still uses the in-process fallback until the Azure Cosmos SDK is wired.
- **Context model**: [app/context/catering_plan_context.py](c:\Users\gen.david\test\cwb\app\context\catering_plan_context.py) — single object updated after each specialist step; snapshot included in `final_report.shared_context_snapshot`.

### 6. Platform layer (Azure)

Provisioned in Azure (not created by this repo alone):

- **Model deployments**: Map to `AZURE_OPENAI_DEPLOYMENT_ORCH` (orchestrator-style, e.g. GPT-4o) and `AZURE_OPENAI_DEPLOYMENT_SPECIALIST` (e.g. GPT-4o-mini). Endpoints and keys: see [.env.example](c:\Users\gen.david\test\cwb\.env.example).
- **Observability**: [app/runtime/logging_config.py](c:\Users\gen.david\test\cwb\app\runtime\logging_config.py) emits JSON lines to stdout (`STRUCTURED_LOG_JSON=1`) suitable for collection into **Azure Monitor / Application Insights**. Optional `ENABLE_OTEL=1` with OpenTelemetry FastAPI instrumentation in [app/runtime/api.py](c:\Users\gen.david\test\cwb\app\runtime\api.py).
- **Security**: [app/runtime/auth.py](c:\Users\gen.david\test\cwb\app\runtime\auth.py) — when `ENTRA_AUDIENCE` is set, `POST /invocations` and `POST /a2a/messages` require a valid **Entra ID** bearer JWT (configure `ENTRA_TENANT_ID` as needed for issuer discovery).

## Runtime API

- [app/runtime/api.py](c:\Users\gen.david\test\cwb\app\runtime\api.py): `GET /health`, `POST /invocations`, `POST /a2a/messages`.
- [app/runtime/router.py](c:\Users\gen.david\test\cwb\app\runtime\router.py): routes invocations to the orchestrator with `thread_id`.

## Request flow (summary)

1. Client sends structured event payload (+ optional `thread_id`).
2. Orchestrator records decomposed plan message, runs specialists in order.
3. After each step, **CateringPlanContext** is saved via **ContextStore**.
4. Monitoring runs on full context; result is merged into `final_report`.
5. Response returns **message_trace**, **final_report** (including **monitoring** and **shared_context_snapshot**), and **thread_id**.

## Microsoft Agent Framework (future workers)

- [app/runtime/ms_autogen_adapter.py](c:\Users\gen.david\test\cwb\app\runtime\ms_autogen_adapter.py) remains a hook to swap in-process execution for **AutoGen** (or other Microsoft agent runtime) workers while keeping the same contracts.
