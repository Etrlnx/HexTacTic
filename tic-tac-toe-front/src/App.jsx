import { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000/ws';

const SOUNDS = {
  move: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  win: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  lose: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  draw: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
};

function playSound(name) {
  try {
    const audio = new Audio(SOUNDS[name]);
    audio.volume = 0.3;
    audio.play().catch(() => {});
  } catch { /* audio not supported */ }
}

function App() {
  const [board, setBoard] = useState(Array(6).fill(Array(6).fill("")));
  const [currentPlayer, setCurrentPlayer] = useState("X");
  const [winnerCombo, setWinnerCombo] = useState([]);
  const [hasWinner, setHasWinner] = useState(false);
  const [isTied, setIsTied] = useState(false);
  const [scores, setScores] = useState({ X: 0, O: 0 });

  const [gameMode, setGameMode] = useState("vs_player");
  const [difficulty, setDifficulty] = useState("Normal");
  const [gameStarted, setGameStarted] = useState(false);
  const [playerName, setPlayerName] = useState("");
  const [playerStats, setPlayerStats] = useState(null);
  const [playerMarker, setPlayerMarker] = useState("X");

  const [moveHistory, setMoveHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [focusedCell, setFocusedCell] = useState({ row: 0, col: 0 });
  const [gameResult, setGameResult] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [wsSessionId, setWsSessionId] = useState(null);
  const [opponentConnected, setOpponentConnected] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const boardRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  // Latest values for WebSocket callbacks, which outlive the render that created them.
  const latest = useRef({});

  const syncGameState = useCallback((data) => {
    setBoard(data.board);
    setCurrentPlayer(data.current_player);
    setWinnerCombo(data.winner_combo || []);
    setHasWinner(data.has_winner);
    setIsTied(data.is_tied);
    setScores(data.scores || { X: 0, O: 0 });
  }, []);

  const fetchPlayerProfile = useCallback(async (username) => {
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
  }, []);

  const connectWebSocket = useCallback((wsSession, marker) => {
    if (wsRef.current) {
      wsRef.current.onclose = null; // intentional close: don't trigger a reconnect to the old session
      wsRef.current.close();
    }
    clearTimeout(reconnectTimeoutRef.current);

    const ws = new WebSocket(`${WS_BASE_URL}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connecting');
      reconnectAttempts.current = 0;
      ws.send(JSON.stringify({ type: 'join', session_id: wsSession, marker }));
    };

    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (e) {
        console.error('WS message parse error:', e);
        return;
      }
      latest.current.handleWSMessage(message);
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      const { gameStarted, gameMode, wsSessionId, playerMarker, connectWebSocket: reconnect } = latest.current;
      if (gameStarted && gameMode === 'vs_player_ws' && reconnectAttempts.current < 5) {
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 10000);
        reconnectAttempts.current++;
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnect(wsSessionId, playerMarker);
        }, delay);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setConnectionStatus('error');
    };
  }, []);

  const handleWSMessage = useCallback((message) => {
    const { type, payload } = message;

    switch (type) {
      case 'created':
        setWsSessionId(payload.session_id);
        setPlayerMarker(payload.marker);
        setConnectionStatus('connected');
        break;

      case 'joined':
        syncGameState(payload);
        setWsSessionId(payload.session_id);
        setPlayerMarker(payload.your_marker);
        setConnectionStatus('connected');
        setOpponentConnected(false);
        break;

      case 'ready':
        setOpponentConnected(true);
        break;

      case 'state':
        if (payload.your_marker) {
          setPlayerMarker(payload.your_marker);
        }
        syncGameState(payload);
        break;

      case 'game_over':
        setHasWinner(!!payload.winner);
        setIsTied(payload.is_tied);
        if (payload.winner_combo) {
          setWinnerCombo(payload.winner_combo);
        }
        if (payload.winner) {
          playSound(payload.winner === playerMarker ? 'win' : 'lose');
          setGameResult(payload.winner === playerMarker ? 'win' : 'lose');
        } else {
          playSound('draw');
          setGameResult('draw');
        }
        break;

      case 'opponent_disconnected':
        setOpponentConnected(false);
        alert(payload.message);
        break;

      case 'error':
        alert(payload);
        break;

      case 'pong':
        break;

      default:
        console.log('Unknown WS message type:', type);
    }
  }, [syncGameState, playerMarker]);

  useEffect(() => {
    latest.current = { gameStarted, gameMode, wsSessionId, playerMarker, handleWSMessage, connectWebSocket };
  });

  const handleGameInitialization = useCallback(async (mode) => {
    const nameInput = prompt("Enter your username to register this play session:");
    if (!nameInput || nameInput.trim() === "") {
      alert("A valid user name identifier is mandatory to start!");
      return;
    }
    const cleanName = nameInput.trim();

    let chosenMarker = "X";
    if (mode === "vs_system") {
      const goFirst = window.confirm("Would you like to take the opening move as X? (Click OK for X, Cancel to let Bot play first as X while you play as O)");
      chosenMarker = goFirst ? "X" : "O";
    }

    if (mode === "vs_player_ws") {
      try {
        const response = await fetch(`${API_BASE_URL}/ws/create`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        setWsSessionId(data.session_id);
        setPlayerMarker('X');
        setConnectionStatus('connecting');
        connectWebSocket(data.session_id, 'X');
      } catch (err) {
        console.error("WS session creation failed:", err);
        alert("Failed to create WebSocket session");
        return;
      }
    } else {
      try {
        const response = await fetch(`${API_BASE_URL}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: mode, difficulty: difficulty, starting_player: chosenMarker })
        });
        const data = await response.json();
        syncGameState(data);
        setSessionId(data.session_id);
        setPlayerMarker(chosenMarker);
      } catch (err) {
        console.error("Initialization pipeline broken:", err);
        return;
      }
    }

    setPlayerName(cleanName);
    setGameMode(mode);
    setGameStarted(true);
    setMoveHistory([]);
    setFocusedCell({ row: 0, col: 0 });
    setGameResult(null);
    void fetchPlayerProfile(cleanName);
  }, [difficulty, syncGameState, fetchPlayerProfile, connectWebSocket]);

  const handlePlayAgain = useCallback(async () => {
    if (gameMode === 'vs_player_ws') {
      try {
        const response = await fetch(`${API_BASE_URL}/ws/create`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        setWsSessionId(data.session_id);
        setPlayerMarker('X');
        connectWebSocket(data.session_id, 'X');
      } catch (err) {
        console.error("WS session creation failed:", err);
      }
    } else {
      try {
        const response = await fetch(`${API_BASE_URL}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: gameMode, difficulty: difficulty, starting_player: playerMarker })
        });
        const data = await response.json();
        syncGameState(data);
        setSessionId(data.session_id);
      } catch (err) {
        console.error("Quick restart sequence broke:", err);
      }
    }
    setMoveHistory([]);
    setFocusedCell({ row: 0, col: 0 });
    setGameResult(null);
    setHasWinner(false);
    setIsTied(false);
  }, [gameMode, difficulty, playerMarker, syncGameState, connectWebSocket]);

  const recordMoveInHistory = useCallback((row, col, player, isAi = false) => {
    setMoveHistory(prev => [...prev, { row, col, player, isAi, timestamp: Date.now() }]);
  }, []);

  const processEndgame = useCallback(async (finalData, activePlayerName) => {
    let result = "draw";

    if (finalData.has_winner) {
      const humanWon = finalData.current_player === playerMarker;

      if (gameMode === "vs_system") {
        result = humanWon ? "win" : "loss";
        playSound(humanWon ? 'win' : 'lose');
        setGameResult(humanWon ? 'win' : 'lose');
        alert(humanWon ? "You beat the AI!" : "The AI outsmarted you. Game Over!");
      } else {
        const winningToken = finalData.current_player;
        alert(`Match completed! Player ${winningToken} wins!`);
        setGameResult('win');
        return;
      }
    } else if (finalData.is_tied) {
      playSound('draw');
      setGameResult('draw');
      alert("Match concluded in an absolute tie!");
      if (gameMode !== "vs_system") return;
    }

    if (gameMode !== 'vs_player_ws') {
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
        if (!response.ok) throw new Error(updatedStats.detail || response.statusText);
        setPlayerStats(updatedStats);
      } catch (err) {
        console.error("Postgres dashboard sync failed:", err);
      }
    }
  }, [gameMode, playerMarker, difficulty]);

  const handleCellClick = useCallback(async (row, col) => {
    if (hasWinner || isTied) return;

    if (gameMode === 'vs_player_ws') {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'move', row, col }));
      }
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, row, col })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      if (data.board[row][col] === board[row][col]) return; // rejected move, state unchanged

      recordMoveInHistory(row, col, currentPlayer);
      // In vs_system the AI replies within the same request: any other newly filled cell is its move.
      data.board.forEach((cells, r) => cells.forEach((cell, c) => {
        if (cell && !board[r][c] && !(r === row && c === col)) recordMoveInHistory(r, c, cell, true);
      }));
      syncGameState(data);

      if (data.has_winner || data.is_tied) {
        playSound(data.has_winner ? 'win' : 'draw');
        await processEndgame(data, playerName);
      } else {
        playSound('move');
      }
    } catch (err) {
      console.error("Turn execution failed:", err);
    }
  }, [hasWinner, isTied, gameMode, sessionId, board, currentPlayer, playerName, recordMoveInHistory, syncGameState, processEndgame]);

  const handleKeyDown = useCallback((e) => {
    if (!gameStarted || hasWinner || isTied) return;

    let { row, col } = focusedCell;
    const maxIndex = 5;

    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        setFocusedCell(prev => ({ ...prev, row: Math.max(0, prev.row - 1) }));
        break;
      case 'ArrowDown':
        e.preventDefault();
        setFocusedCell(prev => ({ ...prev, row: Math.min(maxIndex, prev.row + 1) }));
        break;
      case 'ArrowLeft':
        e.preventDefault();
        setFocusedCell(prev => ({ ...prev, col: Math.max(0, prev.col - 1) }));
        break;
      case 'ArrowRight':
        e.preventDefault();
        setFocusedCell(prev => ({ ...prev, col: Math.min(maxIndex, prev.col + 1) }));
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (board[row][col] === "") {
          handleCellClick(row, col);
        }
        break;
      case 'h':
      case 'H':
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          setShowHistory(prev => !prev);
        }
        break;
      default:
        break;
    }
  }, [gameStarted, hasWinner, isTied, focusedCell, board, handleCellClick]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [handleKeyDown]);

  const isCoordinateInScorePath = (r, c) => {
    return winnerCombo.some(([sr, sc]) => sr === r && sc === c);
  };

  const getCellAriaLabel = (row, col, cellValue) => {
    if (cellValue) return `Cell ${row + 1}, ${col + 1}, occupied by ${cellValue}`;
    return `Cell ${row + 1}, ${col + 1}, empty. Press Enter to place ${currentPlayer}`;
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return '#10b981';
      case 'connecting': return '#f59e0b';
      case 'error': return '#ef4444';
      default: return '#64748b';
    }
  };

  return (
    <div className="app-container" role="application" aria-label="6x6 Tic-Tac-Toe Game">
      <h1>6x6 Tic-Tac-Toe Engine</h1>

      {!gameStarted ? (
        <div className="setup-screen">
          <h2>Select Configuration</h2>

          <div className="difficulty-selector">
            <label htmlFor="difficulty-select">Difficulty Level: </label>
            <select
              id="difficulty-select"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
            >
              <option value="Easy">Easy</option>
              <option value="Normal">Normal</option>
              <option value="Hard">Hard</option>
              {(playerStats?.highest_difficulty === "Hard" || playerStats?.highest_difficulty === "Nightmare") && (
                <option value="Nightmare">Nightmare (DDQN AI)</option>
              )}
            </select>
          </div>

          <div className="mode-buttons">
            <button onClick={() => handleGameInitialization("vs_player")}>Player vs Player (HTTP)</button>
            <button onClick={() => handleGameInitialization("vs_player_ws")}>Player vs Player (Real-time WebSocket)</button>
            <button onClick={() => handleGameInitialization("vs_system")}>Player vs System (AI)</button>
          </div>
        </div>
      ) : (
        <div className="game-screen">
          <div className="status-bar" role="status" aria-live="polite">
            <div className="score-display">
              Points Scoreboard:
              <span className="X"> X: {scores.X} /3</span> |
              <span className="O">O: {scores.O}/3</span>
            </div>
            {gameMode === 'vs_player_ws' && (
              <div className="connection-indicator" style={{ marginTop: '0.5rem' }}>
                <span className="connection-dot" style={{ backgroundColor: getConnectionStatusColor() }}></span>
                <span className="connection-text">
                  {connectionStatus === 'connected' ? (opponentConnected ? 'Connected • Opponent ready' : 'Connected • Waiting for opponent...') :
                   connectionStatus === 'connecting' ? 'Connecting...' :
                   connectionStatus === 'error' ? 'Connection error' : 'Disconnected'}
                </span>
                {wsSessionId && (
                  <button className="session-id-btn" onClick={() => navigator.clipboard.writeText(wsSessionId)}>
                    Share ID: {wsSessionId}
                  </button>
                )}
              </div>
            )}
            {hasWinner ? (
              <span className="status-text win">Match Decided!</span>
            ) : isTied ? (
              <span className="status-text tie">Match Tied!</span>
            ) : (
              <span className="status-text">
                Active Turn:
                <strong className={currentPlayer} aria-live="assertive">{currentPlayer}</strong>
              </span>
            )}
          </div>

          <div className="game-main">
            <div className="grid-container" role="grid" aria-label="Game board" ref={boardRef}>
              {board.map((row, rowIndex) => (
                <div key={rowIndex} className="grid-row" role="row">
                  {row.map((cellValue, colIndex) => (
                    <button
                      key={colIndex}
                      className={`grid-cell ${cellValue} ${isCoordinateInScorePath(rowIndex, colIndex) ? 'winner-highlight' : ''} ${focusedCell.row === rowIndex && focusedCell.col === colIndex ? 'focused' : ''}`}
                      onClick={() => handleCellClick(rowIndex, colIndex)}
                      disabled={hasWinner || isTied || cellValue !== "" || (gameMode === 'vs_player_ws' && currentPlayer !== playerMarker)}
                      role="gridcell"
                      aria-label={getCellAriaLabel(rowIndex, colIndex, cellValue)}
                      aria-selected={focusedCell.row === rowIndex && focusedCell.col === colIndex}
                      tabIndex={focusedCell.row === rowIndex && focusedCell.col === colIndex ? 0 : -1}
                    >
                      {cellValue}
                    </button>
                  ))}
                </div>
              ))}
            </div>

            <div className="side-panel">
              <div className="controls">
                <button className="history-toggle" onClick={() => setShowHistory(!showHistory)}>
                  {showHistory ? 'Hide' : 'Show'} Move History
                </button>
                <div className="keyboard-hint">
                  <kbd>↑↓←→</kbd> Navigate &nbsp;
                  <kbd>Enter</kbd> Place &nbsp;
                  <kbd>Ctrl+H</kbd> History
                </div>
              </div>

              {showHistory && moveHistory.length > 0 && (
                <div className="move-history" role="log" aria-label="Move history">
                  <h3>Move History</h3>
                  <ul>
                    {moveHistory.map((move, idx) => (
                      <li key={idx} className={move.isAi ? 'ai-move' : ''}>
                        <span className="move-player">{move.player}</span>
                        <span className="move-coords">({move.row + 1}, {move.col + 1})</span>
                        {move.isAi && <span className="ai-badge">AI</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {gameResult && (
                <div className={`game-result ${gameResult}`} role="alert">
                  {gameResult === 'win' && '🎉 Victory!'}
                  {gameResult === 'lose' && '🤖 AI Wins'}
                  {gameResult === 'draw' && '🤝 Draw'}
                </div>
              )}
            </div>
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
        <h2>Active Player Postgres Dashboard</h2>
        {playerStats ? (
          <div className="stats-container">
            <h3>Player Profile: <strong>{playerName}</strong></h3>
            <div className="difficulty-badge-container">
              <span className="difficulty-label">Highest Difficulty Reached:</span>
              <span className={`difficulty-badge ${(playerStats.highest_difficulty || 'Easy').toLowerCase()}`}>
                {playerStats.highest_difficulty || 'Easy'}
              </span>
            </div>
          </div>
        ) : (
          <p className="no-scores">Log in above to view historical Postgres stats tracking records.</p>
        )}
      </div>
    </div>
  );
}

export default App;