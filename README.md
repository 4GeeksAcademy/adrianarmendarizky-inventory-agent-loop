# Inventory Assistant

A conversational inventory system for a fictional coffee-shop supply store. Instead of tracking stock in a spreadsheet, the owner (Carla) talks to an AI assistant in plain English — it reads and updates a real inventory system behind the scenes.

Two independent pieces, talking to each other over HTTP:

- **`api/app.py`** — a FastAPI service that owns the inventory data, stored in `products.csv`.
- **`agent.py`** — a command-line assistant that connects to an LLM (Groq / Llama 3.3), uses the API's endpoints as tools, and runs a hand-coded Observe → Think → Act → Update → Repeat loop (no agent framework).

Full design decisions and rationale are in [`SPEC.md`](./SPEC.md).

## Setup

This project uses [`uv`](https://docs.astral.sh/uv/) for dependencies. From the project root:

```bash
uv add fastapi uvicorn openai python-dotenv requests
```

Create a `.env` file at the project root with your Groq API key (see `.env.example` for the expected format):

```
GROQ_API_KEY=your_key_here
```

`.env` is already git-ignored — never commit it.

## Running it

Two terminals, both from the project root:

```bash
# Terminal 1 — the API
uv run uvicorn api.app:app --reload

# Terminal 2 — the agent
uv run python agent.py
```

The API must be running before the agent starts. Once both are up, type messages directly into Terminal 2 after the `You:` prompt — plain English, no special syntax needed.

**Stopping:** `Ctrl+C` in Terminal 2 (agent) first, then Terminal 1 (API). `conversation_log.csv` is written incrementally, so nothing is lost by stopping mid-session.

**Relaunching:** Run `uv run python agent.py` again — the API doesn't need to be restarted. Product data and conversation history both persist across sessions.

## What it can do

| You say | What happens |
|---|---|
| "What's in my inventory?" | Lists every product currently tracked |
| "Add 15 kg of arabica beans" | Registers a new product |
| "I sold 3 units of coffee mugs" | Adjusts an existing product's stock (positive delta for incoming, negative for outgoing) |
| "What's running low?" | Lists every product below its own low-stock threshold |
| "Adjust the alert threshold for cold brew to 5 liters" | Changes when a specific product starts showing up as low stock |

A couple of rules worth knowing:
- Stock changes are always relative (a *change* in quantity), never a new total.
- Quantities must be whole numbers for countable units (e.g. `"units"`, as in individual mugs or napkins); units like `kg` or `liters` allow decimals.
- An update that would push a product's quantity below zero is rejected rather than allowed.

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/inventory` | List all products |
| `POST` | `/inventory` | Register a new product |
| `PATCH` | `/inventory/{product_id}` | Adjust stock by a signed delta |
| `GET` | `/inventory/alerts` | List products below their alert threshold |
| `PATCH` | `/inventory/{product_id}/threshold` | Change a product's alert threshold |

Interactive API docs are available at `http://localhost:8000/docs` while the API is running.

## Files

| File | Purpose |
|---|---|
| `api/app.py` | The FastAPI application — all inventory logic and data persistence |
| `agent.py` | The LLM agent — tool definitions, the conversation loop, and logging |
| `products.csv` | Inventory data, created automatically on first API run |
| `conversation_log.csv` | Full event log of every conversation, created automatically |
| `SPEC.md` | Design spec and decisions made before/during the build |
| `.env.example` | Template showing which environment variable(s) are required |

`main.py`, `server.py`, and `src/` are leftover scaffolding from the starter template / `uv init` and aren't used by this project.

## Verifying it worked

```bash
cat products.csv
cat conversation_log.csv
```

`products.csv` should reflect whatever changes were made during the session. `conversation_log.csv` should have a row for every user message, every tool the agent decided to call, every tool result, and every final response — with `actor`, `message`, `tool_call`, and `timestamp` populated on each row.