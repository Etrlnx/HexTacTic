# database.py
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


def _load_local_env() -> None:
    """Load simple KEY=VALUE pairs from the ignored local .env file when present."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"").strip("'"))


_load_local_env()

DIFFICULTIES = {"easy": "Easy", "normal": "Normal", "hard": "Hard", "nightmare": "Nightmare"}
RESULTS = {"win": "wins", "wins": "wins", "loss": "losses", "losses": "losses", "draw": "draws", "draws": "draws"}

# database configuration
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5")),
}


def _normalize_match_fields(difficulty: str, result: str):
    """Return safe, schema-backed values for a match update."""
    difficulty_key = difficulty.strip().lower()
    result_key = result.strip().lower()
    if difficulty_key not in DIFFICULTIES:
        raise ValueError(f"Unsupported difficulty: {difficulty}")
    if result_key not in RESULTS:
        raise ValueError(f"Unsupported match result: {result}")
    return difficulty_key, RESULTS[result_key]

def init_db():
    """Initializes the structural table directly inside PostgreSQL."""
    query = """
    CREATE TABLE IF NOT EXISTS public.player_scoreboard (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        easy_wins INT DEFAULT 0,
        easy_losses INT DEFAULT 0,
        easy_draws INT DEFAULT 0,
        normal_wins INT DEFAULT 0,
        normal_losses INT DEFAULT 0,
        normal_draws INT DEFAULT 0,
        -- Retained solely to preserve records created by the original schema.
        medium_wins INT DEFAULT 0,
        medium_losses INT DEFAULT 0,
        medium_draws INT DEFAULT 0,
        hard_wins INT DEFAULT 0,
        hard_losses INT DEFAULT 0,
        hard_draws INT DEFAULT 0,
        nightmare_wins INT DEFAULT 0,
        nightmare_losses INT DEFAULT 0,
        nightmare_draws INT DEFAULT 0,
        highest_difficulty TEXT NOT NULL DEFAULT 'Easy',
        last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                # Make the migration safe for databases created by earlier releases.
                for column in (
                    "normal_wins INT DEFAULT 0", "normal_losses INT DEFAULT 0", "normal_draws INT DEFAULT 0",
                    "nightmare_wins INT DEFAULT 0", "nightmare_losses INT DEFAULT 0", "nightmare_draws INT DEFAULT 0",
                    "highest_difficulty TEXT NOT NULL DEFAULT 'Easy'",
                ):
                    cur.execute(f"ALTER TABLE public.player_scoreboard ADD COLUMN IF NOT EXISTS {column}")
                cur.execute("""
                    UPDATE public.player_scoreboard
                    SET highest_difficulty = CASE
                        WHEN nightmare_wins + nightmare_losses + nightmare_draws > 0 THEN 'Nightmare'
                        WHEN hard_wins + hard_losses + hard_draws > 0 THEN 'Hard'
                        WHEN normal_wins + normal_losses + normal_draws + medium_wins + medium_losses + medium_draws > 0 THEN 'Normal'
                        ELSE 'Easy'
                    END
                """)
                conn.commit()
    except Exception as e:
        print(f"Database initialization failed: {e}")

def update_player_record(username: str, difficulty: str, result: str):
    """
    Increments or creates a player tracking row dynamically using UPSERT.
    difficulty: 'easy', 'normal', 'hard', or 'nightmare'
    result: 'win(s)', 'loss(es)', or 'draw(s)'
    """
    difficulty_key, result_key = _normalize_match_fields(difficulty, result)
    column_name = f"{difficulty_key}_{result_key}"
    difficulty_name = DIFFICULTIES[difficulty_key]
    
    query = f"""
        INSERT INTO public.player_scoreboard (username, {column_name}, highest_difficulty)
        VALUES (%s, 1, %s)
        ON CONFLICT (username) 
        DO UPDATE SET 
            {column_name} = public.player_scoreboard.{column_name} + 1,
            highest_difficulty = CASE
                WHEN public.player_scoreboard.highest_difficulty = 'Nightmare' THEN 'Nightmare'
                WHEN EXCLUDED.highest_difficulty = 'Nightmare' THEN 'Nightmare'
                WHEN public.player_scoreboard.highest_difficulty = 'Hard' THEN 'Hard'
                WHEN EXCLUDED.highest_difficulty = 'Hard' THEN 'Hard'
                WHEN public.player_scoreboard.highest_difficulty = 'Normal' THEN 'Normal'
                WHEN EXCLUDED.highest_difficulty = 'Normal' THEN 'Normal'
                ELSE 'Easy'
            END,
            last_updated = NOW();
    """
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (username, difficulty_name))
                conn.commit()
    except Exception as e:
        print(f"Failed to upsert player records: {e}")

def get_player_stats(username: str):
    """Retrieves all tracking statistics for a specific logging-in user."""
    query = "SELECT * FROM public.player_scoreboard WHERE username = %s;"
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (username,))
                row = cur.fetchone()
                return dict(row) if row else {"message": "Player record not found"}
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return {"error": "Failed to read database records"}
