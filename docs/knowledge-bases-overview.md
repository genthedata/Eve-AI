# Eve Cater's AI — Knowledge Bases Overview

Eve Cater's AI uses **38 structured YAML knowledge bases (KBs)** under `app/tools/data/kb/`. They give specialist agents real catering domain data—menus, suppliers, venues, pricing, culture, and compliance—without hard-coding everything in Python.

**Loader & search:** `YAMLKBSearch` in `app/tools/kb_yaml.py` loads all files at startup and exposes keyword-overlap **RAG-lite** search (`search`, `search_scope`, `search_multi`, `get`).

**Future:** When `USE_AZURE_AI_SEARCH=true`, hybrid retrieval can target index `eve-cater-kb` (placeholder in `app/platform/search/`). Until then, YAML + keyword search is authoritative.

---

## How KBs are organised

| Folder | Count | Primary agents |
|--------|------:|----------------|
| `customer/` | 6 | Customer Interaction |
| `menu/` | 5 | Menu Planning |
| `inventory/` | 5 | Inventory & Procurement |
| `logistics/` | 8 | Logistics Planning |
| `pricing/` | 6 | Pricing Optimization |
| `shared/` | 8 | Multiple agents (cross-cutting) |
| **Total** | **38** | |

**KB key format:** path without `.yaml`, e.g. `menu/recipe_library`, `shared/seasonal_availability`.

Each agent records which KBs it used in **`kb_sources`** on its output for traceability.

---

## Retrieval (RAG-lite)

```python
from app.tools.kb_yaml import YAMLKBSearch

kb = YAMLKBSearch()
kb.get("customer/event_profiles")                    # full YAML document
kb.search("menu/cuisine_trends", "halal wedding", top_k=3)
kb.search_scope("shared", "typhoon ingredient risk") # all shared/*.yaml
```

Scoring is **token overlap** on flattened record text (no embeddings required). Lists inside each YAML (e.g. `recipes`, `profiles`, `benchmarks`) are the searchable documents.

---

## Customer agent KBs (6)

Intake, policies, and cultural context—turns vague requests into a structured brief.

| KB key | File | What it contains |
|--------|------|------------------|
| `customer/event_profiles` | `event_profiles.yaml` | Templates per event type (wedding, corporate, birthday, etc.): typical guests, service style, budget bands, clarifying questions, flags for downstream agents. |
| `customer/dietary_restrictions` | `dietary_restrictions.yaml` | Halal, vegan, nut-free, etc.: permitted/forbidden foods, cross-contamination, kitchen rules, combined-profile matrix, allergen severity. |
| `customer/cultural_norms` | `cultural_norms.yaml` | Religious and cultural service rules (prayer timing, seating, symbolism) beyond bare dietary tags. |
| `customer/interaction_history` | `interaction_history.yaml` | CRM-style client records: past events, preferences, complaints, VIP flags, payment behaviour. |
| `customer/service_packages` | `service_packages.yaml` | Product catalog: Silver/Gold packages, inclusions, add-ons, package-matching by guest count and budget. |
| `customer/faq_policies` | `faq_policies.yaml` | Deposits, cancellations, headcount cut-offs, liability—answers the customer agent must quote accurately. |

**Also uses (shared):** `shared/venue_index` for early venue feasibility checks.

---

## Menu agent KBs (5)

Culinary intelligence and constraints—what to cook, how much, and whether the venue can execute it.

| KB key | File | What it contains |
|--------|------|------------------|
| `menu/recipe_library` | `recipe_library.yaml` | Dish catalogue with cuisine, dietary profiles, equipment, service-style fit, scale limits, pairing hints; includes `dietary_filter_index`, `cuisine_index`, `occasion_index`. |
| `menu/cuisine_trends` | `cuisine_trends.yaml` | SEA catering trends, flavour-pairing rules, **menu balance templates** per event (e.g. Malay wedding buffet, corporate plated), quality vs amateurism red flags. |
| `menu/portion_yield` | `portion_yield.yaml` | Real consumption rates by event type and service style, demographic adjustments, buffet replenishment, waste buffers. |
| `menu/equipment_capability` | `equipment_capability.yaml` | Owned/rented equipment, technique→equipment map, dish requirements, **venue constraint profiles** (no gas, outdoor tent, etc.). |
| `menu/menu_performance` | `menu_performance.yaml` | Historical menus and outcomes; dish performance index and proven combos to reuse or avoid. |

**Also uses (shared):** `shared/seasonal_availability`, `shared/guest_feedback`, `shared/social_trends` (where referenced in pipeline).

**Linked:** Inventory uses `inventory/ingredient_recipe_map` (not recipe_library directly) for quantities.

---

## Inventory agent KBs (5)

Procurement and supply—translate menu → ingredients → purchase orders.

| KB key | File | What it contains |
|--------|------|------------------|
| `inventory/ingredient_recipe_map` | `ingredient_recipe_map.yaml` | Per-dish ingredient quantities per adult serving (`procurement_key`, units, prep waste, cold chain). |
| `inventory/supplier_catalog` | `supplier_catalog.yaml` | Suppliers, SKUs, MOQs, lead times, halal flags, substitutions, credit limits. |
| `inventory/vendor_performance` | `vendor_performance.yaml` | On-time delivery, quality incidents, price stability—ranks vendors beyond cheapest price. |
| `inventory/spoilage_waste` | `spoilage_waste.yaml` | Past over-order and spoilage logs; aggregate buffers by event type for demand planning. |
| `inventory/procurement_sop` | `procurement_sop.yaml` | Approval thresholds, preferred vendors, emergency contacts, blacklists. |

**Also uses (shared):** `shared/seasonal_availability` for disruption and price-impact warnings.

---

## Logistics agent KBs (8)

On-the-ground execution—venue, people, transport, safety, permits.

| KB key | File | What it contains |
|--------|------|------------------|
| `logistics/venue_profiles` | `venue_profiles.yaml` | Deep venue dossiers: loading bay, kitchen, power, AC, outdoor rules, learned constraints. |
| `logistics/runsheet_templates` | `runsheet_templates.yaml` | Minute-by-minute timelines (T−/T+) by event type; critical-path tasks. |
| `logistics/staff_scheduling` | `staff_scheduling.yaml` | Roles, certifications, staff:guest ratios, roster, staffing models by service style and scale. |
| `logistics/route_transport` | `route_transport.yaml` | Routes from central kitchens (MY/PH), travel times, fleet specs, loading rules, delivery scheduling. |
| `logistics/food_safety` | `food_safety.yaml` | Holding times, cold chain, transport temperatures, outdoor/humidity rules. |
| `logistics/equipment_inventory` | `equipment_inventory.yaml` | Equipment dimensions, vehicle assignment, setup sequence, **double-booking** prevention. |
| `logistics/compliance_permits` | `compliance_permits.yaml` | Licences, event permits, food-handler certs, fire safety, insurance by country. |
| `logistics/execution_logs` | `execution_logs.yaml` | Post-event ground truth; aggregated learnings per venue and event type. |

**Also uses (shared):** `shared/venue_index`, `shared/sop_compliance`.

---

## Pricing agent KBs (6)

Cost, margin, and competitive quote positioning.

| KB key | File | What it contains |
|--------|------|------------------|
| `pricing/cost_of_goods` | `cost_of_goods.yaml` | Ingredient price list (`procurement_key`), dish benchmarks, drift alerts, service-style multipliers, minimum cost per head. |
| `pricing/overhead_labour` | `overhead_labour.yaml` | Non-food costs: staffing models, transport, ops overhead, quick-reference totals by event scale. |
| `pricing/market_benchmarks` | `market_benchmarks.yaml` | Per-head market tiers (budget / standard / premium) by event, region, cuisine, guest count. |
| `pricing/discount_rules` | `discount_rules.yaml` | Promotions, repeat-client discounts, **margin floors** (never quote below). |
| `pricing/historical_quotes` | `historical_quotes.yaml` | Past quotes with win/loss, actual cost, realised margin—validates new bids. |
| `pricing/price_elasticity` | `price_elasticity.yaml` | Price vs win-rate curves, segment elasticity, expected-value optimisation hints. |

**Also uses (shared):** `shared/seasonal_availability`, `shared/competitor_pricing`.

---

## Shared KBs (8)

Cross-agent intelligence—any specialist can query these when relevant.

| KB key | File | What it contains | Typical consumers |
|--------|------|------------------|-------------------|
| `shared/seasonal_availability` | `seasonal_availability.yaml` | Monthly ingredient availability, festive spikes, typhoon/Eid disruption notes by region. | Menu, Inventory, Pricing |
| `shared/competitor_pricing` | `competitor_pricing.yaml` | Competitor per-head rates and positioning notes. | Pricing, Customer (initial scoping) |
| `shared/event_postmortems` | `event_postmortems.yaml` | Structured lessons learned (what worked / failed) across events. | All agents (RAG queries) |
| `shared/sop_compliance` | `sop_compliance.yaml` | Food safety regs, halal/kosher process standards, alcohol licensing (MY, PH, SG). | Logistics, Customer |
| `shared/venue_index` | `venue_index.yaml` | Lightweight venue compatibility index for early intake. | Customer, Logistics |
| `shared/guest_feedback` | `guest_feedback.yaml` | Survey snippets by dish and event type. | Menu |
| `shared/social_trends` | `social_trends.yaml` | Social/media food trends for “moment-worthy” suggestions. | Menu, Customer (ideas) |
| `shared/carbon_footprint` | `carbon_footprint.yaml` | kg CO₂e per ingredient for optional sustainability scoring. | Menu (optional), Reporting |

---

## KB ↔ agent matrix (quick reference)

| Agent | Own folder KBs | Shared KBs (common) |
|--------|----------------|---------------------|
| **Customer** | All 6 in `customer/` | `venue_index`, `sop_compliance` |
| **Menu** | All 5 in `menu/` | `seasonal_availability`, `guest_feedback`, `social_trends` |
| **Inventory** | All 5 in `inventory/` | `seasonal_availability` |
| **Logistics** | All 8 in `logistics/` | `venue_index`, `sop_compliance`, `event_postmortems` |
| **Pricing** | All 6 in `pricing/` | `seasonal_availability`, `competitor_pricing` |
| **Monitoring** | — (reads agent outputs + context) | Indirect via shortage/seasonal fields in context |

---

## Data location and maintenance

```
app/tools/data/kb/
├── customer/     (6 YAML files)
├── menu/         (5)
├── inventory/    (5)
├── logistics/    (8)
├── pricing/      (6)
└── shared/       (8)
```

**Editing:** Change YAML, restart the app (KBs reload on `YAMLKBSearch()` init). Keep `procurement_key` aligned across `ingredient_recipe_map`, `supplier_catalog`, and `cost_of_goods` when adding ingredients.

**Indexes inside YAML:** Some files (e.g. `recipe_library.yaml`) include pre-built indices (`dietary_filter_index`, `occasion_index`) for fast filtering—update these when adding dishes.

---

## Related documentation

- [agents-overview.md](./agents-overview.md) — which agents run which pipeline steps  
- [microsoft-agent-framework-architecture.md](./microsoft-agent-framework-architecture.md) — syncing YAML chunks to **Azure AI Search**  
- [README.md](../README.md) — running the system and environment variables  
