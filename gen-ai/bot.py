"""
Telegram bot: user messages -> local Ollama -> create files under OUTPUT_DIR.

Use a bot (not "just a chat"): Telegram only delivers updates to bots via the Bot API.
Add the bot to a group or DM it; only allowed user IDs can trigger file writes if configured.
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from ollama import Client, ResponseError
from pydantic import BaseModel, Field, ValidationError
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(ROOT / "generated"))).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

_allowed_raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS: set[int] | None = None
if _allowed_raw:
    ALLOWED_USER_IDS = {int(x.strip()) for x in _allowed_raw.split(",") if x.strip()}


class FileSpec(BaseModel):
    relative_path: str = Field(description="Path under output root, use forward slashes, no ..")
    content: str = Field(description="Full file contents")


class FilesResponse(BaseModel):
    files: list[FileSpec] = Field(default_factory=list)


class FilePlan(BaseModel):
    files: list[str] = Field(description="List of file paths to create")


def _clean_json(raw: str) -> str:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0).strip()
    return text


def safe_resolve_under_root(relative: str, root: Path) -> Path:
    """Block path traversal; return absolute path inside root."""
    cleaned = relative.replace("\\", "/").lstrip("/")
    if ".." in cleaned or cleaned.startswith(".."):
        raise ValueError(f"Invalid path: {relative}")
    target = (root / cleaned).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Path escapes output directory: {relative}") from None
    return target


def _ollama_chat(messages: list[dict]) -> str:
    client = Client(host=OLLAMA_HOST)
    try:
        r = client.chat(model=OLLAMA_MODEL, messages=messages)
    except ResponseError as e:
        if e.status_code == 404:
            raise ValueError(
                f"Ollama model '{OLLAMA_MODEL}' not found. Pull it: ollama pull {OLLAMA_MODEL}"
            ) from e
        raise
    return r.get("message", {}).get("content") or ""


def plan_files(user_request: str) -> list[str]:
    """Step 1: ask model to list file paths needed (no content yet)."""
    schema = json.dumps(FilePlan.model_json_schema(), indent=2)
    system = (
        "You are a project planner. The user describes a project. "
        "Return ONLY valid JSON listing the file paths needed.\n"
        f"Schema:\n{schema}\n"
        "Use forward slashes, no .., no absolute paths. "
        "Example: {\"files\": [\"package.json\", \"src/App.jsx\", \"server/index.js\"]}\n"
        "If no files are needed, return {\"files\": []}."
    )
    raw = _ollama_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user_request},
    ])
    cleaned = _clean_json(raw)
    if not cleaned:
        raise ValueError("Model returned empty plan.")
    try:
        plan = FilePlan.model_validate_json(cleaned)
    except ValidationError as e:
        raise ValueError(f"Could not parse file plan. Raw:\n{raw[:2000]}") from e
    return plan.files


def generate_single_file(user_request: str, file_path: str, all_files: list[str]) -> FileSpec:
    """Step 2: generate content for one file at a time."""
    file_list = "\n".join(f"- {f}" for f in all_files)
    system = (
        "You are a code generator. The user requested a project. "
        "The full file list is:\n"
        f"{file_list}\n\n"
        f"Now generate ONLY the file: {file_path}\n"
        "Return ONLY valid JSON with keys: relative_path (string), content (string).\n"
        "content must be the complete file contents. No markdown, no explanation."
    )
    raw = _ollama_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user_request},
    ])
    cleaned = _clean_json(raw)
    if not cleaned:
        raise ValueError(f"Model returned empty content for {file_path}.")
    try:
        return FileSpec.model_validate_json(cleaned)
    except ValidationError as e:
        raise ValueError(f"Could not parse file content for {file_path}. Raw:\n{raw[:2000]}") from e


def write_files(spec: FilesResponse) -> list[str]:
    written: list[str] = []
    for f in spec.files:
        path = safe_resolve_under_root(f.relative_path, OUTPUT_DIR)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f.content, encoding="utf-8")
        written.append(str(path.relative_to(OUTPUT_DIR)))
    return written


def is_allowed(user_id: int) -> bool:
    if ALLOWED_USER_IDS is None:
        return True
    return user_id in ALLOWED_USER_IDS


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Always allowed — use this once to learn your id for TELEGRAM_ALLOWED_USER_IDS."""
    if not update.effective_user:
        return
    await update.message.reply_text(
        f"Your Telegram user id: `{update.effective_user.id}`\n"
        "Put it in .env as TELEGRAM_ALLOWED_USER_IDS=<that number>",
        parse_mode="Markdown",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await update.message.reply_text(
        "Send a message describing what to create (e.g. “add hello.py that prints hi”). "
        f"Files go under: {OUTPUT_DIR}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if not is_allowed(uid):
        await update.message.reply_text("You are not allowed to use this bot.")
        return

    text = update.message.text.strip()
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        # Step 1: plan which files are needed
        await update.message.reply_text("Planning project structure...")
        file_list = plan_files(text)

        if not file_list:
            await update.message.reply_text(
                "No files to create (model returned empty plan). Try being explicit: "
                '"Create a todo app with React and Node"'
            )
            return

        plan_msg = "\n".join(f"- {f}" for f in file_list)
        await update.message.reply_text(
            f"Will create {len(file_list)} file(s):\n{plan_msg}\n\nGenerating one by one..."
        )

        # Step 2: generate each file individually
        written: list[str] = []
        errors: list[str] = []
        for i, fp in enumerate(file_list, 1):
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
            try:
                spec = generate_single_file(text, fp, file_list)
                path = safe_resolve_under_root(spec.relative_path, OUTPUT_DIR)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(spec.content, encoding="utf-8")
                rel = str(path.relative_to(OUTPUT_DIR))
                written.append(rel)
                await update.message.reply_text(f"[{i}/{len(file_list)}] Created: {rel}")
            except ValueError as e:
                errors.append(f"{fp}: {e}")
                await update.message.reply_text(f"[{i}/{len(file_list)}] Failed: {fp}")

        # Summary
        summary = f"Done! {len(written)}/{len(file_list)} file(s) created."
        if errors:
            summary += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:10])
        await update.message.reply_text(summary)

    except ValueError as e:
        await update.message.reply_text(f"Error: {e}")
    except Exception:
        logger.exception("handle_message")
        await update.message.reply_text("Something went wrong; check server logs.")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in ollama-telegram/.env", file=sys.stderr)
        sys.exit(1)

    # Python 3.12+ / 3.14: no implicit main-thread loop; PTB's run_polling uses get_event_loop().
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if ALLOWED_USER_IDS is None:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_IDS not set — anyone can use this bot. "
            "Set it in .env to restrict to your user id (use /myid to see it)."
        )
    else:
        logger.info("Only these Telegram user ids may use the bot: %s", sorted(ALLOWED_USER_IDS))

    logger.info("Bot starting; output dir=%s model=%s", OUTPUT_DIR, OLLAMA_MODEL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
