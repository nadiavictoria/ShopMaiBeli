"""
SessionStore — global, thread-safe store for per-user ExecutionContext objects.

Ensures that:
- Session state (memory, chat history) persists across requests for the same user.
- Concurrent requests from different users are fully isolated.
- Concurrent requests from the *same* user are serialized via a per-session lock,
  preventing race conditions on shared context state.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from .context import ExecutionContext


@dataclass
class SessionEntry:
    context: ExecutionContext
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


class SessionStore:
    """
    Global store mapping session_id -> (ExecutionContext, asyncio.Lock).

    Usage:
        store = SessionStore()

        # Acquire a session-scoped lock before executing a workflow
        async with store.session_lock(session_id):
            ctx = store.get_or_create(session_id)
            ...

        # Inspect active sessions
        store.active_sessions()

        # Clean up stale sessions
        store.evict_stale(max_age_seconds=3600)
    """

    def __init__(self):
        self._sessions: Dict[str, SessionEntry] = {}
        self._store_lock = asyncio.Lock()  # guards mutations to _sessions dict

    async def get_or_create(self, session_id: str) -> ExecutionContext:
        """Return the existing context for session_id, or create a fresh one."""
        async with self._store_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionEntry(
                    context=ExecutionContext(session_id=session_id)
                )
            entry = self._sessions[session_id]
            entry.last_used = time.time()
            return entry.context

    def session_lock(self, session_id: str) -> asyncio.Lock:
        """
        Return the asyncio.Lock for the given session.

        Callers should use this as an async context manager:
            async with store.session_lock(session_id):
                ...

        Note: get_or_create must be called (possibly concurrently) before this,
        or call ensure_exists() to create the entry synchronously.
        """
        # Create entry synchronously if missing (safe outside of concurrent mutations)
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionEntry(
                context=ExecutionContext(session_id=session_id)
            )
        return self._sessions[session_id].lock

    def get(self, session_id: str) -> Optional[ExecutionContext]:
        """Return context if it exists, else None."""
        entry = self._sessions.get(session_id)
        return entry.context if entry else None

    def delete(self, session_id: str):
        """Remove a session from the store."""
        self._sessions.pop(session_id, None)

    def active_sessions(self) -> Dict[str, dict]:
        """Return a summary of all active sessions (for the /sessions endpoint)."""
        now = time.time()
        return {
            sid: {
                "session_id": sid,
                "created_at": entry.created_at,
                "last_used": entry.last_used,
                "idle_seconds": round(now - entry.last_used, 1),
                "memory_keys": list(entry.context.memory.keys()),
            }
            for sid, entry in self._sessions.items()
        }

    def evict_stale(self, max_age_seconds: float = 3600):
        """Remove sessions that have been idle longer than max_age_seconds."""
        now = time.time()
        stale = [
            sid for sid, entry in self._sessions.items()
            if now - entry.last_used > max_age_seconds
        ]
        for sid in stale:
            del self._sessions[sid]
        return stale


# Module-level singleton — shared across all requests in the same process
session_store = SessionStore()
