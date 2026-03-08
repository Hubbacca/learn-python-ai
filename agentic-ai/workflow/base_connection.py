import os
from pathlib import Path

from dotenv import load_dotenv
from ollama import Client


class BaseConnection:
    """Singleton that manages Ollama client/model configuration."""

    _instance: "BaseConnection | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        env_path = Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(dotenv_path=env_path)

        self.host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.client = Client(host=self.host)
        self._initialized = True

