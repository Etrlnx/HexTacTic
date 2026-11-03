"""Enhanced trainer with monitoring, evaluation, and checkpoint management."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

from .agent import DQNAgent
from .config import DQNconf as cfg
from .model_registry import (
    DEFAULT_REGISTRY_DIR,
    ModelEvaluator,
    ModelRegistry,
    evaluate_model_vs_heuristic,
    evaluate_model_vs_random,
    play_match,
)
from .trainer import WEIGHTS_PATH, play_episode

DEFAULT_LOG_DIR = DEFAULT_REGISTRY_DIR.parent / "logs" / "training"


class TrainingMonitor:
    """Monitors and logs training progress."""

    def __init__(self, log_dir: str | Path = DEFAULT_LOG_DIR):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.writer = SummaryWriter(str(self.log_dir))
        self.episode_rewards: List[float] = []
        self.episode_lengths: List[int] = []
        self.losses: List[float] = []
        self.epsilon_history: List[float] = []
        self.start_time = time.time()

    def log_episode(
        self,
        episode: int,
        reward: float,
        length: int,
        epsilon: float,
        loss: Optional[float] = None,
    ) -> None:
        self.episode_rewards.append(reward)
        self.episode_lengths.append(length)
        self.epsilon_history.append(epsilon)
        if loss is not None:
            self.losses.append(loss)

        self.writer.add_scalar("train/episode_reward", reward, episode)
        self.writer.add_scalar("train/episode_length", length, episode)
        self.writer.add_scalar("train/epsilon", epsilon, episode)
        if loss is not None:
            self.writer.add_scalar("train/loss", loss, episode)

        if episode % 100 == 0 and self.episode_rewards:
            avg_reward = np.mean(self.episode_rewards[-100:])
            avg_length = np.mean(self.episode_lengths[-100:])
            self.writer.add_scalar("train/avg_reward_100", avg_reward, episode)
            self.writer.add_scalar("train/avg_length_100", avg_length, episode)

    def log_evaluation(self, episode: int, metrics: Dict[str, Any]) -> None:
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                self.writer.add_scalar(f"eval/{key}", value, episode)

    def log_model_stats(self, episode: int, model: torch.nn.Module) -> None:
        total_params = sum(p.numel() for p in model.parameters())
        grad_norm = 0.0
        param_count = 0
        for p in model.parameters():
            if p.grad is not None:
                grad_norm += p.grad.data.norm(2).item() ** 2
                param_count += 1
        if param_count > 0:
            grad_norm = grad_norm ** 0.5
        self.writer.add_scalar("model/total_parameters", total_params, episode)
        self.writer.add_scalar("model/grad_norm", grad_norm, episode)

    def close(self) -> None:
        self.writer.close()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_episodes": len(self.episode_rewards),
            "total_time_seconds": time.time() - self.start_time,
            "avg_reward": np.mean(self.episode_rewards) if self.episode_rewards else 0,
            "avg_length": np.mean(self.episode_lengths) if self.episode_lengths else 0,
            "final_epsilon": self.epsilon_history[-1] if self.epsilon_history else 0,
            "avg_loss": np.mean(self.losses) if self.losses else 0,
        }


class EnhancedTrainer:
    """Enhanced trainer with evaluation, checkpointing, and monitoring."""

    def __init__(
        self,
        episodes: int = 10000,
        eval_interval: int = 500,
        checkpoint_interval: int = 500,
        registry_dir: str | Path = DEFAULT_REGISTRY_DIR,
        log_dir: str | Path = DEFAULT_LOG_DIR,
        device: Optional[str] = None,
    ):
        self.episodes = episodes
        self.eval_interval = eval_interval
        self.checkpoint_interval = checkpoint_interval
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.registry = ModelRegistry(registry_dir)
        self.evaluator = ModelEvaluator(self.registry)
        self.monitor = TrainingMonitor(log_dir)

        self.agent = DQNAgent(self.device)
        self.total_steps = 0
        self.best_win_rate = 0.0

    def train(self) -> Dict[str, Any]:
        """Run the full training loop with evaluation and checkpointing."""
        print(f"Starting training on {self.device} for {self.episodes} episodes")
        print(f"Checkpoints: {self.checkpoint_interval} episodes | Evaluation: {self.eval_interval} episodes")

        for episode in range(self.episodes):
            episode_reward, episode_length, losses, self.total_steps = play_episode(self.agent, self.total_steps)
            avg_loss = float(np.mean(losses)) if losses else None

            self.monitor.log_episode(
                episode, episode_reward, episode_length, self.agent.epsilon, avg_loss
            )

            if (episode + 1) % self.eval_interval == 0:
                self._evaluate_and_checkpoint(episode + 1)

            if (episode + 1) % self.checkpoint_interval == 0:
                self._save_checkpoint(episode + 1)

            self.agent.epsilon = max(cfg.EPS_MIN, self.agent.epsilon * cfg.EPS_DECAY)

            if (episode + 1) % 100 == 0:
                elapsed = time.time() - self.monitor.start_time
                print(
                    f"Episode {episode + 1}/{self.episodes} | "
                    f"Reward: {episode_reward:.2f} | "
                    f"Len: {episode_length} | "
                    f"Eps: {self.agent.epsilon:.4f} | "
                    f"Loss: {avg_loss if avg_loss is not None else float('nan'):.4f} | "
                    f"Time: {elapsed:.1f}s"
                )

        self._save_checkpoint(self.episodes, is_final=True)
        self.monitor.close()

        return self.monitor.get_summary()

    def _evaluate_and_checkpoint(self, episode: int) -> None:
        """Evaluate the live policy network and register it if it is the best so far."""
        print(f"\nEvaluating at episode {episode}...")
        model = self.agent.policynet
        eval_results = evaluate_model_vs_random(model, games=50, device=self.device)
        self.monitor.log_evaluation(episode, eval_results)

        r = eval_results
        print(f"  vs Random: Win={r['win_rate']:.2%}, Loss={r['loss_rate']:.2%}, Draw={r['draw_rate']:.2%}")

        # "Best" is judged against the heuristic: beating random is too low a bar to rank checkpoints.
        heuristic = evaluate_model_vs_heuristic(model, games=100, device=self.device)
        self.monitor.log_evaluation(episode, {f"heuristic_{k}": v for k, v in heuristic.items()})
        win_rate = heuristic["win_rate"]
        print(f"  vs Heuristic: Win={win_rate:.2%}, Loss={heuristic['loss_rate']:.2%}, Draw={heuristic['draw_rate']:.2%}")

        current = self.registry._index["current"]
        if current and episode % (self.eval_interval * 2) == 0:
            wins, cur_wins, draws = play_match(model, self.registry.load_model(current), games=30, device=self.device)
            print(f"  vs {current}: Win={wins / 30:.2%}, Loss={cur_wins / 30:.2%}, Draw={draws / 30:.2%}")

        model.train()

        if win_rate > self.best_win_rate:
            self.best_win_rate = win_rate
            version = f"best_{episode}"
            self._save_weights()
            self.registry.register_model(
                WEIGHTS_PATH,
                version,
                metadata={"heuristic_win_rate": win_rate, "random_win_rate": r["win_rate"], "episode": episode},
                make_current=True,
            )
            print(f"  New best model! Win rate: {win_rate:.2%} (saved as {version})")

    def _save_weights(self) -> None:
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.agent.policynet.state_dict(), WEIGHTS_PATH)

    def _save_checkpoint(self, episode: int, is_final: bool = False) -> None:
        """Save model checkpoint."""
        version = f"ep{episode}" if not is_final else "final"
        self._save_weights()
        self.registry.register_model(
            WEIGHTS_PATH,
            version,
            metadata={"episode": episode, "is_final": is_final},
            make_current=False,
        )
        print(f"Checkpoint saved: {version}")


def train_enhanced(
    episodes: int = 10000,
    eval_interval: int = 500,
    checkpoint_interval: int = 500,
    registry_dir: str | Path = DEFAULT_REGISTRY_DIR,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """Main entry point for enhanced training."""
    trainer = EnhancedTrainer(
        episodes=episodes,
        eval_interval=eval_interval,
        checkpoint_interval=checkpoint_interval,
        registry_dir=registry_dir,
        log_dir=log_dir,
        device=device,
    )
    return trainer.train()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Mimika with evaluation, checkpoints and TensorBoard")
    parser.add_argument("--episodes", type=int, default=10000)
    parser.add_argument("--eval-interval", type=int, default=500)
    parser.add_argument("--checkpoint-interval", type=int, default=500)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    print(train_enhanced(args.episodes, args.eval_interval, args.checkpoint_interval, device=args.device))
