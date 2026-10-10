"""Checks for the fixed training, registry and WebSocket logic.

Run: python tests/test_core.py   (or pytest, if installed). Needs no database.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from mimika.agent import DQNAgent
from mimika.board_encoding import masked_argmax
from mimika.model_registry import ModelEvaluator, ModelRegistry
from mimika.trainer import WIN_REWARD, play_episode


def test_masked_argmax_skips_occupied():
    q = np.arange(36, dtype=np.float32)  # best raw Q is index 35
    assert masked_argmax(q, [0, 7, 12]) == 12


def test_self_play_transitions():
    torch.manual_seed(0)
    agent = DQNAgent(torch.device("cpu"))
    _, length, _, steps = play_episode(agent, 0)
    transitions = list(agent.memory)

    assert steps == length
    assert len(transitions) == length  # one transition per move
    done = [t for t in transitions if t[4]]
    assert len(done) == 2  # last move of each player

    for state, _, _, next_state, is_done in transitions:
        if is_done:
            continue
        # next_state is the same player's next turn: own and opponent piece counts each grew by one.
        assert next_state[0, 1].sum() == state[0, 1].sum() + 1
        assert next_state[0, 2].sum() == state[0, 2].sum() + 1

    rewards = sorted(t[2] for t in done)
    if rewards[-1] > WIN_REWARD / 2:  # decisive game: one side +30-ish, the other -30-ish
        assert rewards[0] < -WIN_REWARD / 2


def test_registry_lists_trainer_versions_and_evaluates():
    weights = ROOT / "saved_models" / "best_model.pt"
    registry = ModelRegistry(tempfile.mkdtemp())
    registry.register_model(weights, "ep500")
    registry.register_model(weights, "best_500")
    assert [m["version"] for m in registry.list_models()] == ["best_500", "ep500"]

    result = ModelEvaluator(registry).evaluate_vs_random(games=2)
    assert result["wins"] + result["losses"] + result["draws"] == 2


def test_ws_ready_is_top_level_message():
    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)  # not used as a context manager, so the lifespan (DB) is skipped
    with client.websocket_connect("/ws") as p1, client.websocket_connect("/ws") as p2:
        p1.send_json({"type": "create"})
        session_id = p1.receive_json()["payload"]["session_id"]
        p2.send_json({"type": "join", "session_id": session_id})
        assert p2.receive_json()["type"] == "joined"
        assert p1.receive_json()["type"] == "ready"
        assert p2.receive_json()["type"] == "ready"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
