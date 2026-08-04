# Inventory Assistant — Project Spec

## Overview
Carla's coffee shop supply store currently tracks stock in a shared spreadsheet nobody keeps updated. This project replaces that with two pieces working together:
- A REST API that owns the inventory data (`products.csv`)
- An AI agent that talks to Carla in plain language, using that API as its only way to touch the data

This doc locks in the design decisions the API and the agent both need to agree on, before either gets built.

## 1. Data Model — products.csv

| Field | Type | Notes |
|---|---|---|
| product_id | int | Auto-incrementing, assigned by the API on creation |
| name | string | e.g. "oat milk" |
| quantity | number | Current stock level |
| unit | string | e.g. "units", "kg", "liters" |
| alert_threshold | number | Below this quantity, the product shows up in `/inventory/alerts`. Defaults to 10 if not given at creation, but can be set per product. |

**Decimal rule:** whether `quantity` (and a PATCH `delta`) may be a decimal depends on the unit. Continuous units like `kg` or `liters` allow decimals. Discrete/countable units — anything measured in `"units"` (napkins, coffee mugs, etc.) — must stay whole numbers. The API validates this on both POST and PATCH.

## 2. API Spec — api/app.py

### GET /inventory
Returns the full product list.
- **200** → JSON array of all products

### POST /inventory
Registers a new product.
- Body: `{name, quantity, unit, alert_threshold?}` — `alert_threshold` optional, defaults to 10
- **201** → the created product, including its assigned `product_id`
- **400** → missing/invalid fields (e.g. negative quantity, missing unit, or a decimal quantity given for a discrete unit like `"units"`)

### PATCH /inventory/{product_id}
Adjusts stock via a *signed delta* — not an absolute value.
- Body: `{delta}` — positive = incoming stock, negative = outgoing
- **200** → the updated product
- **404** → `product_id` doesn't exist
- **400** → the delta would push quantity below zero, *or* the delta isn't a whole number for a discrete-unit product — either way, the file is not modified

### GET /inventory/alerts
Returns every product whose quantity is currently below *its own* `alert_threshold`.
- **200** → JSON array of low-stock products (can be empty)

### Persistence
`products.csv` is the source of truth. Every write (POST, PATCH) saves to the file immediately, so state survives a server restart.

## 3. Agent Spec — agent.py

### Tools (map 1:1 to the API endpoints)

| Tool name | Calls | Parameters |
|---|---|---|
| list_inventory | GET /inventory | none |
| add_product | POST /inventory | name (str), quantity (number), unit (str) |
| update_stock | PATCH /inventory/{id} | product_id (int), delta (number) |
| get_low_stock_alerts | GET /inventory/alerts | none |

Each tool's description (the text the LLM actually reads) needs to be explicit about anything a model could misread — especially `update_stock`: its description should say plainly that `delta` is a *change*, not a new total, since that's the easiest thing to get backwards.

### The loop — Observe → Think → Act → Update → Repeat

```
while True:
    user_input = input("You: ")                          # Observe
    log_event(actor="user", message=user_input)

    while True:
        llm_response = call_llm(conversation_history)     # Think
        log_event(actor="agent", tool_call=llm_response.tool_name or "")

        if llm_response.has_tool_call:
            result = call_api_endpoint(                   # Act
                llm_response.tool_name, llm_response.args
            )
            log_event(actor="tool", tool_call=llm_response.tool_name, message=result)
            conversation_history.append(tool_result=result)  # Update
            continue   # feed the result back to the LLM before deciding what's next
        else:
            print("Agent:", llm_response.text)
            log_event(actor="agent", message=llm_response.text)
            break      # final answer, no pending tool calls — exit inner loop
```

The inner loop is what satisfies the multi-step requirement: after a tool result comes back, the LLM gets another turn *before* anything is printed to Carla. That's what lets "add 30 units of oat milk" turn into a tool call → a result → a second tool call (say, checking alerts) → a final answer, all in one exchange.

## 4. Conversation Log Spec — conversation_log.csv

| Field | Values |
|---|---|
| actor | `user`, `agent`, or `tool` |
| message | The text or result content of the event |
| tool_call | Name of the tool involved (empty string if not applicable) |
| timestamp | ISO 8601, e.g. `2026-08-04T15:32:07` |

Four event types, mapped onto those three actors:

1. **User message** → `actor=user`, `message=<input text>`, `tool_call=""`
2. **Agent decides to call a tool** → `actor=agent`, `message=""`, `tool_call=<tool name>`
3. **Tool result comes back** → `actor=tool`, `message=<result>`, `tool_call=<tool name>`
4. **Agent's final response** → `actor=agent`, `message=<response text>`, `tool_call=""`

The file is opened in append mode on every write — never read-modify-write the whole file. That's what keeps it safe across multiple sessions (stop the agent, relaunch it later, the log just keeps growing).