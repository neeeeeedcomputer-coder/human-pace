"""Where gap history lives.

Two backends with the same tiny interface:

* :class:`MemoryStore` - a dict of deques, no files, good for tests and for
  bots that restart often anyway.
* :class:`SqliteStore` - survives restarts. Useful because typing pace is a
  property of the *person*, not of the process: after a deploy you should not
  have to re-learn that this user types slowly.

Both keep at most ``keep`` samples per key and return newest-first, because
every consumer here cares about recent behaviour.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def add(self, key: str, gap: float, ts: float) -> None: ...
    def recent(self, key: str, n: int = 50) -> list[float]: ...
    def clear(self, key: str | None = None) -> None: ...


class MemoryStore:
    """In-process storage. Nothing is written to disk."""

    def __init__(self, keep: int = 200) -> None:
        self.keep = keep
        self._data: dict[str, deque[float]] = {}

    def add(self, key: str, gap: float, ts: float) -> None:
        dq = self._data.get(key)
        if dq is None:
            dq = deque(maxlen=self.keep)
            self._data[key] = dq
        dq.append(float(gap))

    def recent(self, key: str, n: int = 50) -> list[float]:
        dq = self._data.get(key)
        if not dq:
            return []
        items = list(dq)
        items.reverse()
        return items[:n]

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)


class SqliteStore:
    """Persistent storage. One row per gap."""

    def __init__(self, path: str | os.PathLike, keep: int = 200) -> None:
        self.path = Path(path)
        self.keep = keep
        self._conn: sqlite3.Connection | None = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gaps (
                    id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    gap REAL NOT NULL,
                    ts  INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gaps_key ON gaps(key, id DESC);
                """
            )
            self._conn.commit()
        return self._conn

    def add(self, key: str, gap: float, ts: float) -> None:
        db = self._db()
        db.execute(
            "INSERT INTO gaps(key, gap, ts) VALUES (?,?,?)",
            (key, float(gap), int(ts)),
        )
        # Trim old rows so the table cannot grow without bound.
        db.execute(
            "DELETE FROM gaps WHERE key=? AND id NOT IN "
            "(SELECT id FROM gaps WHERE key=? ORDER BY id DESC LIMIT ?)",
            (key, key, self.keep),
        )
        db.commit()

    def recent(self, key: str, n: int = 50) -> list[float]:
        rows = self._db().execute(
            "SELECT gap FROM gaps WHERE key=? ORDER BY id DESC LIMIT ?", (key, n)
        ).fetchall()
        return [float(r[0]) for r in rows]

    def clear(self, key: str | None = None) -> None:
        db = self._db()
        if key is None:
            db.execute("DELETE FROM gaps")
        else:
            db.execute("DELETE FROM gaps WHERE key=?", (key,))
        db.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class ObservedStore(MemoryStore):
    """MemoryStore that also remembers the wall-clock time of each sample.

    The main algorithms only need the gap values, but demos and debugging
    often want the timeline. Kept separate to avoid bloating the hot path.
    """

    def __init__(self, keep: int = 200) -> None:
        super().__init__(keep)
        self._times: dict[str, deque[float]] = {}

    def add(self, key: str, gap: float, ts: float) -> None:
        super().add(key, gap, ts)
        dq = self._times.get(key)
        if dq is None:
            dq = deque(maxlen=self.keep)
            self._times[key] = dq
        dq.append(float(ts))

    def timeline(self, key: str, n: int = 20) -> list[tuple[float, float]]:
        gaps = self.recent(key, n)
        times = list(self._times.get(key, []))[::-1][:n]
        return list(zip(times, gaps))
