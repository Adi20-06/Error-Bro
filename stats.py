import config
import db


def cost_usd(prompt_tokens: int | None, completion_tokens: int | None) -> float | None:
    """Cost of some tokens, or None if no prices are set in .env."""
    if not (config.PRICE_INPUT_PER_1M or config.PRICE_OUTPUT_PER_1M):
        return None
    p = prompt_tokens or 0
    c = completion_tokens or 0
    return round((p * config.PRICE_INPUT_PER_1M + c * config.PRICE_OUTPUT_PER_1M) / 1_000_000, 6)


def _ms(value) -> int | None:
    return None if value is None else int(round(float(value)))


def snapshot() -> dict:
    """Summary of every bot reply ever saved in the database."""
    with db.pool.connection() as conn:
        row = conn.execute(
            """
            SELECT
                count(*),
                coalesce(sum(prompt_tokens), 0),
                coalesce(sum(completion_tokens), 0),
                coalesce(sum(tokens_used), 0),
                avg(latency_ms),
                percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms),
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                max(latency_ms),
                count(*) FILTER (WHERE latency_ms <= %s)
            FROM messages
            WHERE role = 'bot' AND latency_ms IS NOT NULL
            """,
            (config.SLOW_REPLY_MS,),
        ).fetchone()

    replies, prompt_tokens, completion_tokens, total_tokens, avg_ms, median_ms, p95_ms, max_ms, fast = row
    total_cost = cost_usd(prompt_tokens, completion_tokens)

    return {
        "note": "Computed from every reply saved in the database.",
        "model": config.AI_MODEL,
        "replies": replies,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "avg_tokens_per_reply": round(total_tokens / replies) if replies else None,
        "total_cost_usd": total_cost,
        "avg_cost_usd_per_reply": round(total_cost / replies, 6) if (replies and total_cost is not None) else None,
        "response_time_ms": {
            "average": _ms(avg_ms),
            "median": _ms(median_ms),
            "p95": _ms(p95_ms),
            "slowest": max_ms,
            "target_ms": config.SLOW_REPLY_MS,
            "percent_within_target": round(100 * fast / replies) if replies else None,
        },
    }