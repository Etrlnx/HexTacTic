# Settings panel for the bot

class DQNconf:
    BOARD_SIZE = 6
    IP_CHANNELS = 3
    
    LR = 0.001              # learning rate
    GAMMA = 0.99            # discount factor
    BATCH_SIZE = 64
    MEMORY_SIZE = 50000     # memory buffer size
    
    
    # Decay calculation
    EPS_START = 1.0
    EPS_MIN = 0.05
    EPS_DECAY = 0.995
    
    # Network update parameters
    TARGET_UPD_FREQ = 1000