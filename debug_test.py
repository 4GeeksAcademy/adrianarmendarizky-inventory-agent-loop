import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Get every product currently below its own low-stock threshold.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": "You are an inventory assistant. Use tools when needed."},
        {"role": "user", "content": "What's running low on stock?"},
    ],
    tools=TOOLS,
)

message = response.choices[0].message
print("content:", repr(message.content))
print("tool_calls:", message.tool_calls)