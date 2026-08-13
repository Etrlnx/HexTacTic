import os

import numpy as np
import torch

from settings import MODEL_PATH
from .board_encoding import encode_board
from .config import DQNconf as cfg
from .model import TTDQNN


class GridScaleAI:
    """Loads the trained model into memory for fast inference."""

    def __init__(self, model_path: str | os.PathLike | None = None):
        self.model_path = str(model_path or MODEL_PATH)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TTDQNN().to(self.device)
        self.weights_loaded = False

        try:
            self.model.load_state_dict(
                torch.load(self.model_path, map_location=self.device, weights_only=True)
            )
            self.weights_loaded = True
            print(f"AI model loaded from {self.model_path} on {self.device}")
        except FileNotFoundError:
            print(f"Warning: model weights not found at {self.model_path}. AI falls back to random moves.")

        self.model.eval()

    def get_best_move(self, current_moves, player_char, valid_moves, difficulty="Normal"):
        if not valid_moves:
            return None

        chance_to_play_optimal = {
            "Nightmare": 1.0,
            "Hard": 0.9,
            "Normal": 0.7,
            "Easy": 0.3,
        }.get(difficulty, 0.7)

        if not self.weights_loaded or np.random.rand() > chance_to_play_optimal:
            return int(np.random.choice(valid_moves))

        state_tensor = encode_board(current_moves, player_char).to(self.device)
        with torch.no_grad():
            q_values = self.model(state_tensor).cpu().numpy()[0]

        q_mask = np.full(cfg.BOARD_SIZE * cfg.BOARD_SIZE, -np.inf)
        for move in valid_moves:
            q_mask[move] = q_values[move]
        return int(np.argmax(q_mask))
