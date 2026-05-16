# What is Eve Cater's AI?

**Eve Cater's AI** is iNextLabs' smart catering assistant for **Southeast Asia**. It helps customers plan and book events through a friendly chat experience (**Eve**), while a backend **multi-agent system** turns each booking into a real operational plan—menu, ingredients, logistics, pricing, and risk checks—grounded in curated catering knowledge.

---

## Who is it for?

| Audience | How they use it |
|----------|------------------|
| **Customers** | Chat with Eve to choose country, event type, menu style, date, guests, budget, and receive a **booking receipt** with a unique ID. |
| **Operations & sales** | Use the agent pipeline output (menu, procurement, staffing, quote) to prepare quotes, sourcing, and event execution. |
| **Developers / integrators** | Call `POST /invocations` with structured event data or extend agents, knowledge bases, and orchestration. |

---

## What does it do?

### For customers (Eve)

Eve guides you through a simple menu:

1. **New Customer** — step-by-step booking for weddings, corporate events, birthdays, cultural celebrations, and custom events across supported SEA countries (e.g. Malaysia, Philippines, Singapore).
2. **View my booking** — look up status with your Booking ID.
3. **Browse catalogue** — get ideas from past-style packages.
4. **How do I use Eve Cater's AI?** — quick guide to features.
5. **Chat with a staff** — handoff when human help is needed.

Eve can hold **natural conversation** (e.g. menu suggestions, flexible budget) when an AI model is connected (such as Ollama). The booking flow stays structured so nothing important is missed—country, dietary needs, date availability, and contact details for WhatsApp follow-up.

After you confirm, you get a **receipt** with an estimated total; staff contact you to confirm final payment and details.

### Behind the scenes (multi-agent system)

When a booking is confirmed (or when the API is called directly), **six specialist agents** work in sequence:

| Agent | Role in one sentence |
|--------|----------------------|
| **Customer** | Turns your answers into a clear event brief (dietary, culture, packages, policies). |
| **Menu** | Picks suitable dishes and checks portions, season, and venue equipment. |
| **Inventory** | Lists ingredients, stock gaps, and a procurement plan with suppliers. |
| **Logistics** | Plans staff, transport, timelines, food safety, and venue compliance. |
| **Pricing** | Builds a quote with margins and checks it against your budget. |
| **Monitoring** | Flags risks (shortages, budget overrun, operational issues). |

They draw on **38 YAML knowledge bases**—recipes, venues, suppliers, pricing benchmarks, cultural norms, and more—so recommendations are **data-driven**, not generic chat guesses.

---

## Why it is different from a simple chatbot

- **Structured booking** — Eve collects the right fields in the right order; you can go back and edit before confirming.
- **Operational depth** — The same system that chats with you can produce procurement lists, staffing counts, and pricing logic used by a real caterer.
- **Transparent reasoning** — Agent outputs include **knowledge-base sources** so teams can see which data drove a decision.
- **Regional focus** — Built for SEA events: halal options, multi-currency (MYR, PHP, SGD, etc.), and local venue/supplier assumptions.
- **Optional intelligence** — Works without a large language model for core planning; LLM adds conversational polish and summaries when enabled.

---

## How do you run it?

Typical local setup:

```bash
# Terminal 1 — API and agents
python -m app.main

# Terminal 2 — Eve customer chat
python -m app.chat
```

You can also run automated pipeline tests: `python test_scenarios.py`.

---

## Learn more

| Document | Contents |
|----------|----------|
| [system-architecture.md](./system-architecture.md) | Full technical architecture |
| [agents-overview.md](./agents-overview.md) | Orchestrator and specialist agents |
| [knowledge-bases-overview.md](./knowledge-bases-overview.md) | All 38 knowledge bases |
| [README.md](../README.md) | Setup, environment variables, and usage |

---

**Eve Cater's AI — iNextLabs** — making catering bookings clearer for customers and more executable for the team behind the event.
