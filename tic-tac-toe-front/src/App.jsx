import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  // Core Game State synced from FastAPI Backend
  const [board, setBoard] = useState(Array(6).fill(Array(6).fill("")));
  const [currentPlayer, setCurrentPlayer] = useState("X");
  const [scores, setScores] = useState({ X: 0, O: 0 });
  const [winningSegments, setWinningSegments] = useState([]);
  const [isFilled, setIsFilled] = useState(false);
  const [winner, setWinner] = useState(null);
  
  // Custom Frontend Management States
  const [gameMode, setGameMode] = useState("vs_player");
  const [gameStarted, setGameStarted] = useState(false);
  const [playerName, setPlayerName] = useState("");
  const [leaderboard, setLeaderboard] = useState([]);

  // Fetch local scores automatically when the website mounts
  useEffect(() => {
    fetchScores();
  }, []);

  const fetchScores = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/scores');
      const data = await response.json();
      setLeaderboard(data);
    } catch (err) {
      console.error("Failed to fetch leaderboard records:", err);
    }
  };

  // Pre-game Prompt Sequence
  const handleGameInitialization = async (mode) => {
    // 1. Gather player name details immediately upon choosing mode
    const nameInput = prompt("Enter your name to register this play session:");
    if (!nameInput || nameInput.trim() === "") {
      alert("A valid user name identifier is mandatory to start!");
      return;
    }
    const cleanName = nameInput.trim();

    // 2. If vs_system, let them choose if they want to go first
    let choice = "X"; 
    if (mode === "vs_system") {
      const goFirst = window.confirm("Would you like to take the opening move? (Click OK for Yes, Cancel for Bot First)");
      choice = goFirst ? "X" : "O";
    }

    try {
      const response = await fetch('http://localhost:5000/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode, starting_player: choice })
      });
      const data = await response.json();

      // Sync the backend's initial game state with React
      setBoard(data.board);
      setCurrentPlayer(data.current_player);
      setScores(data.scores);
      setWinningSegments(data.winning_segments);
      setIsFilled(data.is_filled);
      setWinner(data.winner);
      
      setPlayerName(cleanName);
      setGameMode(mode);
      setGameStarted(true);
    } catch (err) {
      console.error("Initialization pipeline broken:", err);
    }
  };

  // Turn Trigger
  const handleCellClick = async (row, col) => {
    if (isFilled) return; // Prevent clicking if the grid is completely full

    try {
      const response = await fetch('http://localhost:5000/api/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row, col })
      });
      const data = await response.json();

      // Update state live
      setBoard(data.board);
      setCurrentPlayer(data.current_player);
      setScores(data.scores);
      setWinningSegments(data.winning_segments);
      setIsFilled(data.is_filled);
      setWinner(data.winner);

      // Check if this move filled the final box
      if (data.is_filled) {
        processEndgame(data, playerName);
      }
    } catch (err) {
      console.error("Turn execution failed:", err);
    }
  };

  // Endgame evaluation and Leaderboard filtering
  const processEndgame = async (finalData, activePlayerName) => {
    // Constraint Rule: If Bot wins or ties against Human, stop right here
    if (finalData.game_mode === "vs_system" && finalData.winner !== "X") {
      alert(`Game Over! Final scores: ${activePlayerName} (X): ${finalData.scores.X} vs Bot (O): ${finalData.scores.O}. The bot wins/ties, blocking leaderboard submission.`);
      return;
    }

    let highscoreWinnerName = activePlayerName;
    
    // Manage nomenclature formatting for local PVP
    if (finalData.game_mode === "vs_player") {
      if (finalData.winner === "O") highscoreWinnerName = "Player O";
      else if (finalData.winner === "Tie") {
        alert(`Match concluded in an absolute tie! (${finalData.scores.X} vs ${finalData.scores.O}) No database entries added.`);
        return;
      }
    }

    alert(`Congratulations ${highscoreWinnerName}! Submitting your victory track record.`);

    try {
      const response = await fetch('http://localhost:5000/api/scores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: highscoreWinnerName })
      });
      const updatedLeaderboard = await response.json();
      setLeaderboard(updatedLeaderboard);
    } catch (err) {
      console.error("Highscore database sync failed:", err);
    }
  };

  // Helper styling module to evaluate if a square belongs to a scored triplet path
  const isCoordinateInScorePath = (r, c) => {
    return winningSegments.some(segment => 
      segment.some(([sr, sc]) => sr === r && sc === c)
    );
  };

  return (
    <div className="app-container">
      <h1>Welcome</h1>

      {!gameStarted ? (
        <div className="setup-screen">
          <h2>Select Game Mode</h2>
          <div className="mode-buttons">
            <button onClick={() => handleGameInitialization("vs_player")}>👥 Player vs Player</button>
            <button onClick={() => handleGameInitialization("vs_system")}>🤖 Player vs System (AI)</button>
          </div>
        </div>
      ) : (
        <div className="game-screen">
          {/* Top Score Matrix Display */}
          <div className="scoreboard-panel">
            <div className="score-node X">
              <span className="label">{gameMode === "vs_system" ? playerName : "Player X"}</span>
              <span className="count">{scores.X} pts</span>
            </div>
            <div className="score-node O">
              <span className="label">{gameMode === "vs_system" ? "Bot" : "Player O"}</span>
              <span className="count">{scores.O} pts</span>
            </div>
          </div>

          <div className="status-bar">
            {isFilled ? (
              <span className="status-text win">
                🏆 Winner: {winner === "Tie" ? "It's a Tie!" : winner}
              </span>
            ) : (
              <span className="status-text">Active Turn: <strong className={currentPlayer}>{currentPlayer}</strong></span>
            )}
          </div>

          {/* Grid Layout Canvas */}
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
          
          <button className="back-btn" onClick={() => setGameStarted(false)}>⚙️ Main Menu</button>
        </div>
      )}

      <hr className="divider" />

      {/* Leaderboard Table Footer Rendering */}
      <div className="leaderboard-section">
        <h2>🏆 Local High Scores (Top Wins)</h2>
        {leaderboard.length === 0 ? (
          <p className="no-scores">No wins recorded yet.</p>
        ) : (
          <table className="score-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Player Name</th>
                <th>Total Wins</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((row, index) => (
                <tr key={index}>
                  <td>{index + 1}</td>
                  <td>{row.player_name}</td>
                  <td>{row.wins}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default App;