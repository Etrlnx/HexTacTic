from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel
from typing import Optional, List, Dict
from script import TicTacToeGame
from mimika.ai_service import GridScaleAI
from database import init_db, update_player_record, get_player_stats

from contextlib import asynccontextmanager
from fastapi import FastAPI
app = FastAPI(title="6x6 Tic-Tac-Toe GridScale API")

# Setup CORS - Allow local and remote access via Tailscale
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust to specific frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database & AI Engine on Startup
init_db()
ai = GridScaleAI()

# Global Game Instance (for single-player testing; consider session IDs for multi-user)
game = TicTacToeGame()


class StartGameRequest(BaseModel):
    mode: str = "vs_player"  # "vs_player" or "vs_system"
    difficulty: Optional[str] = "Normal"  # "Easy", "Normal", "Hard", "Nightmare"
    starting_player: Optional[str] = "X"  # "X" or "O"


class MoveRequest(BaseModel):
    row: int
    col: int


class RecordMatchRequest(BaseModel):
    username: str
    difficulty: str  # "Easy", "Normal", "Hard", "Nightmare"
    result: str      # "win", "loss", "draw"


def _make_ai_move():
    """Helper function to fetch valid moves and call the DDQN model."""
    if game._has_winner or game.is_tied():
        return

    valmoves = []
    for r in range(6):
        for c in range(6):
            if game.is_valid_move(r, c):
                valmoves.append(r * 6 + c)

    if not valmoves:
        return

    # Call DDQN Inference Model
    action_idx = ai.get_best_move(
        current_moves=game._current_moves,
        player_char=game.current_player,
        valid_moves=valmoves,
        difficulty=game.difficulty
    )

    if action_idx is not None:
        row, col = action_idx // 6, action_idx % 6
        game.process_move(row, col)


@app.get("/api/state")
def get_state():
    return game.get_state()


@app.post("/api/start")
def start_game(payload: StartGameRequest):
    game.reset_game()
    game.game_mode = payload.mode
    
    # Capitalize difficulty to match "Easy", "Normal", "Hard", "Nightmare"
    diff_formatted = payload.difficulty.title()
    if diff_formatted in ["Easy", "Normal", "Hard", "Nightmare"]:
        game.difficulty = diff_formatted
    else:
        game.difficulty = "Normal"
        
    # If system plays first (Player selected 'O'), trigger AI opening move
    if payload.mode == "vs_system" and payload.starting_player == "O":
        _make_ai_move()
            
    return game.get_state()


@app.post("/api/move")
def make_move(payload: MoveRequest):
    if game.is_valid_move(payload.row, payload.col):
        player_marker = game.current_player
        game.process_move(payload.row, payload.col)
        
        state = game.get_state()
        if state["has_winner"] or state["is_tied"]:
            return state

        # AI counters automatically using the DDQN inference engine
        if game.game_mode == "vs_system" and game.current_player != player_marker:
            _make_ai_move()

    return game.get_state()


@app.get("/api/player/{username}")
def get_player_profile(username: str):
    return get_player_stats(username)


@app.post("/api/record-match")
def record_match(payload: RecordMatchRequest):
    valid_results = ["win", "loss", "draw", "wins", "losses", "draws"]
    if payload.result.lower() not in valid_results:
        raise HTTPException(status_code=400, detail="Invalid result token string")
        
    update_player_record(payload.username, payload.difficulty, payload.result)
    return get_player_stats(payload.username)