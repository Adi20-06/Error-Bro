import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import db
import stats
from errors import ChatError
from llm import ask_model
from memory import (
    add_exchange,
    find_message,
    get_full_history,
    get_history,
    new_session_id,
    reset_session,
    session_exists,
    set_feedback,
)
from prompt import build_system_prompt
from retrieval import list_topics, retrieve

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("error-translator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()      # runs once when the server starts
    yield
    db.close_db()     # runs once when the server stops


app = FastAPI(title="Error Translator", lifespan=lifespan)


# ---------- Error handlers: every error leaves the server in the same shape ----------

def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(ChatError)
async def handle_chat_error(request: Request, exc: ChatError):
    return error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_bad_request(request: Request, exc: RequestValidationError):
    return error_response(
        422,
        "bad_request",
        "The request was not in the expected format. Check the fields and try again.",
    )


@app.exception_handler(psycopg.Error)
async def handle_database_error(request: Request, exc: psycopg.Error):
    # Covers connection problems, pool timeouts and failed queries
    logger.error("Database error: %s", exc)
    return error_response(
        503,
        "database_unavailable",
        "The chat history database is not available right now. Please try again in a moment.",
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    # A bug we did not predict. Log the details, show a safe message.
    logger.exception("Unexpected error")
    return error_response(500, "internal", "Something went wrong on our side. Please try again.")


# ---------- Request shapes ----------

class ChatRequest(BaseModel):
    session_id: str | None = None   # if missing, the server creates one
    message: str


class FeedbackRequest(BaseModel):
    message_id: int = Field(gt=0, lt=2**62)
    rating: int = Field(ge=-1, le=1)   # we only accept +1 or -1 (0 is rejected below)


# ---------- Helpers ----------

def clean_session_id(session_id: str) -> str:
    """Session ids are UUIDs. Returns the tidy lowercase form, or raises a clear error."""
    try:
        return str(uuid.UUID(session_id))
    except ValueError:
        raise ChatError(422, "bad_request", "That session id is not valid.")


def build_search_query(text: str, history: list[dict]) -> str:
    """Short follow-ups ("what about the second cause?") have no keywords of their own,
    so we also search using the user's previous question."""
    if len(text.split()) < 8:
        previous = [m["content"] for m in history if m["role"] == "user"]
        if previous:
            return previous[-1] + " " + text
    return text


# ---------- Routes ----------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config-check")
def config_check():
    # Never return keys or passwords, only whether they exist
    return {
        "key_loaded": bool(config.AI_API_KEY),
        "base_url": config.AI_BASE_URL,
        "model": config.AI_MODEL,
        "timeout_seconds": config.AI_TIMEOUT_SECONDS,
        "max_history_messages": config.MAX_HISTORY_MESSAGES,
        "max_input_chars": config.MAX_INPUT_CHARS,
        "max_reply_tokens": config.MAX_REPLY_TOKENS,
        "reasoning_effort": config.AI_REASONING_EFFORT or "default",
        "allow_general_answers": config.ALLOW_GENERAL_ANSWERS,
        "prices_set": bool(config.PRICE_INPUT_PER_1M or config.PRICE_OUTPUT_PER_1M),
    }


@app.get("/api/topics")
def topics():
    return {"topics": list_topics()}


@app.get("/api/stats")
def get_stats():
    return stats.snapshot()


@app.get("/api/db-check")
def db_check():
    return {"database": "connected", "rows": db.table_counts()}


# Debug route. Remove before deploying.
@app.get("/api/prompt-preview")
def prompt_preview(q: str):
    prompt = build_system_prompt(retrieve(q), list_topics())
    return {"approx_tokens": len(prompt) // 4, "prompt": prompt}


@app.post("/api/chat")
def chat(req: ChatRequest):
    started = time.perf_counter()
    text = req.message.strip()

    if not text:
        raise ChatError(400, "empty_input", "Please type a message before sending.")
    if len(text) > config.MAX_INPUT_CHARS:
        raise ChatError(
            400,
            "too_long",
            f"That message is too long ({len(text)} characters). "
            f"Please keep it under {config.MAX_INPUT_CHARS}. Try pasting just the error line.",
        )

    session_id = clean_session_id(req.session_id) if req.session_id else new_session_id()
    history = get_history(session_id)

    # 1. Search the notes and build the prompt (timed separately)
    t0 = time.perf_counter()
    notes = retrieve(build_search_query(text, history))
    system_prompt = build_system_prompt(notes, list_topics())
    retrieval_ms = int((time.perf_counter() - t0) * 1000)

    # 2. Ask the AI (raises ChatError on any AI failure)
    result = ask_model(system_prompt, history, text)

    reply = result["reply"]
    if result["truncated"]:
        reply += "\n\n(My answer was cut short because it reached the length limit. Ask me to continue.)"

    total_ms = int((time.perf_counter() - started) * 1000)
    cost = stats.cost_usd(result["prompt_tokens"], result["completion_tokens"])

    # 3. Save the exchange in PostgreSQL. Done only after the AI succeeded,
    #    so a failed AI call leaves no half-saved turn.
    message_id = add_exchange(
        session_id,
        text,
        reply,
        latency_ms=total_ms,
        tokens_used=result["tokens_used"],
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
    )

    log = "chat ok: total %d ms (search %d + AI %d), tokens %s (in %s / out %s), cost %s"
    args = (total_ms, retrieval_ms, result["ai_ms"], result["tokens_used"],
            result["prompt_tokens"], result["completion_tokens"],
            f"${cost}" if cost is not None else "not set")
    if total_ms > config.SLOW_REPLY_MS:
        logger.warning("SLOW " + log, *args)
    else:
        logger.info(log, *args)

    return {
        "session_id": session_id,
        "message_id": message_id,            # the bot reply's id, used by the feedback buttons
        "reply": reply,
        "latency_ms": total_ms,              # everything the user waited for
        "ai_ms": result["ai_ms"],            # just the AI call
        "retrieval_ms": retrieval_ms,        # just the note search
        "tokens_used": result["tokens_used"],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
        "cost_usd": cost,
        "sources": [{"title": n["title"], "url": n["url"]} for n in notes if n["url"]],
    }


@app.get("/api/history/{session_id}")
def history(session_id: str):
    session_id = clean_session_id(session_id)
    if not session_exists(session_id):
        raise ChatError(404, "session_not_found", "No conversation found for that session.")
    return {"session_id": session_id, "messages": get_full_history(session_id)}


@app.post("/api/reset/{session_id}")
def reset(session_id: str):
    session_id = clean_session_id(session_id)
    reset_session(session_id)   # fine even if the session never existed
    return {"status": "reset", "session_id": new_session_id()}


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if req.rating not in (1, -1):
        raise ChatError(422, "bad_request", "The rating must be 1 (helpful) or -1 (not helpful).")

    message = find_message(req.message_id)
    if message is None:
        raise ChatError(404, "message_not_found", "That message does not exist.")
    if message["role"] != "assistant":
        raise ChatError(400, "not_a_bot_message", "Feedback can only be given on the bot's replies.")

    set_feedback(req.message_id, req.rating)
    return {"status": "saved", "message_id": req.message_id, "rating": req.rating}


# The chat page. Keep this as the LAST line so it never hides the /api routes.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")