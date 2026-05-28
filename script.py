# CORE GAME LOGIC
# game_logic.py
from typing import NamedTuple, Optional, List, Dict, Any
import random


class Move(NamedTuple):
    row: int
    col: int
    label: str = ""

class TicTacToeGame:
    def __init__(self, board_size: int = 6, win_streak: int = 5):
        self.board_size = board_size
        self.win_streak = win_streak
        self.current_player = "X"
        self.winner_combo = []
        self._has_winner = False
        self._current_moves = []
        self.game_mode = "vs_player" # Default; can be "vs_system"
        self.reset_game()

    def reset_game(self):
        self._current_moves = [
            ["" for _ in range(self.board_size)]
            for _ in range(self.board_size)
        ]
        self._has_winner = False
        self.winner_combo = []
        self.current_player = "X"

    def is_valid_move(self, row: int, col: int) -> bool:
        if self._has_winner:
            return False
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False
        return self._current_moves[row][col] == ""

    def process_move(self, row: int, col: int) -> bool:
        """Executes a move. Returns True if valid, False otherwise."""
        if not self.is_valid_move(row, col):
            return False
        
        self._current_moves[row][col] = self.current_player
        if self._check_win(row, col):
            self._has_winner = True
        else:
            self.toggle_player()
        return True

    def toggle_player(self):
        self.current_player = "O" if self.current_player == "X" else "X"

    def get_ai_move(self) -> Optional[tuple]:
        """Finds an empty square randomly for the computer turn."""
        empty_cells = [
            (r, c) for r in range(self.board_size) 
            for c in range(self.board_size) if self._current_moves[r][c] == ""
        ]
        return random.choice(empty_cells) if empty_cells else None

    def _check_win(self, row: int, col: int) -> bool:
        label = self._current_moves[row][col]
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)] # Horiz, Vert, Diag, Anti-Diag
        
        for dr, dc in directions:
            cells_in_line = [(row, col)]
            
            # Check forwards
            r, c = row + dr, col + dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == label:
                cells_in_line.append((r, c))
                r += dr
                c += dc
                
            # Check backwards
            r, c = row - dr, col - dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == label:
                cells_in_line.append((r, c))
                r -= dr
                c -= dc
            
            if len(cells_in_line) >= self.win_streak:
                self.winner_combo = cells_in_line
                return True
        return False

    def is_tied(self) -> bool:
        if self._has_winner:
            return False
        return all(cell != "" for row in self._current_moves for cell in row)

    def get_state(self) -> Dict[str, Any]:
        """Packages the game state safely for an API response."""
        return {
            "board": self._current_moves,
            "current_player": self.current_player,
            "has_winner": self._has_winner,
            "winner_combo": self.winner_combo,
            "is_tied": self.is_tied()
        }