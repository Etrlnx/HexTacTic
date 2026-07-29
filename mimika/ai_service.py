import torch
import numpy as np
from .model import TTDQNN
from .config import DQNconf as cfg

class GridScaleAI:
    """Loads the trained model into memory for fast inference."""
    def __init__(self, model_path="saved_models/dqn_model_weights.pth"):
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TTDQNN().to(self.device)
        
        # Load the trained weights
        try:
            self.model.load_state_dict(torch.load(model_path, map_location=self.device, weights_only=True))
            print(f"AI Model loaded from {model_path} on {self.device}")
        except FileNotFoundError:
            print(f"Warning: Model weights not found at {model_path}. AI will play randomly.")
            
        # Set to evaluation mode which disables dropout/batchnorm updates
        self.model.eval()

    def preproc_state(self, current_moves, player_char):
        state = np.zeros((3, cfg.BOARD_SIZE, cfg.BOARD_SIZE), dtype=np.float32)
        state[0, :, :] = 1.0 # Initialize all as empty

        opp_char = 'O' if player_char == 'X' else 'X'

        for (r, c), p in current_moves.items():
            state[0, r, c] = 0.0 # Remove empty flag
            if p == player_char:
                state[1, r, c] = 1.0 # Self channel
            elif p == opp_char:
                state[2, r, c] = 1.0 # Opponent channel

        return torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)

    def get_best_move(self, current_moves, player_char, valid_moves, difficulty="Normal"):
        """
        Returns the optimal move based on difficulty. 
        Higher difficulties use the AI strictly; lower difficulties add randomness.
        """
        
        # If all valid moves are exhausted
        if not valid_moves:
            return None

        # --- Difficulty Logic ---
        # Nightmare: 100% AI
        # Hard: 90% AI, 10% Random
        # Normal: 70% AI, 30% Random
        # Easy: 30% AI, 70% Random
        
        chance_to_play_optimal = {
            "Nightmare": 1.0,
            "Hard": 0.9,
            "Normal": 0.7,
            "Easy": 0.3
        }.get(difficulty, 0.7)

        # Random fallback based on difficulty
        if np.random.rand() > chance_to_play_optimal:
            return int(np.random.choice(valid_moves))

        # --- AI Prediction ---
        state_tensor = self.preproc_state(current_moves, player_char)
        
        with torch.no_grad():
            q_values = self.model(state_tensor).cpu().numpy()[0]
            
            # Mask out invalid moves so the AI doesn't pick an occupied square
            q_mask = np.full(cfg.BOARD_SIZE * cfg.BOARD_SIZE, -np.inf)
            for move in valid_moves:
                q_mask[move] = q_values[move]
                
            return int(np.argmax(q_mask))