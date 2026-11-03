"""Model registry for versioning and managing multiple model checkpoints."""

from __future__ import annotations

import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from .board_encoding import encode_board, masked_argmax, valid_move_indices
from .config import DQNconf as cfg
from .model import TTDQNN

DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parent.parent / "saved_models"


class ModelRegistry:
    """Manages model versions, metadata, and checkpoints."""

    def __init__(self, registry_dir: str | Path = DEFAULT_REGISTRY_DIR):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.registry_dir / "model_index.json"
        self._index: Dict[str, Any] = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text())
            except Exception:
                return {"models": {}, "current": None}
        return {"models": {}, "current": None}

    def _save_index(self) -> None:
        self.index_file.write_text(json.dumps(self._index, indent=2))

    def register_model(
        self,
        model_path: str | Path,
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
        make_current: bool = True,
    ) -> Dict[str, Any]:
        """Register a model version with metadata."""
        src = Path(model_path)
        if not src.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        dst = self.registry_dir / f"model_v{version}.pth"
        shutil.copy2(src, dst)

        # Load model to get architecture info
        model = TTDQNN()
        state_dict = torch.load(dst, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)

        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

        model_info = {
            "version": version,
            "path": str(dst),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "file_size_bytes": dst.stat().st_size,
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "architecture": "TTDQNN",
            "board_size": cfg.BOARD_SIZE,
            "input_channels": cfg.IP_CHANNELS,
            "metadata": metadata or {},
        }

        self._index["models"][version] = model_info
        if make_current or self._index["current"] is None:
            self._index["current"] = version
        self._save_index()

        return model_info

    def get_model_info(self, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get model info by version, or current if not specified."""
        ver = version or self._index["current"]
        return self._index["models"].get(ver)

    def list_models(self) -> List[Dict[str, Any]]:
        """List all registered models, newest registration first."""
        return sorted(self._index["models"].values(), key=lambda m: m["registered_at"], reverse=True)

    def set_current(self, version: str) -> bool:
        """Set the current model version."""
        if version not in self._index["models"]:
            return False
        self._index["current"] = version
        self._save_index()
        return True

    def delete_model(self, version: str) -> bool:
        """Delete a model version (cannot delete current)."""
        if version == self._index["current"]:
            return False
        if version not in self._index["models"]:
            return False

        model_info = self._index["models"].pop(version)
        Path(model_info["path"]).unlink(missing_ok=True)
        self._save_index()
        return True

    def load_model(self, version: Optional[str] = None) -> TTDQNN:
        """Load a model by version (or current)."""
        model_info = self.get_model_info(version)
        if not model_info:
            raise ValueError(f"Model version not found: {version or 'current'}")

        model = TTDQNN()
        state_dict = torch.load(model_info["path"], map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()
        return model


class ModelEvaluator:
    """Evaluates model performance against baselines."""

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def evaluate_vs_random(
        self,
        version: Optional[str] = None,
        games: int = 100,
        device: str = "cpu",
    ) -> Dict[str, Any]:
        """Evaluate a registered model against random play."""
        return evaluate_model_vs_random(self.registry.load_model(version), games, device)

    def evaluate_vs_heuristic(
        self,
        version: Optional[str] = None,
        games: int = 100,
        device: str = "cpu",
    ) -> Dict[str, Any]:
        """Evaluate a registered model against the line-completing/blocking heuristic."""
        return evaluate_model_vs_heuristic(self.registry.load_model(version), games, device)

    def evaluate_vs_previous(
        self,
        version: str,
        previous_version: str,
        games: int = 100,
        device: str = "cpu",
    ) -> Dict[str, Any]:
        """Evaluate a registered model against another registered version."""
        a_wins, b_wins, draws = play_match(
            self.registry.load_model(version), self.registry.load_model(previous_version), games, device
        )
        return {
            version: a_wins,
            previous_version: b_wins,
            "draws": draws,
            "total_games": games,
            f"{version}_win_rate": a_wins / games,
            f"{previous_version}_win_rate": b_wins / games,
            "draw_rate": draws / games,
        }


def _greedy_move(model: torch.nn.Module, board, player: str, moves: list[int], device: str) -> int:
    with torch.no_grad():
        q_values = model(encode_board(board, player).to(device)).cpu().numpy()[0]
    return masked_argmax(q_values, moves)


def _points_if_played(board, row: int, col: int, label: str) -> int:
    """New 3-cell lines `label` would score by playing (row, col); mirrors TicTacToeGame scoring."""
    n = len(board)
    points = 0
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        run = []
        for sign in (1, -1):
            r, c, length = row + sign * dr, col + sign * dc, 0
            while 0 <= r < n and 0 <= c < n and board[r][c] == label:
                length += 1
                r, c = r + sign * dr, c + sign * dc
            run.append(length)
        forward, back = run
        # 3-cell windows containing the new cell start at offset -2, -1 or 0.
        points += sum(1 for start in (-2, -1, 0) if -start <= back and start + 2 <= forward)
    return points


def random_move(board, player: str, moves: list[int]) -> int:
    return random.choice(moves)


def heuristic_move(board, player: str, moves: list[int]) -> int:
    """Score the most points if possible, else block the opponent's best line, else play randomly."""
    opponent = "O" if player == "X" else "X"
    for label in (player, opponent):
        gains = {m: _points_if_played(board, m // cfg.BOARD_SIZE, m % cfg.BOARD_SIZE, label) for m in moves}
        best = max(gains.values())
        if best > 0:
            return random.choice([m for m, g in gains.items() if g == best])
    return random.choice(moves)


def play_match(
    model_a: torch.nn.Module,
    model_b: Optional[torch.nn.Module],
    games: int,
    device: str = "cpu",
    opponent=random_move,
) -> tuple[int, int, int]:
    """Play greedy model_a vs model_b (None = `opponent` policy, default uniform random), alternating who opens.

    Returns (a_wins, b_wins, draws).
    """
    from script import TicTacToeGame

    for m in (model_a, model_b):
        if m is not None:
            m.to(device).eval()

    a_wins = b_wins = draws = 0
    for i in range(games):
        game = TicTacToeGame()
        a_plays = "X" if i % 2 == 0 else "O"
        while not game._has_winner and not game.is_tied():
            current = game.current_player
            moves = valid_move_indices(game._current_moves)
            model = model_a if current == a_plays else model_b
            if model is None:
                action = opponent(game._current_moves, current, moves)
            else:
                action = _greedy_move(model, game._current_moves, current, moves, device)
            game.process_move(action // cfg.BOARD_SIZE, action % cfg.BOARD_SIZE)

        if not game._has_winner:
            draws += 1
        elif game.current_player == a_plays:
            a_wins += 1
        else:
            b_wins += 1
    return a_wins, b_wins, draws


def evaluate_model_vs_random(model: torch.nn.Module, games: int = 100, device: str = "cpu") -> Dict[str, Any]:
    """Win/loss/draw rates of a model (not necessarily registered) against random play."""
    return _rates(*play_match(model, None, games, device), games)


def evaluate_model_vs_heuristic(model: torch.nn.Module, games: int = 100, device: str = "cpu") -> Dict[str, Any]:
    """Win/loss/draw rates of a model against heuristic_move (a much stronger bar than random)."""
    return _rates(*play_match(model, None, games, device, opponent=heuristic_move), games)


def _rates(wins: int, losses: int, draws: int, games: int) -> Dict[str, Any]:
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "total_games": games,
        "win_rate": wins / games,
        "loss_rate": losses / games,
        "draw_rate": draws / games,
    }


# Convenience function
def create_registry(registry_dir: str | Path = DEFAULT_REGISTRY_DIR) -> ModelRegistry:
    return ModelRegistry(registry_dir)
