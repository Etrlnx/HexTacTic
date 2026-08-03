"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


def _load_local_env() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_local_env()

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = ROOT_DIR / "mimika" / "dqn_model_weights.pth"
FALLBACK_MODEL_PATH = ROOT_DIR / "saved_models" / "dqn_model_weights.pth"

RUNTIME_MODE = os.getenv("RUNTIME_MODE", "development").lower()
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

MODEL_PATH = Path(os.getenv("MODEL_PATH", str(DEFAULT_MODEL_PATH)))
if not MODEL_PATH.is_file() and FALLBACK_MODEL_PATH.is_file():
    MODEL_PATH = FALLBACK_MODEL_PATH

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

API_KEY = os.getenv("API_KEY", "")
RATE_LIMIT = os.getenv("RATE_LIMIT", "120/minute")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))

DIFFICULTIES = ("easy", "normal", "hard", "nightmare")
RESULTS = ("win", "loss", "draw")
