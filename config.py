import os
from dotenv import load_dotenv

# Reads the .env file and puts its values into environment variables
load_dotenv()


def _get_int(name: str, default: int) -> int:
    """Reads a number from .env. Falls back to a default if missing or invalid."""
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    """Reads true/false from .env. Accepts true, yes, on or 1."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_TIMEOUT_SECONDS = _get_int("AI_TIMEOUT_SECONDS", 20)
MAX_HISTORY_MESSAGES = _get_int("MAX_HISTORY_MESSAGES", 10)
MAX_INPUT_CHARS = _get_int("MAX_INPUT_CHARS", 4000)

# true  = errors that are not in the notes are answered from general knowledge (and labelled)
# false = strict mode: the bot says "I don't have this in my knowledge base"
ALLOW_GENERAL_ANSWERS = _get_bool("ALLOW_GENERAL_ANSWERS", True)

# Speed and cost controls
AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT", "").strip().lower()  # "", low, medium or high
MAX_REPLY_TOKENS = _get_int("MAX_REPLY_TOKENS", 1500)
PRICE_INPUT_PER_1M = _get_float("PRICE_INPUT_PER_1M", 0.0)
PRICE_OUTPUT_PER_1M = _get_float("PRICE_OUTPUT_PER_1M", 0.0)
SLOW_REPLY_MS = _get_int("SLOW_REPLY_MS", 5000)

DATABASE_URL = os.getenv("DATABASE_URL", "")