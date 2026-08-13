import random
import numpy as np
import torch
import torch.nn.functional as F
import torch.optim as optim
from collections import deque

from .model import TTDQNN
from .config import DQNconf as cfg


class DQNAgent:
    def __init__(self, device):
        self.device = device
        self.memory = deque(maxlen=cfg.MEMORY_SIZE)
        self.epsilon = cfg.EPS_START
        self.policynet = TTDQNN().to(device)
        self.targnet = TTDQNN().to(device)
        self.targnet.load_state_dict(self.policynet.state_dict())
        self.targnet.eval()
        self.optimizer = optim.Adam(self.policynet.parameters(), lr=cfg.LR)

    def action_s(self, state_tensor, valid_actions):
        if random.random() < self.epsilon:
            return random.choice(valid_actions)

        with torch.no_grad():
            q_values = self.policynet(state_tensor.to(self.device)).cpu().numpy()[0]
            q_mask = np.full(cfg.BOARD_SIZE * cfg.BOARD_SIZE, -np.inf)
            for action in valid_actions:
                q_mask[action] = q_values[action]
            return int(np.argmax(q_mask))

    def optimality(self):
        """Run one Double-DQN replay update when a full batch is available."""
        if len(self.memory) < cfg.BATCH_SIZE:
            return None

        batch = random.sample(self.memory, cfg.BATCH_SIZE)
        state, action, reward, next_state, done = zip(*batch)

        state_batch = torch.cat(state).to(self.device)
        action_batch = torch.tensor(action, dtype=torch.long, device=self.device).unsqueeze(1)
        reward_batch = torch.tensor(reward, dtype=torch.float32, device=self.device).unsqueeze(1)
        next_state_batch = torch.cat(next_state).to(self.device)
        done_batch = torch.tensor(done, dtype=torch.float32, device=self.device).unsqueeze(1)

        current_q = self.policynet(state_batch).gather(1, action_batch)
        with torch.no_grad():
            next_actions = self.policynet(next_state_batch).argmax(dim=1, keepdim=True)
            next_q = self.targnet(next_state_batch).gather(1, next_actions)
            target_q = reward_batch + cfg.GAMMA * next_q * (1 - done_batch)

        loss = F.mse_loss(current_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policynet.parameters(), max_norm=1.0)
        self.optimizer.step()
        return loss.item()

    def update_target_network(self):
        self.targnet.load_state_dict(self.policynet.state_dict())
