import uuid

import config
import db

# Everything is stored in PostgreSQL now. Inside the database a bot reply has the role "bot",
# but the AI wants the word "assistant", so we convert in both directions here.


def new_session_id() -> str:
    return str(uuid.uuid4())


def session_exists(session_id: str) -> bool:
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = %s::uuid", (session_id,)
        ).fetchone()
    return row is not None


def get_history(session_id: str) -> list[dict]:
    """The recent messages we send to the AI (at most MAX_HISTORY_MESSAGES), oldest first."""
    with db.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT message_id, role, content
                FROM messages
                WHERE session_id = %s::uuid
                ORDER BY message_id DESC
                LIMIT %s
            ) AS recent
            ORDER BY message_id
            """,
            (session_id, config.MAX_HISTORY_MESSAGES),
        ).fetchall()

    history = [
        {"role": "assistant" if role == "bot" else "user", "content": content}
        for role, content in rows
    ]
    # Never start with a bot message, because the conversation should begin with the user
    if history and history[0]["role"] == "assistant":
        history = history[1:]
    return history


def get_full_history(session_id: str) -> list[dict]:
    """Every message in the session, shaped like the API response."""
    with db.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT m.message_id, m.role, m.content, m.created_at, f.rating
            FROM messages m
            LEFT JOIN feedback f ON f.message_id = m.message_id
            WHERE m.session_id = %s::uuid
            ORDER BY m.message_id
            """,
            (session_id,),
        ).fetchall()

    return [
        {
            "message_id": message_id,
            "role": role,
            "content": content,
            "created_at": created_at.isoformat(timespec="seconds"),
            "rating": rating,
        }
        for message_id, role, content, created_at, rating in rows
    ]


def add_exchange(
    session_id: str,
    user_text: str,
    bot_text: str,
    latency_ms: int | None = None,
    tokens_used: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> int:
    """Saves one question and its answer together. Returns the bot message's id.
    Everything inside the "with" block is one transaction: either all of it is saved, or none."""
    with db.pool.connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id) VALUES (%s::uuid) ON CONFLICT DO NOTHING",
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, created_at)
            VALUES (%s::uuid, 'user', %s, clock_timestamp())
            """,
            (session_id, user_text),
        )
        row = conn.execute(
            """
            INSERT INTO messages
                (session_id, role, content, latency_ms, tokens_used,
                 prompt_tokens, completion_tokens, created_at)
            VALUES (%s::uuid, 'bot', %s, %s, %s, %s, %s, clock_timestamp())
            RETURNING message_id
            """,
            (session_id, bot_text, latency_ms, tokens_used, prompt_tokens, completion_tokens),
        ).fetchone()
    return row[0]


def reset_session(session_id: str) -> None:
    """Deletes a session. Its messages and their feedback are deleted automatically (ON DELETE CASCADE)."""
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = %s::uuid", (session_id,))


def find_message(message_id: int) -> dict | None:
    """Looks a message up by id."""
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT message_id, role FROM messages WHERE message_id = %s", (message_id,)
        ).fetchone()
    if row is None:
        return None
    return {"message_id": row[0], "role": "assistant" if row[1] == "bot" else "user"}


def set_feedback(message_id: int, rating: int) -> None:
    """Saves a rating. Rating the same message again replaces the old rating."""
    with db.pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback (message_id, rating) VALUES (%s, %s)
            ON CONFLICT (message_id) DO UPDATE SET rating = EXCLUDED.rating, created_at = now()
            """,
            (message_id, rating),
        )