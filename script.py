# script.py
from typing import Dict, Any, List, Tuple


class TicTacToeGame:
    def __init__(self, board_size: int = 6, win_streak: int = 3):
        self.board_size = board_size
        self.win_streak = win_streak
        self.current_player = "X"
        self.winner_combo: List[Tuple[int, int]] = []
        self._has_winner = False
        self._current_moves: List[List[str]] = []
        self.game_mode = "vs_player"
        self.difficulty = "Normal"
        self.scores = {"X": 0, "O": 0}
        self.reset_game()

    def reset_game(self):
        self._current_moves = [["" for _ in range(self.board_size)] for _ in range(self.board_size)]
        self._has_winner = False
        self.winner_combo = []
        self.current_player = "X"
        self.scores = {"X": 0, "O": 0}

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
        new_pts = self.update_scores_combos(row, col)

        if new_pts > 0:
            self.scores[self.current_player] += new_pts

        if self.scores[self.current_player] >= 3:
            self._has_winner = True
        else:
            self.toggle_player()
        return True

    def toggle_player(self):
        self.current_player = "O" if self.current_player == "X" else "X"

    def update_scores_combos(self, row: int, col: int) -> int:
        label = self._current_moves[row][col]
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        new_pts_scored = 0

        for dr, dc in directions:
            cells_active = [(row, col)]

            r, c = row + dr, col + dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == label:
                cells_active.append((r, c))
                r += dr
                c += dc

            r, c = row - dr, col - dc
            while 0 <= r < self.board_size and 0 <= c < self.board_size and self._current_moves[r][c] == label:
                cells_active.append((r, c))
                r -= dr
                c -= dc

            if len(cells_active) >= 3:
                cells_active.sort()

                for i in range(len(cells_active) - 2):
                    subseg = cells_active[i : i + 3]
                    r1, c1 = subseg[0]
                    r2, c2 = subseg[1]
                    r3, c3 = subseg[2]

                    if (
                        (r2 - r1 == dr and c2 - c1 == dc and r3 - r2 == dr and c3 - c2 == dc)
                        or (r2 - r1 == -dr and c2 - c1 == -dc and r3 - r2 == -dr and c3 - c2 == -dc)
                    ):
                        combo_sig = tuple(subseg)
                        if combo_sig not in self.winner_combo:
                            self.winner_combo.append(combo_sig)
                            new_pts_scored += 1

        return new_pts_scored

    def is_tied(self) -> bool:
        if self._has_winner:
            return False
        return all(cell != "" for row in self._current_moves for cell in row)

    def get_state(self) -> Dict[str, Any]:
        return {
            "board": self._current_moves,
            "current_player": self.current_player,
            "has_winner": self._has_winner,
            "winner_combo": [list(cell) for combo in self.winner_combo for cell in combo],
            "is_tied": self.is_tied(),
            "difficulty": self.difficulty,
            "scores": self.scores,
        }
