from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Literal, Optional

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from database import close_pool, get_player_stats, init_db, ping_database, update_player_record
from game_sessions import GameSessionManager
from mimika.ai_service import GridScaleAI
from mimika.board_encoding import valid_move_indices
from settings import API_KEY, CORS_ORIGINS, MODEL_PATH, RATE_LIMIT, RESULTS, RUNTIME_MODE
from ws_manager import websocket_endpoint

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
sessions = GameSessionManager()
ai_engine: GridScaleAI | None = None

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)
ACTIVE_SESSIONS = Gauge("active_game_sessions", "Number of active game sessions")
AI_INFERENCE_LATENCY = Histogram("ai_inference_duration_seconds", "AI inference latency")
AI_MOVES_TOTAL = Counter("ai_moves_total", "Total AI moves made", ["difficulty"])
DB_OPERATIONS = Counter("db_operations_total", "Database operations", ["operation", "status"])

ALLOWED_DIFFICULTIES = {"Easy", "Normal", "Hard", "Nightmare"}
ALLOWED_RESULTS = set(RESULTS)

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_engine
    logger.info("application_startup", runtime_mode=RUNTIME_MODE)
    try:
        init_db()
        logger.info("database_initialized")
    except Exception as exc:
        logger.error("database_initialization_failed", error=str(exc))
    try:
        ai_engine = GridScaleAI()
        logger.info("ai_engine_initialized", weights_loaded=ai_engine.weights_loaded)
    except Exception as exc:
        logger.error("ai_engine_initialization_failed", error=str(exc))
        ai_engine = None
    yield
    logger.info("application_shutdown")
    close_pool()
    logger.info("database_pool_closed")


app = FastAPI(
    title="6x6 Tic-Tac-Toe GridScale API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=f"{API_PREFIX}/docs",
    redoc_url=f"{API_PREFIX}/redoc",
    openapi_url=f"{API_PREFIX}/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if RUNTIME_MODE == "production" else CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "request_started",
        method=request.method,
        url=str(request.url),
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent", ""),
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.error(
            "request_failed",
            method=request.method,
            url=str(request.url),
            duration_ms=round(duration * 1000, 2),
            error=str(exc),
        )
        REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=500).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
        raise

    duration = time.perf_counter() - start_time
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)

    logger.info(
        "request_completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    return response


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

    start = time.perf_counter()
    action_idx = ai_engine.get_best_move(
        current_moves=game._current_moves,
        player_char=game.current_player,
        valid_moves=moves,
        difficulty=game.difficulty,
    )
    AI_INFERENCE_LATENCY.observe(time.perf_counter() - start)

    if action_idx is not None:
        row, col = action_idx // 6, action_idx % 6
        game.process_move(row, col)
        AI_MOVES_TOTAL.labels(difficulty=game.difficulty).inc()


@app.get("/health")
@limiter.limit(RATE_LIMIT)
def health_check(request: Request):
    return {
        "status": "ok",
        "runtime_mode": RUNTIME_MODE,
        "database": "up" if ping_database() else "down",
        "ai_weights_loaded": bool(ai_engine and ai_engine.weights_loaded),
        "model_path": str(MODEL_PATH),
        "model_version": ai_engine.current_version if ai_engine else None,
        "api_version": API_VERSION,
    }


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get(f"{API_PREFIX}/state")
@limiter.limit(RATE_LIMIT)
def get_state(request: Request, session_id: str, _: None = Depends(require_api_key)):
    return sessions.get_state(session_id)


@app.post(f"{API_PREFIX}/start")
@limiter.limit(RATE_LIMIT)
def start_game(request: Request, payload: StartGameRequest, _: None = Depends(require_api_key)):
    difficulty = _normalize_difficulty(payload.difficulty)
    session_id, state = sessions.create_session(
        mode=payload.mode,
        difficulty=difficulty,
        starting_player=payload.starting_player,
    )
    ACTIVE_SESSIONS.set(len(sessions._sessions))

    logger.info(
        "game_started",
        session_id=session_id,
        mode=payload.mode,
        difficulty=difficulty,
        starting_player=payload.starting_player,
    )

    if payload.mode == "vs_system" and payload.starting_player == "O":
        _make_ai_move(session_id)

    return sessions.get_state(session_id)


@app.post(f"{API_PREFIX}/move")
@limiter.limit(RATE_LIMIT)
def make_move(request: Request, payload: MoveRequest, _: None = Depends(require_api_key)):
    session = _get_session_or_404(payload.session_id)
    game = session.game

    logger.info(
        "move_attempted",
        session_id=payload.session_id,
        row=payload.row,
        col=payload.col,
        current_player=game.current_player,
    )

    if not game.is_valid_move(payload.row, payload.col):
        logger.warning(
            "invalid_move",
            session_id=payload.session_id,
            row=payload.row,
            col=payload.col,
        )
        return sessions.get_state(payload.session_id)

    active_marker = game.current_player
    game.process_move(payload.row, payload.col)
    state = game.get_state()

    if state["has_winner"] or state["is_tied"]:
        logger.info(
            "game_ended",
            session_id=payload.session_id,
            has_winner=state["has_winner"],
            is_tied=state["is_tied"],
            winner=state.get("current_player"),
            scores=state.get("scores"),
        )
        ACTIVE_SESSIONS.set(len(sessions._sessions))
        return sessions.get_state(payload.session_id)

    if game.game_mode == "vs_system" and game.current_player != active_marker:
        _make_ai_move(payload.session_id)

    return sessions.get_state(payload.session_id)


@app.get(f"{API_PREFIX}/player/{{username}}")
@limiter.limit(RATE_LIMIT)
def get_player_profile(request: Request, username: str, _: None = Depends(require_api_key)):
    stats = get_player_stats(username)
    if "message" in stats:
        raise HTTPException(status_code=404, detail=stats["message"])
    return stats


@app.post(f"{API_PREFIX}/record-match")
@limiter.limit(RATE_LIMIT)
def record_match(request: Request, payload: RecordMatchRequest, _: None = Depends(require_api_key)):
    if payload.result.strip().lower() not in ALLOWED_RESULTS:
        raise HTTPException(status_code=400, detail=f"Unsupported match result: {payload.result}")

    try:
        difficulty = _normalize_difficulty(payload.difficulty)
        result = update_player_record(payload.username, difficulty, payload.result)
        DB_OPERATIONS.labels(operation="record_match", status="success").inc()
        logger.info(
            "match_recorded",
            username=payload.username,
            difficulty=payload.difficulty,
            result=payload.result,
        )
        return result
    except ValueError as exc:
        DB_OPERATIONS.labels(operation="record_match", status="validation_error").inc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        DB_OPERATIONS.labels(operation="record_match", status="error").inc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        method=request.method,
        url=str(request.url),
        error=str(exc),
        error_type=type(exc).__name__,
    )
    if RUNTIME_MODE == "production":
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.get(f"{API_PREFIX}/ws/create")
@limiter.limit(RATE_LIMIT)
async def create_ws_session(request: Request, _: None = Depends(require_api_key)):
    from ws_manager import ws_manager
    session_id = await ws_manager.create_session()
    return {"session_id": session_id}