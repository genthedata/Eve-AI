# Eve Cater's AI — Smart Catering Assistant by iNextLabs

**Eve Cater's AI** is an intelligent, multi-agent catering operations platform built for Southeast Asia. It combines a structured customer-facing chat assistant (Eve) with a powerful backend of 6 specialist AI agents, 38 knowledge bases, RAG-lite retrieval, inventory simulation, and optional LLM reasoning.

---

## What this system does

- **Eve** guides customers through a full catering booking via a structured 5-option menu — choosing event type, menu style, date, service style, and generating a booking receipt with a unique Booking ID
- **6 specialist agents** plan menus, source inventory, set prices, plan logistics, and monitor risks — each powered by curated YAML knowledge bases
- **38 YAML knowledge bases** across 6 domains (customer, menu, inventory, logistics, pricing, shared) give every agent deep, structured domain knowledge
- **RAG-lite retrieval** (`YAMLKBSearch`) retrieves the most relevant KB records per query using keyword overlap — no embedding dependencies
- **Optional LLM reasoning** on any agent via Ollama, OpenAI-compatible, or Azure OpenAI
- **Microsoft AutoGen** optional group-chat mode for multi-agent conversation
- **Live inventory simulation** with random stock depletion and vendor delay events

---

## Architecture overview

```text
Customer (Terminal 2)
        │
        ▼
Eve Cater's AI (app/chat.py)
  • Menu-driven chat  (5 options)
  • Booking state machine
  • Date availability engine
  • Booking receipt generator (EVE-YYYYMMDD-XXXXX)
        │
        ▼  HTTP POST /invocations
API Server (app/main.py → app/runtime/api.py)
        │
        ▼
Orchestrator (app/orchestrator.py)
  • DAG task decomposition
  • Provider injection
  • Plan assembly & narrative
        │
    ┌───┴────────────────────────────────────────┐
    ▼          ▼           ▼          ▼          ▼           ▼
Customer    Menu        Inventory  Logistics  Pricing    Monitoring
 Agent      Agent         Agent      Agent     Agent       Agent
    │          │             │          │         │            │
    └──────────┴─────────────┴──────────┴─────────┴────────────┘
                              │
                    Knowledge Bases (38 YAML files)
                    RAG-lite YAMLKBSearch retrieval
```

---

## Project structure

```text
app/
  main.py                   ← Terminal 1: starts the API server
  chat.py                   ← Terminal 2: Eve Cater's AI customer chat
  orchestrator.py           ← DAG orchestrator, plan assembly
  models.py                 ← AgentMessage schema
  contracts.py

  agents/
    llm_mixin.py            ← Shared LLM reasoning mixin for all agents
    customer_agent.py       ← 8-step intake pipeline → structured event brief
    menu_agent.py           ← 7-step menu planning → menu plan + ingredient brief
    inventory_agent.py      ← 8-step procurement pipeline via demand_planner.py
    logistics_agent.py      ← 8-step logistics pipeline → runsheet + transport plan
    pricing_agent.py        ← 7-step pricing pipeline → tiered quotes + margin summary
    monitoring_agent.py     ← Risk detection + LLM executive briefing

  tools/
    kb_yaml.py              ← YAMLKBSearch: loads & queries all YAML KBs
    demand_planner.py       ← Inventory agent intelligence core (8-step RAG pipeline)
    recipe_catalogue.py
    inventory_db.py         ← Granular ingredient stock management
    inventory_simulation.py ← Random stock depletion + vendor delay events
    pricing_engine.py
    scheduler_api.py
    currency.py
    registry.py
    web_search.py

    data/
      recipes.json          ← Legacy 34-dish recipe data
      suppliers.json        ← Legacy 10 SEA supplier records
      kb/                   ← 38 YAML knowledge bases (see below)

  providers/
    __init__.py             ← build_provider() factory
    ollama.py
    openai_compatible.py
    azure_openai.py
    mock_provider.py
    base.py

  runtime/
    api.py                  ← FastAPI + Uvicorn
    router.py               ← AutoGen-first routing with DAG fallback
    ms_autogen_adapter.py   ← Microsoft AutoGen group-chat adapter
    auth.py
    logging_config.py

  context/
    store.py                ← In-memory shared plan context
    cosmos_store.py         ← Azure Cosmos DB stub
    memory_store.py
    catering_plan_context.py

docs/
  architecture-microsoft-agent-framework.md
requirements.txt
.env.example
```

---

## Knowledge base structure (38 YAML files)

Each agent has its own curated knowledge bases. All are loaded and queried by `YAMLKBSearch` using RAG-lite keyword retrieval.

### Customer Agent KBs (`kb/customer/`)
| File | What it contains |
|------|-----------------|
| `event_profiles.yaml` | Rich templates for 15+ event types — clarifying questions, menu anchors, cultural defaults, service style recommendations |
| `dietary_restrictions.yaml` | 10 dietary profiles with allergen severity, cross-contamination rules, combined profile logic |
| `interaction_history.yaml` | CRM-style client records with VIP tier, lifetime spend, payment reliability, agent notes |
| `cultural_norms.yaml` | Operational guidance for Malay, Chinese, Indian, Filipino, and Western events — prayer scheduling, seating customs, taboos |
| `service_packages.yaml` | 5 service tiers with per-head pricing, matching rules, and inclusions |
| `faq_policies.yaml` | Machine-readable business policies — cancellation, deposit, dietary commitments |

### Menu Planning Agent KBs (`kb/menu/`)
| File | What it contains |
|------|-----------------|
| `recipe_library.yaml` | 30+ dishes with equipment requirements, scale performance, allergens, dietary variants, occasion suitability, dish compatibility |
| `cuisine_trends.yaml` | 7 current SEA food trends, menu balance templates per event type, flavour pairing rules, amateurism red flags |
| `portion_yield.yaml` | Empirical consumption data by event type and demographic — buffet replenishment rules, dish-specific yield notes |
| `equipment_capability.yaml` | Owned equipment specs, venue constraint profiles, technique-to-equipment mapping, capacity rules by PAX |
| `menu_performance.yaml` | 7 past menu records with satisfaction scores, dish feedback, lessons learned, proven menu combinations |

### Inventory Agent KBs (`kb/inventory/`)
| File | What it contains |
|------|-----------------|
| `ingredient_recipe_map.yaml` | 36 dishes mapped to raw ingredient quantities and procurement keys |
| `supplier_catalog.yaml` | Enriched supplier records with products, pricing, credit limits, substitution maps |
| `vendor_performance.yaml` | Historical supplier performance with selection weights |
| `spoilage_waste.yaml` | Event-level waste logs and aggregate insights for dynamic waste buffers |
| `procurement_sop.yaml` | Preferred vendor priorities, blacklisted vendors, purchasing procedures |

### Logistics Agent KBs (`kb/logistics/`)
| File | What it contains |
|------|-----------------|
| `venue_profiles.yaml` | Detailed dossier for 6 venues (MY + PH) — GPS, loading dock clearance, vehicle height limits, kitchen specs, service lift dimensions, learned operational constraints |
| `route_transport.yaml` | 6 common routes with normal vs. peak travel times (e.g. Shah Alam → Putrajaya: 35min normal / 70min Friday PM), toll costs, vehicle fleet specs, delivery scheduling rules |
| `food_safety.yaml` | Temperature requirements per food category, max holding times, 2-hour danger zone rule, cold chain loading sequence, outdoor event rules |
| `staff_scheduling.yaml` | 11 staff roles with ratios and certifications, named roster with cert expiry tracking, 6 staffing models by event size |
| `runsheet_templates.yaml` | 4 minute-by-minute event timeline templates (Malay Wedding, Corporate Plated, Cocktail, Birthday Buffet) with critical path milestones and adaptation rules |
| `execution_logs.yaml` | 4 post-event records with planned vs. actual timelines, incident reports, root causes, corrective actions, and aggregated learnings by venue |
| `equipment_inventory.yaml` | Full equipment list with dimensions, weight, stacking rules, vehicle assignment, setup sequence priority, 3 loading plans by event size, double-booking detection rules |
| `compliance_permits.yaml` | Business licences by country, temporary permits with lead-time alerts (14-day outdoor permit rule), food handler cert requirements, fire safety rules, insurance requirements, compliance trigger rules |

### Pricing Agent KBs (`kb/pricing/`)
| File | What it contains |
|------|-----------------|
| `cost_of_goods.yaml` | Ingredient pricing (MYR/PHP/SGD) with seasonal risk, drift alerts, dish benchmarks, service style multipliers, minimum food cost per head |
| `overhead_labour.yaml` | Staff hourly rates (8 roles), vehicle costs, equipment rental, utilities, 7 event staffing models, overhead quick reference by PAX tier |
| `market_benchmarks.yaml` | 12 benchmark entries across Malaysia, Philippines, Singapore — per-head ranges by event type, region, guest count tier, service style uplifts |
| `historical_quotes.yaml` | 10 past quotes with accepted/rejected outcomes, actual margins, variance drivers, lessons learned, win rate curves by price point |
| `discount_rules.yaml` | Loyalty, volume, package bundling, off-peak, early booking, and referral discounts; margin floors (10% absolute, 15% recommended); stacking rules |
| `price_elasticity.yaml` | Conversion curves for 6 event types, elasticity coefficients, sweet spot analysis, client segment price sensitivity, seasonal demand multipliers |

### Shared KBs (`kb/shared/`)
| File | Used by |
|------|---------|
| `venue_index.yaml` | Customer Agent, Logistics Agent |
| `seasonal_availability.yaml` | Menu Agent, Pricing Agent |
| `guest_feedback.yaml` | Monitoring Agent, Menu Agent |
| `competitor_pricing.yaml` | Pricing Agent |
| `event_postmortems.yaml` | Logistics Agent, Monitoring Agent |
| `sop_compliance.yaml` | All agents |
| `social_trends.yaml` | Menu Agent |
| `carbon_footprint.yaml` | Monitoring Agent |

---

## Setup (first time only)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

---

## Running the system (two terminals)

### Terminal 1 — start the agent server

```powershell
cd c:\Users\gen.david\test\cwb
.venv\Scripts\activate
python -m app.main
```

You should see:

```
[Catering Agent Runtime] Starting on http://127.0.0.1:8000
  Docs: http://127.0.0.1:8000/docs
  In another terminal run:  python -m app.chat
```

Keep this terminal running. The server auto-reloads when you edit code.

---

### Terminal 2 — Eve Cater's AI (customer chat)

```powershell
cd c:\Users\gen.david\test\cwb
.venv\Scripts\activate
python -m app.chat
```

Eve opens with a structured menu:

```
  ╔══════════════════════════════════════════════════════════╗
  ║           Eve Cater's AI —  iNextLabs 💚              ║
  ╚══════════════════════════════════════════════════════════╝

  Eve: Hi, I'm Eve! I'm iNextLabs' smart catering assistant! 😊
       Choose the below options so we can start.

    1.  New Customer
    2.  View my booking
    3.  Browse catalogue for ideas
    4.  How do I use Eve Cater's AI?
    5.  Chat with a staff
```

### Option 1 — New Customer (booking flow)

Eve guides through 11 structured steps before generating a receipt:

| Step | What Eve asks | Validation |
|------|--------------|-----------|
| 1 | Country | SEA countries only (MY, PH, SG, ID, TH, VN, MM, KH, BN, LA) |
| 2 | Event type | 17 types + custom fallback; accepts numbers, keywords, or natural language |
| 3 | Menu preferences | Free text, or type `suggest` for 3 curated ideas per event type |
| 4 | Event date | May & June 2026 only; blocked dates rejected with nearby alternatives; `show May` / `show June` shows calendar |
| 5 | Event time | Any format: `7pm`, `19:00`, `7:30 PM` |
| 6 | Number of guests | 10–5,000 pax |
| 7 | Dietary requirements | Halal, vegetarian, vegan, etc. — or `none` |
| 8 | Service style | Buffet / Semi-Buffet / Plated / Cocktail |
| 9 | Budget per head | Shows market range (budget / standard / premium) for the event type |
| 10 | Full name | Required |
| 11 | WhatsApp number | Required — staff contacts here after booking |

After all steps, Eve shows a numbered summary. The customer can type any field number to edit it, or `confirm` to finalise. A booking receipt is then generated:

```
  ╔══════════════════════════════════════════════════════════╗
  ║           EVE CATER'S AI — BOOKING RECEIPT 🎉           ║
  ╚══════════════════════════════════════════════════════════╝

  Booking ID   : EVE-20260515-V6JG0
  Status       : ✅ Confirmed — Awaiting Staff Confirmation

  ── EVENT DETAILS ─────────────────────────────────────────
  Event        : Malay Wedding
  Date & Time  : Friday, 15 May 2026 at 7:00 PM
  Country      : Malaysia
  Guests       : 350 pax
  Service      : Buffet
  Dietary      : Halal
  ...
  ── NEXT STEPS ────────────────────────────────────────────
  ✅  A staff member will contact you via WhatsApp
       at +60123456789 within 24 hours to confirm your
       booking and arrange final payment.
```

### Option 2 — View my booking

Enter a Booking ID (`EVE-YYYYMMDD-XXXXX`) to retrieve the full receipt.

### Option 3 — Browse catalogue

5 curated event packages displayed with descriptions, pricing, capacity, and highlights. Type a package number to start booking it directly.

### Option 4 — How do I use Eve Cater's AI?

A 10-item bullet-point feature guide covering all capabilities.

### Option 5 — Chat with a staff

WhatsApp numbers, email, office hours, and website shown for direct staff contact.

### Navigation

| Input | Action |
|-------|--------|
| `back` | Go to previous booking step |
| `menu` or `home` | Return to main menu (at any point) |
| `quit` or `exit` | Leave Eve Cater's AI |

---

## Agent pipelines

Each specialist agent runs a structured multi-step pipeline using its knowledge bases:

| Agent | Steps | Key output |
|-------|-------|-----------|
| **Customer** | 8 steps: profile → dietary → cultural → packages → venue → FAQ → summary → brief | Structured event brief for all downstream agents |
| **Menu Planning** | 7 steps: dietary filter → recipe filter → trends & balance → portions → seasonal → equipment → performance | Menu plan + ingredient brief for inventory |
| **Inventory** | 8 steps: menu → ingredients → stock check → vendor selection → spoilage buffer → order list → risk check → SOP | Procurement plan + supplier assignments |
| **Logistics** | 8 steps: venue → runsheet → staffing → routes → equipment → food safety → compliance → execution logs | Staffing schedule + transport manifest + compliance checklist |
| **Pricing** | 7 steps: food cost → overheads → seasonal → market benchmarks → discounts → historical validation → elasticity | Tiered quotes (value/standard/premium) + margin summary |
| **Monitoring** | Risk detection → escalations → LLM executive briefing | Risk flags + escalation list |

---

## Supported currencies

| Currency | Example inputs |
|----------|----------------|
| MYR (Malaysian Ringgit) | `88`, `MYR 88`, `RM 88` |
| PHP (Philippine Peso) | `1800 PHP`, `1800 peso` |
| SGD (Singapore Dollar) | `220 SGD`, `S$ 220` |
| IDR (Indonesian Rupiah) | `350000 IDR`, `Rp 350000` |
| THB (Thai Baht) | `680 THB`, `680 baht` |
| VND (Vietnamese Dong) | `450000 VND` |
| BND (Brunei Dollar) | `220 BND` |
| KHR (Cambodian Riel) | `80000 KHR` |
| LAK (Lao Kip) | `1500000 LAK` |
| MMK (Myanmar Kyat) | `200000 MMK` |

---

## Environment variables

Copy `.env.example` to `.env` and configure what you need.

### LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `mock` | `mock` \| `ollama` \| `openai_compatible` \| `azure_openai` |
| `MODEL_NAME` | `llama3.1` | Model name (e.g. `llama3.1`, `gpt-4o-mini`, `mistral`) |
| `MODEL_ENDPOINT` | `http://localhost:11434` | API endpoint for Ollama or OpenAI-compatible |
| `MODEL_API_KEY` | *(empty)* | Bearer key for OpenAI-compatible or Azure |
| `USE_LLM` | `false` | Enable LLM reasoning on all agents |

### Orchestration

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_AUTOGEN` | `false` | Use Microsoft AutoGen group-chat instead of deterministic DAG |

### Simulation

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATE_INVENTORY` | `false` | Apply random stock depletion events each run |
| `SIMULATE_VENDOR_DELAY` | `false` | Inject a vendor delay event for the top ingredient |
| `SIM_SEED` | *(empty)* | Integer seed for reproducible simulation results |

### Azure OpenAI

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | Default: `2024-08-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT_ORCH` | Deployment for orchestrator (default: `gpt-4o`) |
| `AZURE_OPENAI_DEPLOYMENT_SPECIALIST` | Deployment for specialists (default: `gpt-4o-mini`) |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `STRUCTURED_LOG_JSON` | `1` | Emit JSON-formatted logs (for App Insights) |
| `ENABLE_OTEL` | `0` | Enable OpenTelemetry FastAPI instrumentation |
| `ENTRA_AUDIENCE` | *(empty)* | Require Entra ID Bearer tokens when set |
| `AGENT_API_URL` | `http://127.0.0.1:8000` | Agent server URL (for Eve chat client) |

---

## Quick-start recipes

### Run with a local Ollama model

```powershell
# Pull a model first
ollama pull llama3.1

# In .env
MODEL_PROVIDER=ollama
MODEL_NAME=llama3.1
USE_LLM=true
```

### Run with OpenAI / Groq / Together

```powershell
# In .env
MODEL_PROVIDER=openai_compatible
MODEL_NAME=gpt-4o-mini
MODEL_ENDPOINT=https://api.openai.com/v1
MODEL_API_KEY=sk-...
USE_LLM=true
```

### Enable Microsoft AutoGen group-chat

```powershell
pip install autogen-agentchat autogen-ext[openai]

# In .env
USE_AUTOGEN=true
MODEL_PROVIDER=openai_compatible   # or ollama / azure_openai
USE_LLM=true
```

### Enable live inventory simulation

```powershell
# In .env
SIMULATE_INVENTORY=true
SIMULATE_VENDOR_DELAY=true
```

---

## API response shape

| Field | Description |
|-------|-------------|
| `thread_id` | UUID for this catering session |
| `message_trace` | Agent-to-agent messages; each carries `reasoning`, `kb_sources`, `simulation_events` |
| `final_report.recommended_menu` | Menu items + `kb_sources` showing which KB documents were retrieved |
| `final_report.procurement_plan` | Ingredients, shortages, procurement list + supplier assignments |
| `final_report.logistics_plan` | Staffing schedule, transport manifest, runsheet, compliance checklist |
| `final_report.cost_and_pricing` | Tiered quotes (value/standard/premium) + margin summary in the customer's chosen currency |
| `final_report.monitoring` | Risks, escalations, optional LLM executive briefing |
| `final_report.orchestrator_plan_narrative` | 3-bullet LLM summary (when `USE_LLM=true`) |

---

## Optional packages

| Package | When needed |
|---------|-------------|
| `autogen-agentchat autogen-ext[openai]` | `USE_AUTOGEN=true` |
| `opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi` | `ENABLE_OTEL=1` |
| `PyJWT cryptography` | `ENTRA_AUDIENCE` set |
