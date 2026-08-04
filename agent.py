import csv
import json
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_BASE_URL = "http://localhost:8000"
LOG_PATH = os.path.join(os.path.dirname(__file__), "conversation_log.csv")
LOG_FIELDNAMES = ["actor", "message", "tool_call", "timestamp"]

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = (
    "You are an inventory assistant for Carla's coffee shop supply store. "
    "Use the available tools to look up or change inventory — never guess at "
    "quantities or product IDs from memory. update_stock takes a delta (a "
    "change in quantity), not a new total."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": "Get the full list of products in inventory, with quantities and units.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Register a brand new product. Only use this for a product that doesn't exist yet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name, e.g. 'oat milk'"},
                    "quantity": {"type": "number", "description": "Starting stock level"},
                    "unit": {"type": "string", "description": "Unit of measure, e.g. 'units', 'kg', 'liters'"},
                },
                "required": ["name", "quantity", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": (
                "Adjust the stock of an EXISTING product by a delta — a change in quantity, "
                "not a new total. Positive delta for incoming stock, negative for stock going out."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "The ID of the product to update"},
                    "delta": {"type": "number", "description": "The change in quantity, positive or negative"},
                },
                "required": ["product_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Get every product currently below its own low-stock threshold.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def call_list_inventory(args):
    return requests.get(f"{API_BASE_URL}/inventory").json()


def call_add_product(args):
    resp = requests.post(f"{API_BASE_URL}/inventory", json=args)
    if resp.status_code >= 400:
        return {"error": resp.json().get("detail", "request failed")}
    return resp.json()


def call_update_stock(args):
    resp = requests.patch(
        f"{API_BASE_URL}/inventory/{args['product_id']}", json={"delta": args["delta"]}
    )
    if resp.status_code >= 400:
        return {"error": resp.json().get("detail", "request failed")}
    return resp.json()


def call_get_low_stock_alerts(args):
    return requests.get(f"{API_BASE_URL}/inventory/alerts").json()


TOOL_FUNCTIONS = {
    "list_inventory": call_list_inventory,
    "add_product": call_add_product,
    "update_stock": call_update_stock,
    "get_low_stock_alerts": call_get_low_stock_alerts,
}


def log_event(actor, message="", tool_call=""):
    file_exists = os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "actor": actor,
                "message": message,
                "tool_call": tool_call,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def run_agent():
    conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("Inventory assistant ready. Type your message (Ctrl+C to quit).")
    while True:
        user_input = input("You: ")  # Observe
        conversation_history.append({"role": "user", "content": user_input})
        log_event(actor="user", message=user_input)

        while True:
            response = client.chat.completions.create(  # Think
                model=MODEL,
                messages=conversation_history,
                tools=TOOLS,
            )
            message = response.choices[0].message

            if message.tool_calls:
                conversation_history.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    }
                )

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    log_event(actor="agent", tool_call=tool_name)

                    result = TOOL_FUNCTIONS[tool_name](tool_args)  # Act
                    log_event(actor="tool", tool_call=tool_name, message=json.dumps(result))

                    conversation_history.append(  # Update
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        }
                    )
                continue  # Repeat: give the LLM the tool result before printing anything
            else:
                print("Agent:", message.content)
                conversation_history.append({"role": "assistant", "content": message.content})
                log_event(actor="agent", message=message.content)
                break  # final answer, no pending tool calls


if __name__ == "__main__":
    run_agent()