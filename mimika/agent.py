import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
from .model import TTDQNN
from .config import DQNconf as cfg


class DQNAgent:
    def __init__(self,device):
        self.device = device                                                # hardware allocation    
        self.memory = deque(maxlen=cfg.MEMORY_SIZE)                         # replay buffer to save transitions
        self.epsilon = cfg.EPS_START                                        # exploration param    
        self.policynet = TTDQNN().to(device)                               # best action selection from present state
        self.targnet = TTDQNN().to(device)                                  # baseline value to use as comparison for each transition
        self.targnet.load_state_dict(self.policynet.state_dict())
        
        self.optimizer = optim.Adam(self.policynet.parameters(),lr=cfg.LR)
        self.loss_fn = nn.MSELoss()
        
        
        # Function to define action state of valid actions
    def action_s(self,statetensor,action):
        if random.random() < self.epsilon:
            return random.choice(action)
        
        else:
            with torch.no_grad():
                qval = self.policynet(statetensor.to(self.device)).cpu().numpy()[0]
                qmask = np.full(cfg.BOARD_SIZE * cfg.BOARD_SIZE, -np.inf)
                for a in action:
                    qmask[a] = qval[a]
                
                return np.argmax(qmask)
            
    
    def optimality(self):
        """Run one Double-DQN replay update when a full batch is available."""
        if len(self.memory) < cfg.BATCH_SIZE:
            return
        # Sample batch of transition
        batch = random.sample(self.memory, cfg.BATCH_SIZE)
        state, action, reward, nextst, done = zip(*batch)
        
        stateb = torch.cat(state).to(self.device)
        actionb = torch.tensor(action, dtype=torch.long).unsqueeze(1).to(self.device)
        rewb = torch.tensor(reward, dtype = torch.float32).unsqueeze(1).to(self.device)
        nextstateb = torch.cat(nextst).to(self.device)
        doneb = torch.tensor(done, dtype=torch.float32).unsqueeze(1).to(self.device)

        current_q = self.policynet(stateb).gather(1, actionb)
        with torch.no_grad():
            # The policy network selects the next action; the target network evaluates it.
            next_actions = self.policynet(nextstateb).argmax(dim=1, keepdim=True)
            next_q = self.targnet(nextstateb).gather(1, next_actions)
            target_q = rewb + cfg.GAMMA * next_q * (1 - doneb)

        loss = self.loss_fn(current_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policynet.parameters(), max_norm=1.0)
        self.optimizer.step()
        return loss.item()
        
    def update_target_network(self):
        """Copies weights from the Policy Network to the Target Network."""
        self.targnet.load_state_dict(self.policynet.state_dict())
