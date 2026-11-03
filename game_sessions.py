"""Concurrency-safe in-memory game session storage."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from script import TicTacToeGame
from settings import SESSION_TTL_SECONDS


@dataclass
class GameSession:
    game: TicTacToeGame
    human_marker: str = "X"
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_accessed = time.time()


class GameSessionManager:
    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS):
        self._sessions: dict[str, GameSession] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds

    def _purge_expired(self) -> None:
        cutoff = time.time() - self._ttl_seconds
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.last_accessed < cutoff
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def create_session(
        self,
        mode: str,
        difficulty: str,
        starting_player: str = "X",
    ) -> tuple[str, dict[str, Any]]:
        with self._lock:
            self._purge_expired()
            session_id = str(uuid.uuid4())
            game = TicTacToeGame()
            game.game_mode = mode
            game.difficulty = difficulty
            session = GameSession(game=game, human_marker=starting_player)
            self._sessions[session_id] = session
            state = self._serialize(session_id, session)
            return session_id, state

    def get_session(self, session_id: str) -> GameSession:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            session.touch()
            return session

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _serialize(self, session_id: str, session: GameSession) -> dict[str, Any]:
        payload = session.game.get_state()
        payload["session_id"] = session_id
        payload["human_marker"] = session.human_marker
        payload["game_mode"] = session.game.game_mode
        return payload

    def get_state(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        return self._serialize(session_id, session)
