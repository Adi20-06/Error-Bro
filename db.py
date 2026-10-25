import logging

from psycopg_pool import ConnectionPool

import config

logger = logging.getLogger("error-translator")

pool: ConnectionPool | None = None

TABLES = ("sessions", "messages", "feedback", "test_results")

# The four tables from the brief. "IF NOT EXISTS" makes this safe to run on every start.
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id  UUID PRIMARY KEY,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        message_id   BIGSERIAL PRIMARY KEY,
        session_id   UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        role         TEXT NOT NULL CHECK (role IN ('user', 'bot')),
        content      TEXT NOT NULL,
        latency_ms   INTEGER,
        tokens_used  INTEGER,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, message_id)",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS completion_tokens INTEGER",
    """
    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id  BIGSERIAL PRIMARY KEY,
        message_id   BIGINT NOT NULL UNIQUE REFERENCES messages(message_id) ON DELETE CASCADE,
        rating       SMALLINT NOT NULL CHECK (rating IN (1, -1)),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS test_results (
        test_id     BIGSERIAL PRIMARY KEY,
        query       TEXT NOT NULL,
        expected    TEXT,
        actual      TEXT,
        correct     BOOLEAN,
        latency_ms  INTEGER,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


def init_db() -> None:
    """Opens the connection pool and creates the tables. Stops the server with a clear message if it fails."""
    global pool

    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is empty. Add it to the .env file.")

    try:
        pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=False)
        pool.open(wait=True, timeout=10)
        # "with" saves (commits) the changes when the block ends without an error
        with pool.connection() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
    except Exception as e:
        logger.error("Could not set up the database: %s", e)
        raise

    logger.info("Database ready")


def close_db() -> None:
    if pool is not None:
        pool.close()


def table_counts() -> dict:
    """How many rows each table has. Used by the check route."""
    counts = {}
    with pool.connection() as conn:
        for table in TABLES:   # fixed list of names, never user input
            counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return counts