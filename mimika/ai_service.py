import os
from pathlib import Path
from typing import Optional

import numpy as np
import structlog
import torch

from settings import MODEL_PATH
from .board_encoding import encode_board, masked_argmax
from .model import TTDQNN
from .model_registry import ModelRegistry

logger = structlog.get_logger()


class GridScaleAI:
    """Loads the trained model into memory for fast inference with version support."""

    def __init__(
        self,
        model_path: str | os.PathLike | None = None,
        version: Optional[str] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TTDQNN().to(self.device)
        self.weights_loaded = False
        self.current_version: Optional[str] = None
        self.registry = registry or ModelRegistry()

        # Production loads MODEL_PATH (saved_models/best_model.pt); registry versions only on request.
        if version:
            self.load_version(version)
        else:
            self.load_from_path(model_path or MODEL_PATH)

        self.model.eval()

    def load_from_path(self, model_path: str | os.PathLike) -> bool:
        """Load model from a specific file path."""
        self.model_path = str(model_path)
        try:
            self.model.load_state_dict(
                torch.load(self.model_path, map_location=self.device, weights_only=True)
            )
            self.weights_loaded = True
            self.current_version = Path(self.model_path).name
            logger.info("ai_model_loaded", path=self.model_path, device=str(self.device))
            return True
        except FileNotFoundError:
            logger.warning("ai_model_missing", path=self.model_path, fallback="random_moves")
            self.weights_loaded = False
            return False

    def load_version(self, version: str) -> bool:
        """Load a specific model version from registry."""
        try:
            model_info = self.registry.get_model_info(version)
            if not model_info:
                logger.warning("ai_model_version_not_found", version=version)
                return False

            state_dict = torch.load(model_info["path"], map_location=self.device, weights_only=True)
            self.model.load_state_dict(state_dict)
            self.weights_loaded = True
            self.current_version = version
            logger.info("ai_model_loaded", version=version, device=str(self.device))
            return True
        except Exception as e:
            logger.error("ai_model_load_failed", version=version, error=str(e))
            self.weights_loaded = False
            return False

    def load_current(self) -> bool:
        """Load the current model from registry."""
        model_info = self.registry.get_model_info()
        if not model_info:
            # Fallback to default path
            return self.load_from_path(MODEL_PATH)

        try:
            state_dict = torch.load(model_info["path"], map_location=self.device, weights_only=True)
            self.model.load_state_dict(state_dict)
            self.weights_loaded = True
            self.current_version = self.registry._index["current"]
            logger.info("ai_model_loaded", version=self.current_version, device=str(self.device))
            return True
        except Exception as e:
            logger.error("ai_model_load_failed", version="current", error=str(e))
            # Fallback
            return self.load_from_path(MODEL_PATH)

    def list_available_versions(self) -> list:
        """List all available model versions."""
        return self.registry.list_models()

    def switch_version(self, version: str) -> bool:
        """Switch to a different model version."""
        return self.load_version(version)

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

        return masked_argmax(q_values, valid_moves)

    def get_model_info(self) -> dict:
        """Get information about the currently loaded model."""
        if self.current_version and self.current_version != "custom":
            info = self.registry.get_model_info(self.current_version)
            if info:
                return info
        return {
            "version": self.current_version or "unknown",
            "weights_loaded": self.weights_loaded,
            "device": str(self.device),
        }