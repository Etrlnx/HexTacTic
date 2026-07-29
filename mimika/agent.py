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
        if len(self.memory) < cfg.BATCH_SIZE:
            return
        # Sample batch of transition
        batch = random.sample(self.memory, cfg.BATCH_SIZE)
        state, action, reward, nextst, done = zip(*batch)
        
        stateb = torch.cat(state).to(self.device)
        actionb = torch.tensor(action, dtype=torch.long).unsqueeze(1).to(self.device)
        rewb = torch.tensor(reward, dtype = torch.float32).unsqueeze(1).to(self.device)
        
    def update_target_network(self):
        """Copies weights from the Policy Network to the Target Network."""
        self.targnet.load_state_dict(self.policynet.state_dict())
        
        
            