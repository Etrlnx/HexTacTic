# script.py
from typing import NamedTuple, Optional, List, Dict, Any

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
        self.game_mode = "vs_player"
        self.difficulty = "medium"  # 'easy', 'medium', 'hard'
        self.reset_game()

    def reset_game(self):
        self._current_moves = [["" for _ in range(self.board_size)] for _ in range(self.board_size)]
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

    def _evaluate_line(self, row: int, col: int, dr: int, dc: int, player: str) -> int:
        """Heuristic value scorer for a specific directional line string alignment."""
        count = 0
        # Scan forward steps
        r, c = row + dr, col + dc
        while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == player:
            count += 1
            r += dr
            c += dc
        # Scan backward steps
        r, c = row - dr, col - dc
        while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == player:
            count += 1
            r -= dr
            c -= dc
        return count

    def get_ai_move(self) -> Optional[tuple]:
        """Heuristic selection algorithm mapping offensive and defensive weights."""
        empty_cells = [(r, c) for r in range(self.board_size) for c in range(self.board_size) if self._current_moves[r][c] == ""]
        if not empty_cells:
            return None

        import random
        # Easy Mode: Picks random valid moves
        if self.difficulty == "easy":
            return random.choice(empty_cells)

        best_score = -1
        best_moves = []
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

        for r, c in empty_cells:
            cell_score = 0
            for dr, dc in directions:
                # Attack weight (AI is O)
                ai_consecutive = self._evaluate_line(r, c, dr, dc, "O")
                # Defense weight (Human is X)
                human_consecutive = self._evaluate_line(r, c, dr, dc, "X")

                # Hard Mode: Maximize defense and offense weightings aggressively
                if self.difficulty == "hard":
                    if ai_consecutive >= self.win_streak - 1: cell_score += 10000  # Imminent win
                    elif human_consecutive >= self.win_streak - 1: cell_score += 5000 # Critical block
                    elif human_consecutive == self.win_streak - 2: cell_score += 500  # Preventive block
                    else: cell_score += (ai_consecutive * 10) + (human_consecutive * 5)
                
                # Medium Mode: Balanced scaling with structural randomness
                else:
                    if ai_consecutive >= self.win_streak - 1: cell_score += 1000
                    elif human_consecutive >= self.win_streak - 1: cell_score += 400
                    cell_score += (ai_consecutive * 4) + (human_consecutive * 2)

            # Center positioning bonuses
            center = self.board_size / 2
            dist_from_center = abs(r - center) + abs(c - center)
            cell_score += int((self.board_size * 2) - dist_from_center)

            if cell_score > best_score:
                best_score = cell_score
                best_moves = [(r, c)]
            elif cell_score == best_score:
                best_moves.append((r, c))

        return random.choice(best_moves)

    def _check_win(self, row: int, col: int) -> bool:
        label = self._current_moves[row][col]
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            cells_in_line = [(row, col)]
            r, c = row + dr, col + dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == label:
                cells_in_line.append((r, c))
                r += dr
                c += dc
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
        return {
            "board": self._current_moves,
            "current_player": self.current_player,
            "has_winner": self._has_winner,
            "winner_combo": self.winner_combo,
            "is_tied": self.is_tied(),
            "difficulty": self.difficulty
        }