# Program backend using FastAPI 

# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Import your existing logic and DB scripts
from script import TicTacToeGame
from database import init_db, add_win, get_leaderboard

app = FastAPI(title="6x6 Tic-Tac-Toe API")

# Configure CORS so your React frontend can communicate with it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # React default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the database and game logic
init_db()
game = TicTacToeGame()

# Define Pydantic models to validate incoming JSON data from React
class StartGameRequest(BaseModel):
    mode: str = "vs_player" # Expects "vs_player" or "vs_system"

class MoveRequest(BaseModel):
    row: int
    col: int

class ScoreRequest(BaseModel):
    player_name: str


@app.get("/api/state")
def get_state():
    """Returns the current state of the game board."""
    return game.get_state()


@app.post("/api/start")
def start_game(payload: StartGameRequest):
    """Resets the game and updates the game mode."""
    game.reset_game()
    game.game_mode = payload.mode
    return game.get_state()


@app.post("/api/move")
def make_move(payload: MoveRequest):
    
    # 1. If the move is valid, process it. If NOT valid, do absolutely nothing!
    if game.is_valid_move(payload.row, payload.col):
        game.process_move(payload.row, payload.col)
        
        # 2. Check if human won or tied after their valid move
        state = game.get_state()
        if state["has_winner"] or state["is_tied"]:
            return state

        # 3. Handle System AI Turn only if the game mode is vs_system
        if game.game_mode == "vs_system" and game.current_player == "O":
            ai_move = game.get_ai_move()
            if ai_move:
                game.process_move(ai_move[0], ai_move[1])

    # 4. Return the game state (either updated by moves, or completely untouched)
    return game.get_state()


@app.get("/api/scores")
def get_scores():
    """Retrieves top 5 high scores."""
    return get_leaderboard()


@app.post("/api/scores")
def record_score(payload: ScoreRequest):
    """Saves a winning player's score and returns the updated leaderboard."""
    add_win(payload.player_name)
    return get_leaderboard()