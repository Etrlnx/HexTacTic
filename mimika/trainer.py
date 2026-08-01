import torch
from script import TicTacToeGame
from .agent import DQNAgent
from .config import DQNconf as cfg
import numpy as np
import os

# NN uses a tensor of dims (Channels, height, width) -> (3,6,6)
# Channel 0 -> board state spaces: 1 = empty  | 0 = marked
# Channel 1 -> position of player's moves: 1 = yes | 0 = no
# Channel 2 -> position of opponent's moves: 1 = yes | 0 = no
# This function converts the game board to a 4D PyTorch tensor 
def preproc_s(board_state: list, curr_player: str) -> torch.Tensor:
    
    
    bnp = np.array(board_state)
    opp = "O" if curr_player == "X" else "X"
    
    empty = (bnp == "").astype(np.float32)
    playerchan = (bnp == curr_player).astype(np.float32)
    oppchan = (bnp == opp).astype(np.float32)
    
    stackstate = np.stack([empty, playerchan, oppchan], axis = 0) # feature matrix
    tensorstate = torch.FloatTensor(stackstate).unsqueeze(0)      # matrix -> tensor, dimensions: (1,3,6,6) 
    # 4- dimensional tensors are more batch-efficient to train in the GPU and reduces training complexity
    return tensorstate


def train(episodes=10000):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent = DQNAgent(device)
    totsteps = 0
    
    for ep in range(episodes):
        game = TicTacToeGame()
        hist = {
            "X": {"state": None, "action": None, "score": 0, "reward": 0.0},
            "O": {"state": None, "action": None, "score": 0, "reward": 0.0}
        }

        # Game loop
        while not game._has_winner and not game.is_tied():
            curr_p = game.current_player
            opp_p = "O" if curr_p == "X" else "X"
            
            valmoves = []
            for r in range(cfg.BOARD_SIZE):
                for c in range(cfg.BOARD_SIZE):
                    if game.is_valid_move(r, c):
                        valmoves.append(r * cfg.BOARD_SIZE + c)
            
            if not valmoves:
                break
        
            statetensor = preproc_s(game._current_moves, curr_p)
            actionidx = agent.action_s(statetensor, valmoves)
            row, col = actionidx // cfg.BOARD_SIZE, actionidx % cfg.BOARD_SIZE
            
            # Record opponent transition once active player responds
            if hist[opp_p]['state'] is not None:
                agent.memory.append((hist[opp_p]['state'], hist[opp_p]['action'], hist[opp_p]['reward'], statetensor, False))
            
            prevscore = game.scores[curr_p]
            game.process_move(row, col)
            newscore = game.scores[curr_p]
            
            # Intermediate line rewards
            ptsgained = newscore - prevscore
            stepreward = -0.1 + (ptsgained * 10.0)
            
            hist[curr_p]['state'] = statetensor
            hist[curr_p]['action'] = actionidx
            hist[curr_p]['score'] = newscore
            hist[curr_p]['reward'] = stepreward
            
            # In-step training pass
            agent.optimality()
            totsteps += 1
            
            if totsteps % cfg.TARGET_UPD_FREQ == 0:
                agent.update_target_network()
                
        # 1. Terminal state recording
        dummyfinal = preproc_s(game._current_moves, 'X')
        for p in ['X', 'O']:
            if hist[p]['state'] is not None:
                if game._has_winner:
                    finalr = 30.0 if game.scores[p] >= 3 else -30.0
                else:
                    finalr = 0.0
                    
                agent.memory.append((
                    hist[p]["state"],
                    hist[p]["action"],
                    finalr,
                    dummyfinal,
                    True
                ))

        # 2. Terminal transition training step (10 batch passes to consolidate game-ending rewards)
        for _ in range(10):
            agent.optimality()

        # Decay exploration rate
        agent.epsilon = max(cfg.EPS_MIN, agent.epsilon * cfg.EPS_DECAY)
        
        # Periodic status update & periodic model checkpointing
        if (ep + 1) % 500 == 0:
            print(f"Episode {ep + 1}/{episodes} | Epsilon: {agent.epsilon:.4f}")
            os.makedirs("saved_models", exist_ok=True)
            torch.save(agent.policynet.state_dict(), "saved_models/dqn_model_weights.pth")
            
    
    # Final save upon training completion
    os.makedirs("saved_models", exist_ok=True)
    torch.save(agent.policynet.state_dict(), "saved_models/dqn_model_weights.pth")    
    print("Training complete! Model weights saved to saved_models/dqn_model_weights.pth")
    print("Donezo")
