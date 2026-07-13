# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel
from typing import Optional

from script import TicTacToeGame
from database import init_db, update_player_record, get_player_stats

app = FastAPI(title="6x6 Tic-Tac-Toe API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
game = TicTacToeGame()

class StartGameRequest(BaseModel):
    mode: str = "vs_player" 
    difficulty: Optional[str] = "medium" # 'easy', 'medium', 'hard'

class MoveRequest(BaseModel):
    row: int
    col: int

class RecordMatchRequest(BaseModel):
    username: str
    difficulty: str
    result: str  # 'wins', 'losses', 'draws'


@app.get("/api/state")
def get_state():
    return game.get_state()


@app.post("/api/start")
def start_game(payload: StartGameRequest):
    game.reset_game()
    game.game_mode = payload.mode
    if payload.difficulty in ["easy", "medium", "hard"]:
        game.difficulty = payload.difficulty
    return game.get_state()


@app.post("/api/move")
def make_move(payload: MoveRequest):
    if game.is_valid_move(payload.row, payload.col):
        game.process_move(payload.row, payload.col)
        
        state = game.get_state()
        if state["has_winner"] or state["is_tied"]:
            return state

        if game.game_mode == "vs_system" and game.current_player == "O":
            ai_move = game.get_ai_move()
            if ai_move:
                game.process_move(ai_move[0], ai_move[1])

    return game.get_state()


@app.get("/api/player/{username}")
def get_player_profile(username: str):
    """Fetches full database stats profile tracking block for the active user."""
    return get_player_stats(username)


@app.post("/api/record-match")
def record_match(payload: RecordMatchRequest):
    """Executes the dynamic UPSERT transaction logging historical matches."""
    if payload.result not in ["wins", "losses", "draws"]:
        raise HTTPException(status_code=400, detail="Invalid result token string")
    
    update_player_record(payload.username, payload.difficulty, payload.result)
    return get_player_stats(payload.username)