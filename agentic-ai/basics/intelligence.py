from ollama import ResponseError

from base_connection import BaseConnection


def basic_intelligence(prompt: str) -> str:
    connection = BaseConnection()
    try:
        response = connection.client.chat(
            model=connection.model,
            messages=[{"role": "user", "content": prompt}],
        )
    except ResponseError as exc:
        if exc.status_code == 404:
            raise ValueError(
                f"Ollama model '{connection.model}' not found. "
                f"Set OLLAMA_MODEL in .env or pull it first with: ollama pull {connection.model}"
            ) from exc
        raise
    return response["message"]["content"]


def basic_intelligence_stream(prompt: str) -> None:
    connection = BaseConnection()
    try:
        stream = connection.client.chat(
            model=connection.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            content = chunk["message"]["content"]
            if content:
                print(content, end="", flush=True)
    except ResponseError as exc:
        if exc.status_code == 404:
            raise ValueError(
                f"Ollama model '{connection.model}' not found. "
                f"Set OLLAMA_MODEL in .env or pull it first with: ollama pull {connection.model}"
            ) from exc
        raise


if __name__ == "__main__":
    print("Basic Intelligence Output:")
    basic_intelligence_stream(prompt="What is artificial intelligence?")
    print()
