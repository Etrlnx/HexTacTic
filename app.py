from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from database import close_pool, get_player_stats, init_db, ping_database, update_player_record
from game_sessions import GameSessionManager
from mimika.ai_service import GridScaleAI
from mimika.board_encoding import valid_move_indices
from settings import API_KEY, CORS_ORIGINS, MODEL_PATH, RATE_LIMIT, RUNTIME_MODE

limiter = Limiter(key_func=get_remote_address)
sessions = GameSessionManager()
ai_engine: GridScaleAI | None = None

ALLOWED_DIFFICULTIES = {"Easy", "Normal", "Hard", "Nightmare"}
ALLOWED_RESULTS = {"win", "loss", "draw", "wins", "losses", "draws"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_engine
    try:
        init_db()
    except Exception as exc:
        print(f"Database initialization skipped: {exc}")
    ai_engine = GridScaleAI()
    yield
    close_pool()


app = FastAPI(title="6x6 Tic-Tac-Toe GridScale API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if RUNTIME_MODE == "production" else CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if RUNTIME_MODE != "production" or not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class StartGameRequest(BaseModel):
    mode: Literal["vs_player", "vs_system"] = "vs_player"
    difficulty: str = "Normal"
    starting_player: Literal["X", "O"] = "X"


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


class MoveRequest(SessionRequest):
    row: int = Field(ge=0, le=5)
    col: int = Field(ge=0, le=5)


class RecordMatchRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    difficulty: str
    result: str


def _normalize_difficulty(value: str) -> str:
    formatted = value.strip().title()
    if formatted == "Medium":
        formatted = "Normal"
    if formatted not in ALLOWED_DIFFICULTIES:
        raise HTTPException(status_code=400, detail=f"Unsupported difficulty: {value}")
    return formatted


def _get_session_or_404(session_id: str):
    try:
        return sessions.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Game session not found or expired") from exc


def _make_ai_move(session_id: str) -> None:
    if ai_engine is None:
        return

    session = sessions.get_session(session_id)
    game = session.game
    if game._has_winner or game.is_tied():
        return

    moves = valid_move_indices(game._current_moves)
    if not moves:
        return

    action_idx = ai_engine.get_best_move(
        current_moves=game._current_moves,
        player_char=game.current_player,
        valid_moves=moves,
        difficulty=game.difficulty,
    )
    if action_idx is not None:
        row, col = action_idx // 6, action_idx % 6
        game.process_move(row, col)


@app.get("/health")
@limiter.limit(RATE_LIMIT)
def health_check(request: Request):
    return {
        "status": "ok",
        "runtime_mode": RUNTIME_MODE,
        "database": "up" if ping_database() else "down",
        "ai_weights_loaded": bool(ai_engine and ai_engine.weights_loaded),
        "model_path": str(MODEL_PATH),
    }


@app.get("/api/state")
@limiter.limit(RATE_LIMIT)
def get_state(request: Request, session_id: str, _: None = Depends(require_api_key)):
    return sessions.get_state(session_id)


@app.post("/api/start")
@limiter.limit(RATE_LIMIT)
def start_game(request: Request, payload: StartGameRequest, _: None = Depends(require_api_key)):
    difficulty = _normalize_difficulty(payload.difficulty)
    session_id, state = sessions.create_session(
        mode=payload.mode,
        difficulty=difficulty,
        starting_player=payload.starting_player,
    )

    if payload.mode == "vs_system" and payload.starting_player == "O":
        _make_ai_move(session_id)

    return sessions.get_state(session_id)


@app.post("/api/move")
@limiter.limit(RATE_LIMIT)
def make_move(request: Request, payload: MoveRequest, _: None = Depends(require_api_key)):
    session = _get_session_or_404(payload.session_id)
    game = session.game

    if not game.is_valid_move(payload.row, payload.col):
        return sessions.get_state(payload.session_id)

    active_marker = game.current_player
    game.process_move(payload.row, payload.col)
    state = game.get_state()
    if state["has_winner"] or state["is_tied"]:
        return sessions.get_state(payload.session_id)

    if game.game_mode == "vs_system" and game.current_player != active_marker:
        _make_ai_move(payload.session_id)

    return sessions.get_state(payload.session_id)


@app.get("/api/player/{username}")
@limiter.limit(RATE_LIMIT)
def get_player_profile(request: Request, username: str, _: None = Depends(require_api_key)):
    stats = get_player_stats(username)
    if "message" in stats:
        raise HTTPException(status_code=404, detail=stats["message"])
    return stats


@app.post("/api/record-match")
@limiter.limit(RATE_LIMIT)
def record_match(request: Request, payload: RecordMatchRequest, _: None = Depends(require_api_key)):
    if payload.result.strip().lower() not in ALLOWED_RESULTS:
        raise HTTPException(status_code=400, detail=f"Unsupported match result: {payload.result}")

    try:
        _normalize_difficulty(payload.difficulty)
        return update_player_record(payload.username, payload.difficulty, payload.result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if RUNTIME_MODE == "production":
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return JSONResponse(status_code=500, content={"detail": str(exc)})
