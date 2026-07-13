import React, { useState, useEffect } from 'react';
import './App.css';

const API_BASE_URL = 'http://localhost:8000/api';

function App() {
  const [board, setBoard] = useState(Array(6).fill(Array(6).fill("")));
  const [currentPlayer, setCurrentPlayer] = useState("X");
  const [winnerCombo, setWinnerCombo] = useState([]);
  const [hasWinner, setHasWinner] = useState(false);
  const [isTied, setIsTied] = useState(false);
  
  const [gameMode, setGameMode] = useState("vs_player");
  const [difficulty, setDifficulty] = useState("medium"); 
  const [gameStarted, setGameStarted] = useState(false);
  const [playerName, setPlayerName] = useState("");
  const [playerStats, setPlayerStats] = useState(null);
  const [playerMarker, setPlayerMarker] = useState("X"); // Tracks if user is X or O

  const syncGameState = (data) => {
    setBoard(data.board);
    setCurrentPlayer(data.current_player);
    setWinnerCombo(data.winner_combo || []);
    setHasWinner(data.has_winner);
    setIsTied(data.is_tied);
  };

  const fetchPlayerProfile = async (username) => {
    try {
      const response = await fetch(`${API_BASE_URL}/player/${username}`);
      const data = await response.json();
      if (!data.error && !data.message) {
        setPlayerStats(data);
      } else {
        setPlayerStats(null);
      }
    } catch (err) {
      console.error("Failed to fetch Postgres records:", err);
    }
  };

  const handleGameInitialization = async (mode) => {
    const nameInput = prompt("Enter your username to register this play session:");
    if (!nameInput || nameInput.trim() === "") {
      alert("A valid user name identifier is mandatory to start!");
      return;
    }
    const cleanName = nameInput.trim();

    // Choice selector for AI Mode
    let chosenMarker = "X";
    if (mode === "vs_system") {
      const goFirst = window.confirm("Would you like to take the opening move as X? (Click OK for X, Cancel to let Bot play first as X while you play as O)");
      chosenMarker = goFirst ? "X" : "O";
    }

    await fetchPlayerProfile(cleanName);

    try {
      const response = await fetch(`${API_BASE_URL}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode, difficulty: difficulty, starting_player: chosenMarker })
      });
      const data = await response.json();

      syncGameState(data);
      setPlayerName(cleanName);
      setPlayerMarker(chosenMarker);
      setGameMode(mode);
      setGameStarted(true);
    } catch (err) {
      console.error("Initialization pipeline broken:", err);
    }
  };

  // Dedicated quick restart handler using current configurations
  const handlePlayAgain = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: gameMode, difficulty: difficulty, starting_player: playerMarker })
      });
      const data = await response.json();
      syncGameState(data);
    } catch (err) {
      console.error("Quick restart sequence broke:", err);
    }
  };

  const handleCellClick = async (row, col) => {
    if (hasWinner || isTied) return; 

    try {
      const response = await fetch(`${API_BASE_URL}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row, col })
      });
      const data = await response.json();

      syncGameState(data);

      if (data.has_winner || data.is_tied) {
        await processEndgame(data, playerName);
      }
    } catch (err) {
      console.error("Turn execution failed:", err);
    }
  };

  const processEndgame = async (finalData, activePlayerName) => {
    let result = "draws";
    
    if (finalData.has_winner) {
      // Corrected Flag Mapping: Because backend swaps player markers on turn end, 
      // if finalData.current_player matches your token, it means the *other* entity (AI) won!
      const humanWon = finalData.current_player !== playerMarker; 
      
      if (gameMode === "vs_system") {
        result = humanWon ? "wins" : "losses";
        alert(humanWon ? "🎉 You beat the AI!" : "🤖 The AI outsmarted you. Game Over!");
      } else {
        // PvP Win Messages
        const winningToken = finalData.current_player === "O" ? "X" : "O";
        alert(`Match completed! Player ${winningToken} wins!`);
        return; 
      }
    } else if (finalData.is_tied) {
      alert("Match concluded in an absolute tie!");
      if (gameMode !== "vs_system") return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/record-match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: activePlayerName,
          difficulty: difficulty,
          result: result
        })
      });
      const updatedStats = await response.json();
      setPlayerStats(updatedStats);
    } catch (err) {
      console.error("Postgres dashboard sync failed:", err);
    }
  };

  const isCoordinateInScorePath = (r, c) => {
    return winnerCombo.some(([sr, sc]) => sr === r && sc === c);
  };

  return (
    <div className="app-container">
      <h1>6x6 Tic-Tac-Toe Engine</h1>

      {!gameStarted ? (
        <div className="setup-screen">
          <h2>Select Configuration</h2>
          
          <div className="difficulty-selector">
            <label>AI Difficulty: </label>
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="easy">Easy (Random)</option>
              <option value="medium">Medium (Heuristic Balance)</option>
              <option value="hard">Hard (Heuristic Aggressive)</option>
            </select>
          </div>

          <div className="mode-buttons">
            <button onClick={() => handleGameInitialization("vs_player")}>👥 Player vs Player</button>
            <button onClick={() => handleGameInitialization("vs_system")}>🤖 Player vs System (AI)</button>
          </div>
        </div>
      ) : (
        <div className="game-screen">
          <div className="status-bar">
            {hasWinner ? (
              <span className="status-text win">🏆 Match Decided!</span>
            ) : isTied ? (
              <span className="status-text tie">🤝 Match Tied!</span>
            ) : (
              <span className="status-text">Active Turn: <strong className={currentPlayer}>{currentPlayer}</strong></span>
            )}
          </div>

          <div className="grid-container">
            {board.map((row, rowIndex) => (
              <div key={rowIndex} className="grid-row">
                {row.map((cellValue, colIndex) => (
                  <button
                    key={colIndex}
                    className={`grid-cell ${cellValue} ${isCoordinateInScorePath(rowIndex, colIndex) ? 'winner-highlight' : ''}`}
                    onClick={() => handleCellClick(rowIndex, colIndex)}
                  >
                    {cellValue}
                  </button>
                ))}
              </div>
            ))}
          </div>
          
          <div className="action-buttons-row">
            {(hasWinner || isTied) && (
              <button className="play-again-btn" onClick={handlePlayAgain}>Play Again</button>
            )}
            <button className="back-btn" onClick={() => setGameStarted(false)}>Main Menu</button>
          </div>
        </div>
      )}

      <hr className="divider" />

      <div className="leaderboard-section">
        <h2>📊 Active Player Postgres Dashboard</h2>
        {playerStats ? (
          <div className="stats-container">
            <h3>Player Profile: <strong>{playerName}</strong></h3>
            <table className="score-table">
              <thead>
                <tr>
                  <th>Difficulty</th>
                  <th>Wins</th>
                  <th>Losses</th>
                  <th>Draws</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>🟢 Easy</td>
                  <td>{playerStats.easy_wins}</td>
                  <td>{playerStats.easy_losses}</td>
                  <td>{playerStats.easy_draws}</td>
                </tr>
                <tr>
                  <td>🟡 Medium</td>
                  <td>{playerStats.medium_wins}</td>
                  <td>{playerStats.medium_losses}</td>
                  <td>{playerStats.medium_draws}</td>
                </tr>
                <tr>
                  <td>🔴 Hard</td>
                  <td>{playerStats.hard_wins}</td>
                  <td>{playerStats.hard_losses}</td>
                  <td>{playerStats.hard_draws}</td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="no-scores">Log in above to view historical Postgres stats tracking records.</p>
        )}
      </div>
    </div>
  );
}

export default App;