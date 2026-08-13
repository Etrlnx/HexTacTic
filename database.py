"""PostgreSQL persistence with connection pooling and SQL migrations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from settings import (
    DB_CONNECT_TIMEOUT,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_POOL_MAX,
    DB_POOL_MIN,
    DB_PORT,
    DB_USER,
    DIFFICULTIES,
    RESULTS,
)

MIGRATIONS_DIR = Path(__file__).with_name("migrations")

DIFFICULTY_LABELS = {
    "easy": "Easy",
    "normal": "Normal",
    "hard": "Hard",
    "nightmare": "Nightmare",
}

DIFFICULTY_RANK = {
    "Easy": 0,
    "Normal": 1,
    "Hard": 2,
    "Nightmare": 3,
}

RESULT_COLUMNS = {
    "win": "wins",
    "loss": "losses",
    "draw": "draws",
}

_pool: pool.ThreadedConnectionPool | None = None


def _db_kwargs() -> dict[str, Any]:
    if not DB_PASSWORD:
        raise RuntimeError("DB_PASSWORD is required. Set it in the environment or .env file.")
    return {
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "connect_timeout": DB_CONNECT_TIMEOUT,
    }


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = pool.ThreadedConnectionPool(DB_POOL_MIN, DB_POOL_MAX, **_db_kwargs())


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_connection() -> Iterator[Any]:
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def run_migrations() -> None:
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for migration in migration_files:
                cur.execute(
                    "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                    (migration.name,),
                )
                if cur.fetchone():
                    continue
                cur.execute(migration.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                    (migration.name,),
                )
            conn.commit()


def init_db() -> None:
    init_pool()
    run_migrations()


def normalize_match_fields(difficulty: str, result: str) -> tuple[str, str]:
    difficulty_key = difficulty.strip().lower()
    result_key = result.strip().lower()
    if difficulty_key not in DIFFICULTIES:
        raise ValueError(f"Unsupported difficulty: {difficulty}")
    if result_key not in RESULTS:
        raise ValueError(f"Unsupported match result: {result}")
    return difficulty_key, RESULT_COLUMNS[result_key]


def _resolve_highest_difficulty(current: str, played: str) -> str:
    current_rank = DIFFICULTY_RANK.get(current, 0)
    played_rank = DIFFICULTY_RANK.get(played, 0)
    return played if played_rank > current_rank else current


def update_player_record(username: str, difficulty: str, result: str) -> dict[str, Any]:
    difficulty_key, result_column = normalize_match_fields(difficulty, result)
    stat_column = f"{difficulty_key}_{result_column}"
    difficulty_label = DIFFICULTY_LABELS[difficulty_key]

    query = f"""
        INSERT INTO public.player_scoreboard (username, {stat_column}, highest_difficulty)
        VALUES (%s, 1, %s)
        ON CONFLICT (username)
        DO UPDATE SET
            {stat_column} = public.player_scoreboard.{stat_column} + 1,
            highest_difficulty = %s,
            last_updated = NOW()
        RETURNING *
    """

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT highest_difficulty FROM public.player_scoreboard WHERE username = %s", (username,))
            existing = cur.fetchone()
            next_highest = _resolve_highest_difficulty(
                existing["highest_difficulty"] if existing else "Easy",
                difficulty_label,
            )
            cur.execute(query, (username, difficulty_label, next_highest))
            row = cur.fetchone()
            conn.commit()
            return dict(row)


def get_player_stats(username: str) -> dict[str, Any]:
    query = "SELECT * FROM public.player_scoreboard WHERE username = %s"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (username,))
            row = cur.fetchone()
            if row:
                return dict(row)
            return {"message": "Player record not found"}


def ping_database() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:
        return False
