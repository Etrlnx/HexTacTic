import argparse

import torch

from script import TicTacToeGame

from .agent import DQNAgent
from .board_encoding import encode_board, valid_move_indices
from .config import DQNconf as cfg
from .model_registry import DEFAULT_REGISTRY_DIR

WEIGHTS_PATH = DEFAULT_REGISTRY_DIR / "dqn_model_weights.pth"

STEP_PENALTY = -0.1
POINT_REWARD = 10.0
WIN_REWARD = 30.0


def play_episode(agent, total_steps=0):
    """Play one self-play game, storing one transition per move from the mover's perspective.

    A player's transition is closed only when that player is about to move again, so
    next_state is the position the same player actually faces after the opponent's reply.
    Points the opponent scores in that reply are subtracted from the transition's reward,
    and the final move of each player gets the +/- WIN_REWARD terminal outcome.

    Returns (episode_reward, length, losses, total_steps).
    """
    game = TicTacToeGame()
    pending = {}  # player -> [state, action, reward] awaiting its next_state
    episode_reward = 0.0
    length = 0
    losses = []

    def learn():
        loss = agent.optimality()
        if loss is not None:
            losses.append(loss)

    while not game._has_winner and not game.is_tied():
        player = game.current_player
        opponent = "O" if player == "X" else "X"
        state = encode_board(game._current_moves, player)

        if player in pending:
            prev_state, prev_action, prev_reward = pending.pop(player)
            agent.memory.append((prev_state, prev_action, prev_reward, state, False))

        action = agent.action_s(state, valid_move_indices(game._current_moves))
        before = game.scores[player]
        game.process_move(action // cfg.BOARD_SIZE, action % cfg.BOARD_SIZE)
        gained = game.scores[player] - before

        reward = STEP_PENALTY + POINT_REWARD * gained
        episode_reward += reward
        pending[player] = [state, action, reward]
        if opponent in pending:
            pending[opponent][2] -= POINT_REWARD * gained

        learn()
        length += 1
        total_steps += 1
        if total_steps % cfg.TARGET_UPD_FREQ == 0:
            agent.update_target_network()

    # next_state of a terminal transition is ignored by the target (done=True).
    terminal_state = encode_board(game._current_moves, "X")
    for player, (state, action, reward) in pending.items():
        if game._has_winner:
            reward += WIN_REWARD if game.current_player == player else -WIN_REWARD
        agent.memory.append((state, action, reward, terminal_state, True))

    for _ in range(10):
        learn()

    return episode_reward, length, losses, total_steps


def train(episodes=10000):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent = DQNAgent(device)
    total_steps = 0
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    for episode in range(episodes):
        _, _, _, total_steps = play_episode(agent, total_steps)
        agent.epsilon = max(cfg.EPS_MIN, agent.epsilon * cfg.EPS_DECAY)

        if (episode + 1) % 500 == 0:
            print(f"Episode {episode + 1}/{episodes} | Epsilon: {agent.epsilon:.4f}")
            torch.save(agent.policynet.state_dict(), WEIGHTS_PATH)

    torch.save(agent.policynet.state_dict(), WEIGHTS_PATH)
    print(f"Training complete! Model weights saved to {WEIGHTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Mimika with plain DDQN self-play")
    parser.add_argument("--episodes", type=int, default=10000)
    train(parser.parse_args().episodes)
