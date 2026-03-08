from typing import Optional
from datetime import datetime
import importlib.util
import json
import logging
import re
from pathlib import Path

from ollama import ResponseError
from pydantic import BaseModel, Field, ValidationError

from base_connection import BaseConnection

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

connection = BaseConnection()


def _clean_json(raw: str) -> str:
    text = raw.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()
    object_match = re.search(r"\{.*\}", text, re.DOTALL)
    if object_match:
        return object_match.group(0).strip()
    return text


def _parse_with_local_model(response_model: type[BaseModel], messages: list[dict]):
    schema = json.dumps(response_model.model_json_schema(), indent=2)
    local_messages = messages + [
        {
            "role": "system",
            "content": (
                "Return ONLY valid JSON matching this schema:\n"
                f"{schema}"
            ),
        }
    ]
    try:
        response = connection.client.chat(model=connection.model, messages=local_messages)
    except ResponseError as exc:
        if exc.status_code == 404:
            raise ValueError(
                f"Ollama model '{connection.model}' not found. "
                f"Set OLLAMA_MODEL in .env or pull it first with: ollama pull {connection.model}"
            ) from exc
        raise
    raw = response.get("message", {}).get("content", "")
    cleaned = _clean_json(raw)

    # Some local models occasionally return empty content on the first try.
    if not cleaned:
        retry_messages = messages + [
            {
                "role": "system",
                "content": (
                    "Reply with ONLY a JSON object. Do not include explanations or markdown."
                ),
            },
            {
                "role": "user",
                "content": f"Return JSON for this schema now:\n{schema}",
            },
        ]
        retry = connection.client.chat(model=connection.model, messages=retry_messages)
        raw = retry.get("message", {}).get("content", "")
        cleaned = _clean_json(raw)

    if not cleaned:
        raise ValueError(
            f"Model returned empty content for {response_model.__name__}. "
            "Try a stronger local model (for example llama3.1:8b-instruct)."
        )

    try:
        return response_model.model_validate_json(cleaned)
    except ValidationError as exc:
        raise ValueError(
            f"Could not parse {response_model.__name__} JSON from model output: {raw}"
        ) from exc

# --------------------------------------------------------------
# Step 1: Define the data models for each stage
# --------------------------------------------------------------


class EventExtraction(BaseModel):
    """First LLM call: Extract basic event information"""

    description: str = Field(description="Raw description of the event")
    is_calendar_event: bool = Field(
        description="Whether this text describes a calendar event"
    )
    confidence_score: float = Field(description="Confidence score between 0 and 1")


class EventDetails(BaseModel):
    """Second LLM call: Parse specific event details"""

    name: str = Field(description="Name of the event")
    date: str = Field(
        description="Date and time of the event. Use ISO 8601 to format this value."
    )
    duration_minutes: int = Field(description="Expected duration in minutes")
    participants: list[str] = Field(description="List of participants")


class EventConfirmation(BaseModel):
    """Third LLM call: Generate confirmation message"""

    confirmation_message: str = Field(
        description="Natural language confirmation message"
    )
    calendar_link: Optional[str] = Field(
        description="Generated calendar link if applicable"
    )


# --------------------------------------------------------------
# Step 2: Define the functions
# --------------------------------------------------------------


def extract_event_info(user_input: str) -> EventExtraction:
    """First LLM call to determine if input is a calendar event"""
    logger.info("Starting event extraction analysis")
    logger.debug(f"Input text: {user_input}")

    today = datetime.now()
    date_context = f"Today is {today.strftime('%A, %B %d, %Y')}."

    result = _parse_with_local_model(
        EventExtraction,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{date_context} "
                    "Classify whether the user is making a calendar request.\n"
                    "Set is_calendar_event=true when the user asks to schedule/create/add/move/reschedule/cancel "
                    "a meeting or event, especially with time/date/participants.\n"
                    "Set is_calendar_event=false for non-calendar tasks like weather, coding help, general Q&A, "
                    "or writing an email.\n"
                    "Always fill description with a clean rewritten version of the user request.\n"
                    "Set confidence_score between 0 and 1.\n"
                    "Examples:\n"
                    "- 'Schedule a team meeting tomorrow at 2pm with Alice' -> true\n"
                    "- 'Move my Friday sync to Monday' -> true\n"
                    "- 'What is the weather in Berlin?' -> false\n"
                    "- 'Write a Python function for sorting' -> false"
                ),
            },
            {"role": "user", "content": user_input},
        ],
    )
    logger.info(
        f"Extraction complete - Is calendar event: {result.is_calendar_event}, Confidence: {result.confidence_score:.2f}"
    )
    return result


def parse_event_details(description: str) -> EventDetails:
    """Second LLM call to extract specific event details"""
    logger.info("Starting event details parsing")

    today = datetime.now()
    date_context = f"Today is {today.strftime('%A, %B %d, %Y')}."

    result = _parse_with_local_model(
        EventDetails,
        messages=[
            {
                "role": "system",
                "content": f"{date_context} Extract detailed event information. When dates reference 'next Tuesday' or similar relative dates, use this current date as reference.",
            },
            {"role": "user", "content": description},
        ],
    )
    logger.info(
        f"Parsed event details - Name: {result.name}, Date: {result.date}, Duration: {result.duration_minutes}min"
    )
    logger.debug(f"Participants: {', '.join(result.participants)}")
    return result


def generate_confirmation(event_details: EventDetails) -> EventConfirmation:
    """Third LLM call to generate a confirmation message"""
    logger.info("Generating confirmation message")

    result = _parse_with_local_model(
        EventConfirmation,
        messages=[
            {
                "role": "system",
                "content": "Generate a natural confirmation message for the event. Sign of with your name; Susie",
            },
            {"role": "user", "content": str(event_details.model_dump())},
        ],
    )
    logger.info("Confirmation message generated successfully")
    return result


# --------------------------------------------------------------
# Step 3: Chain the functions together
# --------------------------------------------------------------


def process_calendar_request(user_input: str) -> Optional[EventConfirmation]:
    """Main function implementing the prompt chain with gate check"""
    logger.info("Processing calendar request")
    logger.debug(f"Raw input: {user_input}")

    # First LLM call: Extract basic info
    initial_extraction = extract_event_info(user_input)

    # Gate check: Verify if it's a calendar event with sufficient confidence
    if (
        not initial_extraction.is_calendar_event
        or initial_extraction.confidence_score < 0.7
    ):
        logger.warning(
            f"Gate check failed - is_calendar_event: {initial_extraction.is_calendar_event}, confidence: {initial_extraction.confidence_score:.2f}"
        )
        return None

    logger.info("Gate check passed, proceeding with event processing")

    # Second LLM call: Get detailed event information
    event_details = parse_event_details(initial_extraction.description)

    # Third LLM call: Generate confirmation
    confirmation = generate_confirmation(event_details)

    logger.info("Calendar request processing completed successfully")
    return confirmation


# --------------------------------------------------------------
# Step 4: Test the chain with a valid input
# --------------------------------------------------------------

user_input = "Let's schedule a 1h team meeting next Tuesday at 2pm with Alice and Bob to discuss the project roadmap."

result = process_calendar_request(user_input)
if result:
    print(f"Confirmation: {result.confirmation_message}")
    if result.calendar_link:
        print(f"Calendar Link: {result.calendar_link}")
else:
    print("This doesn't appear to be a calendar event request.")


# --------------------------------------------------------------
# Step 5: Test the chain with an invalid input
# --------------------------------------------------------------

user_input = "Can you send an email to Alice and Bob to discuss the project roadmap?"

result = process_calendar_request(user_input)
if result:
    print(f"Confirmation: {result.confirmation_message}")
    if result.calendar_link:
        print(f"Calendar Link: {result.calendar_link}")
else:
    print("This doesn't appear to be a calendar event request.")