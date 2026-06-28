# Resonance-Toe (6x6 Tic-Tac-Toe with FastAPI & React)

A full-stack, 6x6 modern Tic-Tac-Toe game implementing an atypical **5-in-a-row winning condition**. Built with a high-performance **FastAPI** backend, a lightweight **SQLite** persistence layer, and a highly responsive **React (Vite)** frontend, this architecture shifts core game-state arbitration and validation entirely to the server side.

## 🚀 Features

- **Dynamic 6x6 Grid Mapping:** Expands traditional grid dimensions to a 6x6 framework requiring a 5-token streak (horizontal, vertical, or diagonal) to secure a win.
- **State-Synchronized Architecture:** The React UI functions as a pure presentation layer; all coordinate validations, turn-toggling, and streak computations are managed dynamically via FastAPI endpoints.
- **Persistent High-Score Tracking:** Features an integrated SQLite database that logs player metrics, ranking the top 5 highest-winning players on a local leaderboard.
- **Hybrid Gameplay Modes:** Supports local Player vs. Player (PvP) match configurations alongside an automated Player vs. System (AI) mode.

---

## 📊 Architecture & Data Flow


```

┌────────────────────────┐                   ┌────────────────────────┐
│    React Frontend      │   HTTP POST/GET   │    FastAPI Backend     │
│   (App.jsx / App.css)  ├──────────────────>│       (app.py)         │
└───────────┬────────────┘                   └───────────┬────────────┘
│                                            │
│ State Sync                                 │ Logic / Query
▼                                            ▼
┌────────────────────────┐                   ┌────────────────────────┐
│ Interactive 6x6 Canvas │                   │   SQLite Database      │
│  & Live Score Panel    │                   │      (scores.db)       │
└────────────────────────┘                   └────────────────────────┘

```

1. **Initialization:** The UI calls `/api/start` to declare game modes (`vs_player` or `vs_system`) and set up token configurations.
2. **Turn Execution:** Every square interaction triggers a payload containing raw matrix indices `(row, col)` sent to `/api/move`. 
3. **State Processing:** The backend evaluates cell validity, registers the coordinates, updates matrix arrays, and evaluates directional geometry vectors to detect a win or tie condition.
4. **State Deserialization:** The updated game-state package updates the UI context, highlighting winning coordinates and handling endgame logic.

---

## 🛠️ Project Structure


```

├── app.py              # FastAPI Main Application & Routing Pipeline
├── script.py           # Core Game Logic (Matrix Evaluations & Coordinate Processing)
├── database.py         # SQLite Persistence Interface & High Score Top-5 Queries
├── App.jsx             # React UI Layout, Async Fetch Dispatches, & State Anchors
├── App.css             # Root Variable Styling & Pulse Animation Configurations
└── README.md           # Documentation

```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js (v18+) & npm

### Backend Configuration
1. Navigate to the backend or project root directory and install dependencies:
   ```bash
   pip install fastapi uvicorn pydantic

```

2. Launch the FastAPI server using Uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 5000 --reload

```



### Frontend Configuration

1. Install dependencies and start the local development environment:
```bash
npm install
npm run dev

```


2. The UI will spin up natively on port `5173`. Open `http://localhost:5173` in your browser.

---

## 🔮 Roadmap & Technical Upgrades

* **Heuristic AI Engine:** Upgrade the current randomizer system to a Minimax algorithm enhanced with Alpha-Beta Pruning or a heuristic-based evaluation engine optimized for larger (6x6) search-spaces.
* **Dynamic Difficulty Tiers:** Implement multi-level difficulty settings (`Easy`, `Medium`, `Hard`) by introducing bounded depth limits and probabilistic non-optimal choices inside the AI turn analyzer.
* **Advanced Server Architecture:** Scale up the persistence layer to track deeper match statistics, such as player loss ratios, specific win margins against the bot, and timestamped history tracking.

```
