import json
import requests
from ollama import Client

client = Client()

MODEL = "llama3.1"


def get_weather(latitude, longitude):
    """Simple weather tool."""
    r = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m"
    )
    return r.json()["current"]


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    }
]


def run_agent(prompt):

    messages = [
        {"role": "system", "content": "You are a weather assistant."},
        {"role": "user", "content": prompt},
    ]

    # First model call
    response = client.chat(
        model=MODEL,
        messages=messages,
        tools=tools,
    )

    message = response["message"]

    # Did the model request a tool?
    if message.get("tool_calls"):

        tool = message["tool_calls"][0]
        name = tool["function"]["name"]
        args = tool["function"]["arguments"]

        if isinstance(args, str):
            args = json.loads(args)

        # Run tool
        result = get_weather(**args)

        messages.append(message)
        messages.append(
            {
                "role": "tool",
                "name": name,
                "content": json.dumps(result),
            }
        )

        # Second model call with tool result
        response = client.chat(
            model=MODEL,
            messages=messages,
        )

        return response["message"]["content"]

    return message["content"]


if __name__ == "__main__":
    answer = run_agent("What is the weather in Paris?")
    print(answer)