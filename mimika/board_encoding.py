"""Shared board tensor encoding for training and inference."""

from __future__ import annotations

import numpy as np
import torch

from .config import DQNconf as cfg


def encode_board(board_state: list[list[str]], current_player: str) -> torch.Tensor:
    """
    Encode the 6x6 game board as a (1, 3, 6, 6) float tensor.

    Channel 0: 1.0 = empty cell, 0.0 = occupied
    Channel 1: 1.0 = current player's mark
    Channel 2: 1.0 = opponent's mark
    """
    board = np.array(board_state, dtype=object)
    opponent = "O" if current_player == "X" else "X"

    empty = (board == "").astype(np.float32)
    player = (board == current_player).astype(np.float32)
    opponent_plane = (board == opponent).astype(np.float32)

    stacked = np.stack([empty, player, opponent_plane], axis=0)
    return torch.from_numpy(stacked).float().unsqueeze(0)


def encode_board_numpy(board_state: list[list[str]], current_player: str) -> np.ndarray:
    """Numpy variant used internally before device transfer."""
    tensor = encode_board(board_state, current_player)
    return tensor.squeeze(0).numpy()


def valid_move_indices(board_state: list[list[str]]) -> list[int]:
    """Return flattened indices for every empty cell on the board."""
    moves: list[int] = []
    for row in range(cfg.BOARD_SIZE):
        for col in range(cfg.BOARD_SIZE):
            if board_state[row][col] == "":
                moves.append(row * cfg.BOARD_SIZE + col)
    return moves
