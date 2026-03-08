import json
import re

from ollama import ResponseError
from pydantic import BaseModel, ValidationError

from base_connection import BaseConnection


# --------------------------------------------------------------
# Step 1: Define the response format in a Pydantic model
# --------------------------------------------------------------


class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]


def _clean_json(raw: str) -> str:
    text = raw.strip()
    # Prefer fenced JSON blocks when present.
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    # Fallback: grab first JSON object in free-form text.
    object_match = re.search(r"\{.*\}", text, re.DOTALL)
    if object_match:
        return object_match.group(0).strip()

    return text


def extract_event(text: str) -> CalendarEvent:
    connection = BaseConnection()
    schema = json.dumps(CalendarEvent.model_json_schema(), indent=2)
    system_prompt = (
        "Extract the event information and return ONLY valid JSON "
        "with keys: name, date, participants."
    )
    user_prompt = f"Text: {text}\n\nJSON schema:\n{schema}"

    try:
        response = connection.client.chat(
            model=connection.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except ResponseError as exc:
        if exc.status_code == 404:
            raise ValueError(
                f"Ollama model '{connection.model}' not found. "
                f"Set OLLAMA_MODEL in .env or pull it first with: ollama pull {connection.model}"
            ) from exc
        raise

    raw = _clean_json(response["message"]["content"])
    try:
        return CalendarEvent.model_validate_json(raw)
    except ValidationError as exc:
        raise ValueError(f"Model did not return valid CalendarEvent JSON: {raw}") from exc


if __name__ == "__main__":
    event = extract_event("Alice and Bob are going to a science fair on Friday.")
    print("Structured Output:")
    print(event.model_dump())