"""In-memory active chat registry — zero MongoDB reads on message relay.

Every relayed message used to hit get_user() (cache miss = DB round-trip).
Active sessions live here after match and are cleared on end/ban/restart.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActiveSession:
    partner_id: int
    session_id: str


@dataclass
class SessionRegistry:
    """Bidirectional map: user_id -> ActiveSession. O(1) lookup, minimal RAM."""

    _sessions: dict[int, ActiveSession] = field(default_factory=dict)

    def connect(self, user_a: int, user_b: int, session_id: str) -> None:
        sess_a = ActiveSession(partner_id=user_b, session_id=session_id)
        sess_b = ActiveSession(partner_id=user_a, session_id=session_id)
        self._sessions[user_a] = sess_a
        self._sessions[user_b] = sess_b

    def get(self, user_id: int) -> ActiveSession | None:
        return self._sessions.get(user_id)

    def disconnect(self, user_id: int) -> int | None:
        """Remove user and partner from registry. Returns partner_id if any."""
        session = self._sessions.pop(user_id, None)
        if not session:
            return None
        partner_id = session.partner_id
        self._sessions.pop(partner_id, None)
        return partner_id

    def disconnect_pair(self, user_a: int, user_b: int) -> None:
        self._sessions.pop(user_a, None)
        self._sessions.pop(user_b, None)

    def clear(self) -> None:
        self._sessions.clear()

    def size(self) -> int:
        return len(self._sessions)

    def snapshot_pairs(self) -> list[tuple[int, int, str]]:
        """For admin diagnostics — deduplicated (a,b) pairs."""
        seen: set[int] = set()
        pairs: list[tuple[int, int, str]] = []
        for uid, sess in self._sessions.items():
            if uid in seen:
                continue
            pid = sess.partner_id
            if pid in self._sessions and self._sessions[pid].partner_id == uid:
                pairs.append((uid, pid, sess.session_id))
                seen.add(uid)
                seen.add(pid)
        return pairs
