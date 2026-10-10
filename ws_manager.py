"""WebSocket connection manager for real-time multiplayer games."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from script import TicTacToeGame
from settings import SESSION_TTL_SECONDS


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WSGameSession:
    game: TicTacToeGame
    player_x: Optional[WebSocket] = None
    player_o: Optional[WebSocket] = None
    spectators: Set[WebSocket] = field(default_factory=set)
    created_at: datetime = field(default_factory=_now)
    last_activity: datetime = field(default_factory=_now)

    def get_player_ws(self, marker: str) -> Optional[WebSocket]:
        return self.player_x if marker == "X" else self.player_o

    def set_player_ws(self, marker: str, ws: WebSocket) -> None:
        if marker == "X":
            self.player_x = ws
        else:
            self.player_o = ws

    def get_opponent_ws(self, marker: str) -> Optional[WebSocket]:
        return self.player_o if marker == "X" else self.player_x

    def all_players_connected(self) -> bool:
        return self.player_x is not None and self.player_o is not None

    def get_all_connections(self) -> List[WebSocket]:
        conns = []
        if self.player_x:
            conns.append(self.player_x)
        if self.player_o:
            conns.append(self.player_o)
        conns.extend(self.spectators)
        return conns


class WSConnectionManager:
    def __init__(self):
        self.sessions: Dict[str, WSGameSession] = {}
        self.ws_to_session: Dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    def _purge_expired(self) -> None:
        cutoff = _now() - timedelta(seconds=SESSION_TTL_SECONDS)
        for session_id in [sid for sid, s in self.sessions.items() if s.last_activity < cutoff]:
            session = self.sessions.pop(session_id)
            for conn in session.get_all_connections():
                self.ws_to_session.pop(conn, None)

    async def create_session(self) -> str:
        async with self._lock:
            self._purge_expired()
            session_id = str(uuid.uuid4())[:8]
            game = TicTacToeGame()
            game.game_mode = "vs_player_ws"
            self.sessions[session_id] = WSGameSession(game=game)
            return session_id

    async def join_session(self, session_id: str, ws: WebSocket, preferred_marker: Optional[str] = None) -> str:
        async with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise ValueError("Session not found")

            if preferred_marker and session.get_player_ws(preferred_marker) is None:
                marker = preferred_marker
            elif session.player_x is None:
                marker = "X"
            elif session.player_o is None:
                marker = "O"
            else:
                session.spectators.add(ws)
                self.ws_to_session[ws] = session_id
                return "spectator"

            session.set_player_ws(marker, ws)
            self.ws_to_session[ws] = session_id
            session.last_activity = _now()
            return marker

    async def leave_session(self, ws: WebSocket) -> None:
        async with self._lock:
            session_id = self.ws_to_session.pop(ws, None)
            if not session_id:
                return

            session = self.sessions.get(session_id)
            if not session:
                return

            if session.player_x == ws:
                session.player_x = None
            elif session.player_o == ws:
                session.player_o = None
            else:
                session.spectators.discard(ws)

            if not session.player_x and not session.player_o and not session.spectators:
                self.sessions.pop(session_id, None)

    async def handle_move(self, ws: WebSocket, row: int, col: int) -> Optional[dict]:
        async with self._lock:
            session_id = self.ws_to_session.get(ws)
            if not session_id:
                return {"error": "Not in a session"}

            session = self.sessions.get(session_id)
            if not session:
                return {"error": "Session not found"}

            marker = "X" if session.player_x == ws else "O" if session.player_o == ws else None
            if not marker:
                return {"error": "Spectators cannot make moves"}

            game = session.game
            if game._has_winner or game.is_tied():
                return {"error": "Game already ended"}

            if game.current_player != marker:
                return {"error": "Not your turn"}

            if not game.is_valid_move(row, col):
                return {"error": "Invalid move"}

            game.process_move(row, col)
            state = game.get_state()
            state["session_id"] = session_id
            state["your_marker"] = marker

            session.last_activity = _now()
            return state

    async def broadcast_state(self, session_id: str, state: dict) -> None:
        await self.broadcast(session_id, {"type": "state", "payload": state})

    async def broadcast(self, session_id: str, message: dict) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return

        message = json.dumps(message)
        disconnected = []

        for conn in session.get_all_connections():
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            await self.leave_session(conn)

    async def send_to_player(self, session_id: str, marker: str, message: dict) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        ws = session.get_player_ws(marker)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                await self.leave_session(ws)

    async def notify_opponent(self, session_id: str, marker: str, message: dict) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        ws = session.get_opponent_ws(marker)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                await self.leave_session(ws)


ws_manager = WSConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = None
    player_marker = None

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "create":
                session_id = await ws_manager.create_session()
                player_marker = await ws_manager.join_session(session_id, websocket, "X")
                await websocket.send_text(json.dumps({
                    "type": "created",
                    "payload": {"session_id": session_id, "marker": player_marker}
                }))

            elif msg_type == "join":
                session_id = message.get("session_id")
                preferred = message.get("marker")
                if not session_id:
                    await websocket.send_text(json.dumps({"type": "error", "payload": "session_id required"}))
                    continue
                try:
                    player_marker = await ws_manager.join_session(session_id, websocket, preferred)
                    session = ws_manager.sessions.get(session_id)
                    state = session.game.get_state()
                    state["session_id"] = session_id
                    state["your_marker"] = player_marker
                    await websocket.send_text(json.dumps({
                        "type": "joined",
                        "payload": state
                    }))
                    if session.all_players_connected():
                        await ws_manager.broadcast(session_id, {
                            "type": "ready",
                            "payload": {"message": "Both players connected. Game starting!"}
                        })
                except ValueError as e:
                    await websocket.send_text(json.dumps({"type": "error", "payload": str(e)}))

            elif msg_type == "move":
                if not session_id:
                    await websocket.send_text(json.dumps({"type": "error", "payload": "Not in a session"}))
                    continue
                row = message.get("row")
                col = message.get("col")
                if row is None or col is None:
                    await websocket.send_text(json.dumps({"type": "error", "payload": "row and col required"}))
                    continue

                result = await ws_manager.handle_move(websocket, row, col)
                if "error" in result:
                    await websocket.send_text(json.dumps({"type": "error", "payload": result["error"]}))
                else:
                    await ws_manager.broadcast_state(session_id, result)
                    if result.get("has_winner") or result.get("is_tied"):
                        await asyncio.sleep(0.1)
                        final_msg = {
                            "type": "game_over",
                            "payload": {
                                "winner": result.get("current_player") if result.get("has_winner") else None,
                                "is_tied": result.get("is_tied"),
                                "scores": result.get("scores"),
                                "winner_combo": result.get("winner_combo")
                            }
                        }
                        await ws_manager.broadcast(session_id, final_msg)

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "payload": str(e)}))
        except Exception:
            pass
    finally:
        if session_id and player_marker and player_marker != "spectator":
            await ws_manager.notify_opponent(session_id, player_marker, {
                "type": "opponent_disconnected",
                "payload": {"message": "Opponent disconnected"}
            })
        await ws_manager.leave_session(websocket)