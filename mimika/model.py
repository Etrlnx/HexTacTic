import torch
import torch.nn as nn

# this class takes the 6x6 board as input gives 36 Q-values as output
# i/p: 6x6 state spaces
# o/p: 36 q-values to represent each state space
class TTDQNN(nn.Module):
    def __init__(self,board_size=6):
        super().__init__()
        self.board_size = board_size
        
        # CNN to scan the board using a 3x3 convolution filter
        # Detects horizontal, vertical, diagonal patterns
        self.conv = nn.Sequential(nn.Conv2d(in_channels=3,out_channels=32,kernel_size=3, padding=1),
                                  nn.ReLU(), nn.Conv2d(in_channels=32, out_channels=64,kernel_size=3,padding=1),
                                  nn.ReLU()
                                  )
        
        # FC layer to process flattened spatial features into 36 q-values
        self.fc = nn.Sequential(
            nn.Linear(64 * board_size * board_size, 128),
            nn.ReLU(),  
            nn.Linear(128, board_size * board_size)
        )
    
    # forward pass
    def forward(self,x):
        x = self.conv(x)
        x = x.view(x.size(0),-1)
        return self.fc(x)
    
        