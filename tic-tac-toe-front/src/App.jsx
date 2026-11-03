import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { gsap } from 'gsap';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8000/ws';

const SOUNDS = {
  move: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  win: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  lose: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
  draw: 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAA=',
};

const COLUMNS = 'ABCDEF';
const DIFFICULTIES = ['Easy', 'Normal', 'Hard', 'Nightmare'];
const MODES = [
  { value: 'vs_system', label: 'Mimika', hint: 'The AI opponent' },
  { value: 'vs_player', label: 'Friend, this device', hint: 'Take turns on one screen' },
  { value: 'vs_player_ws', label: 'Friend, online', hint: 'Share a code to play' },
];

const cellName = (row, col) => `${COLUMNS[col]}${row + 1}`;

function playSound(name) {
  try {
    const audio = new Audio(SOUNDS[name]);
    audio.volume = 0.3;
    audio.play().catch(() => {});
  } catch { /* audio not supported */ }
}

function Mark({ value }) {
  if (value === 'X') {
    return (
      <svg className="mark" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 6 18 18M18 6 6 18" pathLength="1" />
      </svg>
    );
  }
  if (value === 'O') {
    return (
      <svg className="mark" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="6.5" pathLength="1" />
      </svg>
    );
  }
  return null;
}

function ScoreRow({ marker, name, detail, points, active }) {
  return (
    <div className={`score-row reveal${active ? ' is-active' : ''}`}>
      <span className="score-mark"><Mark value={marker} /></span>
      <span className="score-name">
        {name}
        {detail && <span className="score-detail">{detail}</span>}
      </span>
      <span className="pips" aria-label={`${points} of 3 points`}>
        {[0, 1, 2].map(i => <span key={i} className={`pip${i < points ? ' is-filled' : ''}`} />)}
      </span>
    </div>
  );
}

function App() {
  const [board, setBoard] = useState(Array(6).fill(Array(6).fill("")));
  const [currentPlayer, setCurrentPlayer] = useState("X");
  const [winnerCombo, setWinnerCombo] = useState([]);
  const [hasWinner, setHasWinner] = useState(false);
  const [isTied, setIsTied] = useState(false);
  const [scores, setScores] = useState({ X: 0, O: 0 });

  const [gameMode, setGameMode] = useState("vs_system");
  const [difficulty, setDifficulty] = useState("Normal");
  const [gameStarted, setGameStarted] = useState(false);
  const [playerName, setPlayerName] = useState("");
  const [playerStats, setPlayerStats] = useState(null);
  const [playerMarker, setPlayerMarker] = useState("X");
  const [playFirst, setPlayFirst] = useState(true);
  const [joinCode, setJoinCode] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);

  const [moveHistory, setMoveHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [focusedCell, setFocusedCell] = useState({ row: 0, col: 0 });
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [wsSessionId, setWsSessionId] = useState(null);
  const [opponentConnected, setOpponentConnected] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const boardRef = useRef(null);
  const mainRef = useRef(null);
  const seenBlocks = useRef(new WeakSet());
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
    if (!username) return;
    try {
      const response = await fetch(`${API_BASE_URL}/player/${encodeURIComponent(username)}`);
      const data = await response.json();
      setPlayerStats(response.ok && !data.error && !data.message ? data : null);
    } catch (err) {
      console.error("Failed to fetch player record:", err);
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
        setNotice("");
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
        playSound(!payload.winner ? 'draw' : payload.winner === playerMarker ? 'win' : 'lose');
        break;

      case 'opponent_disconnected':
        setOpponentConnected(false);
        setNotice("Your friend left the game. They can rejoin with the same code.");
        break;

      case 'error':
        setNotice(typeof payload === 'string' ? payload : 'Something went wrong with the online game.');
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

  const resetRound = () => {
    setMoveHistory([]);
    setFocusedCell({ row: 0, col: 0 });
    setNotice("");
  };

  const startGame = useCallback(async (event) => {
    event.preventDefault();
    const cleanName = playerName.trim();
    if (!cleanName) {
      setNotice("Enter your name to start.");
      return;
    }

    if (gameMode === "vs_player_ws") {
      const code = joinCode.trim();
      try {
        let session = code;
        if (!session) {
          const response = await fetch(`${API_BASE_URL}/ws/create`);
          session = (await response.json()).session_id;
        }
        setWsSessionId(session);
        setOpponentConnected(false);
        setConnectionStatus('connecting');
        // Creator asks for X; a joiner takes whichever seat is free.
        connectWebSocket(session, code ? null : 'X');
        if (!code) setPlayerMarker('X');
      } catch (err) {
        console.error("WS session creation failed:", err);
        setNotice("Couldn't create an online game. Check that the server is running.");
        return;
      }
    } else {
      const chosenMarker = gameMode === "vs_system" && !playFirst ? "O" : "X";
      try {
        const response = await fetch(`${API_BASE_URL}/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: gameMode, difficulty: difficulty, starting_player: chosenMarker })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || response.statusText);
        syncGameState(data);
        setSessionId(data.session_id);
        setPlayerMarker(chosenMarker);
      } catch (err) {
        console.error("Game start failed:", err);
        setNotice("Couldn't start the game. Check that the server is running.");
        return;
      }
    }

    setPlayerName(cleanName);
    resetRound();
    setGameStarted(true);
    void fetchPlayerProfile(cleanName);
  }, [playerName, gameMode, joinCode, playFirst, difficulty, syncGameState, fetchPlayerProfile, connectWebSocket]);

  const handlePlayAgain = useCallback(async () => {
    if (gameMode === 'vs_player_ws') {
      try {
        const response = await fetch(`${API_BASE_URL}/ws/create`);
        const data = await response.json();
        setWsSessionId(data.session_id);
        setPlayerMarker('X');
        setOpponentConnected(false);
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
        console.error("Restart failed:", err);
      }
    }
    resetRound();
    setHasWinner(false);
    setIsTied(false);
  }, [gameMode, difficulty, playerMarker, syncGameState, connectWebSocket]);

  const leaveGame = () => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    clearTimeout(reconnectTimeoutRef.current);
    setGameStarted(false);
    setNotice("");
  };

  const recordMoveInHistory = useCallback((row, col, player, isAi = false) => {
    setMoveHistory(prev => [...prev, { row, col, player, isAi, timestamp: Date.now() }]);
  }, []);

  const processEndgame = useCallback(async (finalData, activePlayerName) => {
    if (gameMode !== "vs_system") return;
    const result = !finalData.has_winner ? "draw" : finalData.current_player === playerMarker ? "win" : "loss";
    try {
      const response = await fetch(`${API_BASE_URL}/record-match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: activePlayerName, difficulty: difficulty, result: result })
      });
      const updatedStats = await response.json();
      if (!response.ok) throw new Error(updatedStats.detail || response.statusText);
      setPlayerStats(updatedStats);
    } catch (err) {
      console.error("Saving the result failed:", err);
      setNotice("This result wasn't saved to your record. Check that the database is running.");
    }
  }, [gameMode, playerMarker, difficulty]);

  const isMyTurnOnline = gameMode !== 'vs_player_ws' || (opponentConnected && currentPlayer === playerMarker);

  const handleCellClick = useCallback(async (row, col) => {
    if (hasWinner || isTied || board[row][col] !== "") return;

    if (gameMode === 'vs_player_ws') {
      if (isMyTurnOnline && wsRef.current?.readyState === WebSocket.OPEN) {
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
      console.error("Move failed:", err);
      setNotice("That move didn't go through. The game may have expired; start a new one.");
    }
  }, [hasWinner, isTied, gameMode, isMyTurnOnline, sessionId, board, currentPlayer, playerName, recordMoveInHistory, syncGameState, processEndgame]);

  const handleKeyDown = useCallback((e) => {
    if (!gameStarted) return;

    if ((e.key === 'h' || e.key === 'H') && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      setShowHistory(prev => !prev);
      return;
    }

    const steps = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (!steps[e.key]) return;
    // Arrows steer the board only when nothing else (like a button) has focus.
    const inBoard = boardRef.current?.contains(document.activeElement);
    if (!inBoard && document.activeElement !== document.body) return;

    e.preventDefault();
    const [dr, dc] = steps[e.key];
    const row = Math.min(5, Math.max(0, focusedCell.row + dr));
    const col = Math.min(5, Math.max(0, focusedCell.col + dc));
    setFocusedCell({ row, col });
    boardRef.current?.querySelector(`[data-cell="${row}-${col}"]`)?.focus();
  }, [gameStarted, focusedCell]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => () => {
    clearTimeout(reconnectTimeoutRef.current);
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }
  }, []);

  // Every block fades in from above the first time it appears, in top-to-bottom order.
  useLayoutEffect(() => {
    const fresh = [...mainRef.current.querySelectorAll('.reveal')].filter(el => !seenBlocks.current.has(el));
    if (!fresh.length) return;
    fresh.forEach(el => seenBlocks.current.add(el));
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    fresh.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    gsap.from(fresh, { opacity: 0, y: -16, duration: 0.5, ease: 'power2.out', stagger: 0.05, clearProps: 'opacity,transform' });
  });

  const copyCode = () => {
    navigator.clipboard?.writeText(wsSessionId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };

  const isScored = (r, c) => winnerCombo.some(([sr, sc]) => sr === r && sc === c);
  const lastMove = moveHistory[moveHistory.length - 1];
  const opponentMarker = playerMarker === 'X' ? 'O' : 'X';
  const gameOver = hasWinner || isTied;
  const nightmareUnlocked = ["Hard", "Nightmare"].includes(playerStats?.highest_difficulty);
  const opponentName = gameMode === 'vs_system' ? 'Mimika' : 'Friend';

  const statusText = (() => {
    if (hasWinner) {
      if (gameMode === 'vs_player') return `${currentPlayer} wins`;
      return currentPlayer === playerMarker ? 'You win' : `${opponentName} wins`;
    }
    if (isTied) return 'Draw. The board is full.';
    if (gameMode === 'vs_player_ws') {
      if (connectionStatus === 'error' || connectionStatus === 'disconnected') return 'Reconnecting';
      if (!opponentConnected) return 'Waiting for your friend';
    }
    if (gameMode === 'vs_player') return `${currentPlayer} to move`;
    return currentPlayer === playerMarker ? 'Your move' : `${opponentName} to move`;
  })();

  const scoreRows = gameMode === 'vs_player'
    ? [
        { marker: 'X', name: 'X', detail: 'Moves first' },
        { marker: 'O', name: 'O', detail: null },
      ]
    : [
        { marker: playerMarker, name: playerName || 'You', detail: 'You' },
        { marker: opponentMarker, name: opponentName, detail: gameMode === 'vs_system' ? difficulty : null },
      ];

  if (!gameStarted) {
    return (
      <main className="app setup" ref={mainRef}>
        <header className="intro reveal">
          <h1 className="wordmark">HexTacTic</h1>
        </header>

        <div className="setup-grid">
          <div className="setup-aside">
            <p className="rules reveal">A 6 by 6 board. Every three in a row scores a point. First to 3 points wins.</p>
            {playerStats && (
              <section className="record reveal" aria-labelledby="record-title">
                <h2 id="record-title">{playerName.trim()}'s record against Mimika</h2>
                <table>
                  <thead>
                    <tr><th scope="col">Level</th><th scope="col">Wins</th><th scope="col">Losses</th><th scope="col">Draws</th></tr>
                  </thead>
                  <tbody>
                    {DIFFICULTIES.map(level => {
                      const key = level.toLowerCase();
                      return (
                        <tr key={level}>
                          <th scope="row">{level}</th>
                          <td>{playerStats[`${key}_wins`] ?? 0}</td>
                          <td>{playerStats[`${key}_losses`] ?? 0}</td>
                          <td>{playerStats[`${key}_draws`] ?? 0}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="field-hint">Highest level reached: {playerStats.highest_difficulty || 'Easy'}</p>
              </section>
            )}
          </div>
          <form className="setup-form" onSubmit={startGame} noValidate>
            <label className="field reveal">
              <span className="field-label">Your name</span>
              <input
                type="text"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                onBlur={() => fetchPlayerProfile(playerName.trim())}
                autoComplete="nickname"
                maxLength={64}
                placeholder="e.g. Sam"
              />
            </label>

            <fieldset className="field">
              <legend className="field-label reveal">Opponent</legend>
              <div className="choice-list">
                {MODES.map(mode => (
                  <label key={mode.value} className="choice reveal">
                    <input
                      type="radio"
                      name="mode"
                      value={mode.value}
                      checked={gameMode === mode.value}
                      onChange={() => setGameMode(mode.value)}
                    />
                    <span className="choice-body">
                      <span className="choice-label">{mode.label}</span>
                      <span className="choice-hint">{mode.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {gameMode === 'vs_system' && (
              <>
                <fieldset className="field">
                  <legend className="field-label reveal">Mimika's level</legend>
                  <div className="segmented reveal">
                    {DIFFICULTIES.map(level => {
                      const locked = level === 'Nightmare' && !nightmareUnlocked;
                      return (
                        <label key={level} className={`segment${locked ? ' is-locked' : ''}`} title={locked ? 'Win a game on Hard to unlock' : undefined}>
                          <input
                            type="radio"
                            name="difficulty"
                            value={level}
                            checked={difficulty === level}
                            disabled={locked}
                            onChange={() => setDifficulty(level)}
                          />
                          <span>{level}</span>
                        </label>
                      );
                    })}
                  </div>
                  {!nightmareUnlocked && <p className="field-hint reveal">Win a game on Hard to unlock Nightmare.</p>}
                </fieldset>

                <label className="toggle reveal">
                  <input type="checkbox" checked={playFirst} onChange={(e) => setPlayFirst(e.target.checked)} />
                  <span>I'll move first as X</span>
                </label>
              </>
            )}

            {gameMode === 'vs_player_ws' && (
              <label className="field reveal">
                <span className="field-label">Game code</span>
                <input
                  type="text"
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value)}
                  autoComplete="off"
                  spellCheck="false"
                  placeholder="Leave empty to start a new game"
                />
              </label>
            )}

            {notice && <p className="notice reveal" role="alert">{notice}</p>}

            <button type="submit" className="button primary reveal">
              {gameMode === 'vs_player_ws' && joinCode.trim() ? 'Join game' : 'Start game'}
            </button>
          </form>
        </div>

      </main>
    );
  }

  return (
    <main className="app game" ref={mainRef}>
      <header className="game-header reveal">
        <span className="wordmark small">HexTacTic</span>
        <button className="button ghost" onClick={leaveGame}>Main menu</button>
      </header>

      <div className="game-layout">
        <div className="board-wrap">
          <div className="coords coords-cols reveal" aria-hidden="true">
            {COLUMNS.split('').map(c => <span key={c}>{c}</span>)}
          </div>
          <div className="coords coords-rows reveal" aria-hidden="true">
            {[1, 2, 3, 4, 5, 6].map(r => <span key={r}>{r}</span>)}
          </div>
          <div className="board" role="grid" aria-label="Game board" ref={boardRef}>
            {board.map((row, rowIndex) => (
              <div key={rowIndex} className="board-row reveal" role="row">
                {row.map((cellValue, colIndex) => {
                  const isCursor = focusedCell.row === rowIndex && focusedCell.col === colIndex;
                  const unavailable = gameOver || cellValue !== "" || !isMyTurnOnline;
                  const isLast = lastMove && lastMove.row === rowIndex && lastMove.col === colIndex;
                  return (
                    <button
                      key={colIndex}
                      type="button"
                      role="gridcell"
                      data-cell={`${rowIndex}-${colIndex}`}
                      className={`cell${isScored(rowIndex, colIndex) ? ' is-scored' : ''}${isLast ? ' is-last' : ''}`}
                      onClick={() => handleCellClick(rowIndex, colIndex)}
                      onFocus={() => setFocusedCell({ row: rowIndex, col: colIndex })}
                      aria-disabled={unavailable}
                      aria-label={cellValue ? `${cellName(rowIndex, colIndex)}, ${cellValue}` : `${cellName(rowIndex, colIndex)}, empty`}
                      tabIndex={isCursor ? 0 : -1}
                    >
                      <Mark value={cellValue} />
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <aside className="panel">
          <p className="status reveal" role="status" aria-live="polite">{statusText}</p>

          <div className="scores">
            {scoreRows.map(row => (
              <ScoreRow
                key={row.marker}
                {...row}
                points={Math.min(3, scores[row.marker] ?? 0)}
                active={!isTied && currentPlayer === row.marker}
              />
            ))}
          </div>

          {gameMode === 'vs_player_ws' && wsSessionId && !opponentConnected && !gameOver && (
            <div className="share reveal">
              <p className="field-hint">Send this code to your friend. They choose Friend, online and enter it.</p>
              <div className="share-row">
                <code className="share-code">{wsSessionId}</code>
                <button className="button ghost" onClick={copyCode}>{copied ? 'Copied' : 'Copy code'}</button>
              </div>
            </div>
          )}

          {notice && <p className="notice reveal" role="alert">{notice}</p>}

          {gameOver && (
            <button className="button primary reveal" onClick={handlePlayAgain}>Play again</button>
          )}

          <div className="moves reveal">
            <button className="button text" onClick={() => setShowHistory(prev => !prev)} aria-expanded={showHistory}>
              {showHistory ? 'Hide moves' : 'Show moves'}
            </button>
            {showHistory && (
              moveHistory.length > 0 ? (
                <ol className="move-list" aria-label="Moves">
                  {moveHistory.map((move, idx) => (
                    <li key={idx}>
                      <span className="move-mark"><Mark value={move.player} /></span>
                      <span>{cellName(move.row, move.col)}</span>
                      {move.isAi && <span className="move-by">Mimika</span>}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="field-hint">No moves yet. Pick any square to start.</p>
              )
            )}
          </div>

          <p className="keys reveal">Arrow keys move between squares, Enter places a mark, Ctrl+H shows moves.</p>
        </aside>
      </div>
    </main>
  );
}

export default App;
