import logging
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

import config
from errors import ChatError

logger = logging.getLogger("error-translator")

# max_retries=0 so a failure is reported quickly instead of silently retrying
client = OpenAI(
    api_key=config.AI_API_KEY or "missing-key",
    base_url=config.AI_BASE_URL,
    timeout=config.AI_TIMEOUT_SECONDS,
    max_retries=0,
)


def ask_model(system_prompt: str, history: list[dict], user_message: str) -> dict:
    """Sends the system prompt + recent history + new message.
    Returns the reply, how long the AI took, and the tokens used."""
    if not config.AI_API_KEY:
        logger.error("AI_API_KEY is empty. Check the .env file.")
        raise ChatError(500, "not_configured",
                        "The server has no AI key set up yet. Please tell the administrator.")

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": user_message}]
    )

    options = {
        "model": config.AI_MODEL,
        "temperature": 0.3,
        "messages": messages,
        "max_completion_tokens": config.MAX_REPLY_TOKENS,   # caps cost and time
    }
    if config.AI_REASONING_EFFORT:
        # Only sent when set in .env, because not every model accepts it
        options["extra_body"] = {"reasoning_effort": config.AI_REASONING_EFFORT}

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(**options)

    # Order matters: APITimeoutError is a kind of APIConnectionError, so it goes first.
    except APITimeoutError:
        logger.error("AI call timed out after %s seconds", config.AI_TIMEOUT_SECONDS)
        raise ChatError(504, "ai_timeout",
                        "The AI took too long to answer. Please try again.")

    except APIConnectionError as e:
        logger.error("Could not reach the AI service: %s", e)
        raise ChatError(503, "ai_unreachable",
                        "Could not reach the AI service. Check your internet connection and try again.")

    except RateLimitError as e:
        logger.error("Rate limit or quota (%s): %s", getattr(e, "code", None), e.message)
        if getattr(e, "code", None) == "insufficient_quota":
            raise ChatError(429, "ai_quota",
                            "The AI account has run out of credit. Please tell the administrator.")
        raise ChatError(429, "ai_rate_limited",
                        "Too many requests right now. Please wait a minute and try again.")

    except (AuthenticationError, PermissionDeniedError) as e:
        logger.error("AI key rejected (%s): %s", e.status_code, e.message)
        raise ChatError(502, "ai_auth",
                        "The AI service rejected the server's key. This is a setup problem, not your fault.")

    except NotFoundError as e:
        logger.error("Model not found (%s): %s", config.AI_MODEL, e.message)
        raise ChatError(502, "ai_model_missing",
                        "The AI model is not available. This is a setup problem, not your fault.")

    except BadRequestError as e:
        logger.error("AI rejected the request: %s", e.message)
        raise ChatError(400, "ai_rejected",
                        "The AI could not process that message. Try a shorter one, or start a new chat.")

    except APIStatusError as e:
        logger.error("AI service error %s: %s", e.status_code, e.message)
        raise ChatError(502, "ai_server_error",
                        "The AI service is having problems. Please try again shortly.")

    ai_ms = int((time.perf_counter() - start) * 1000)

    choice = completion.choices[0]
    reply = (choice.message.content or "").strip()
    truncated = choice.finish_reason == "length"   # the answer hit MAX_REPLY_TOKENS

    if not reply:
        if truncated:
            logger.error("Reply was empty because MAX_REPLY_TOKENS (%s) was used up", config.MAX_REPLY_TOKENS)
            raise ChatError(502, "reply_too_long",
                            "The answer was too long to finish. Please try a shorter question.")
        logger.error("AI returned an empty reply")
        raise ChatError(502, "empty_reply", "The AI sent an empty answer. Please try again.")

    usage = completion.usage
    return {
        "reply": reply,
        "ai_ms": ai_ms,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
        "tokens_used": usage.total_tokens if usage else None,
        "truncated": truncated,
    }