import json
from pathlib import Path

from ollama import Client

client = Client()

MODEL = "llama3.1"


def search_kb(question: str):
    """Simple retrieval tool: returns records from kb.json."""
    kb_path = Path(__file__).with_name("kb.json")
    with kb_path.open("r", encoding="utf-8") as f:
        return json.load(f)


tools = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Get information from the store knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                },
                "required": ["question"],
            },
        },
    }
]


def run_agent(prompt):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a store support assistant. "
                "Use the search_kb tool for store-policy questions."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    # First model call
    response = client.chat(
        model=MODEL,
        messages=messages,
        tools=tools,
    )
    message = response["message"]

    # If tool was requested, run it and call model again
    if message.get("tool_calls"):
        tool = message["tool_calls"][0]
        name = tool["function"]["name"]
        args = tool["function"]["arguments"]

        if isinstance(args, str):
            args = json.loads(args)

        result = search_kb(**args)

        messages.append(message)
        messages.append(
            {
                "role": "tool",
                "name": name,
                "content": json.dumps(result),
            }
        )

        response = client.chat(
            model=MODEL,
            messages=messages,
        )
        return response["message"]["content"]

    return message["content"]


if __name__ == "__main__":
    print("Q1: What is the return policy?")
    print(run_agent("What is the return policy?"))
    print("Q2: What is the weather in Tokyo?")
    print(run_agent("What is the weather in Tokyo?"))