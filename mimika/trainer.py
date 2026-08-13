import os

import numpy as np
import torch

from script import TicTacToeGame

from .agent import DQNAgent
from .board_encoding import encode_board, valid_move_indices
from .config import DQNconf as cfg


def train(episodes=10000):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent = DQNAgent(device)
    total_steps = 0

    for episode in range(episodes):
        game = TicTacToeGame()

        while not game._has_winner and not game.is_tied():
            current_player = game.current_player
            moves = valid_move_indices(game._current_moves)
            if not moves:
                break

            state_tensor = encode_board(game._current_moves, current_player)
            action_idx = agent.action_s(state_tensor, moves)
            row, col = action_idx // cfg.BOARD_SIZE, action_idx % cfg.BOARD_SIZE

            previous_score = game.scores[current_player]
            game.process_move(row, col)
            points_gained = game.scores[current_player] - previous_score
            step_reward = -0.1 + (points_gained * 10.0)

            done = game._has_winner or game.is_tied()
            next_state_tensor = encode_board(game._current_moves, current_player)
            agent.memory.append((state_tensor, action_idx, step_reward, next_state_tensor, done))
            agent.optimality()
            total_steps += 1

            if total_steps % cfg.TARGET_UPD_FREQ == 0:
                agent.update_target_network()

        terminal_state = encode_board(game._current_moves, "X")
        for player in ("X", "O"):
            if game._has_winner:
                terminal_reward = 30.0 if game.scores[player] >= 3 else -30.0
            else:
                terminal_reward = 0.0

            if agent.memory:
                last_state, last_action, _, _, _ = agent.memory[-1]
                agent.memory.append((last_state, last_action, terminal_reward, terminal_state, True))

        for _ in range(10):
            agent.optimality()

        agent.epsilon = max(cfg.EPS_MIN, agent.epsilon * cfg.EPS_DECAY)

        if (episode + 1) % 500 == 0:
            print(f"Episode {episode + 1}/{episodes} | Epsilon: {agent.epsilon:.4f}")
            os.makedirs("saved_models", exist_ok=True)
            torch.save(agent.policynet.state_dict(), "saved_models/dqn_model_weights.pth")

    os.makedirs("saved_models", exist_ok=True)
    torch.save(agent.policynet.state_dict(), "saved_models/dqn_model_weights.pth")
    print("Training complete! Model weights saved to saved_models/dqn_model_weights.pth")
