"""Every dictation, saved on this PC in history.db so the app window can list, search, and copy them.

The tray app adds to it and the window reads it, each opening the file only for the length of one call.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from ghostwriter.paths import HISTORY_PATH

PAGE_SIZE = 200  # dictations the History page shows before "Show more"
RECENT_COUNT = 3  # dictations on Home
FILTER_APPS = 4  # the most used apps get their own filter on the History page

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dictations (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,  -- local time, like 2026-10-28T17:15:47
    text TEXT NOT NULL,
    app TEXT NOT NULL,
    seconds REAL NOT NULL,
    words INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS dictations_by_time ON dictations (at);
"""
_COLUMNS = "id, at, text, app, seconds, words"


class History:
    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self.path = path

    def add(self, text: str, app: str, seconds: float, at: datetime | None = None) -> None:
        moment = (at or datetime.now()).isoformat(timespec="seconds")
        with self._open() as db:
            db.execute("INSERT INTO dictations (at, text, app, seconds, words) VALUES (?, ?, ?, ?, ?)",
                       (moment, text, app, round(seconds, 1), len(text.split())))

    def search(self, query: str = "", app: str | None = None, limit: int = PAGE_SIZE) -> dict:
        """The newest dictations that contain the query and came from the app, plus how many match in all."""
        conditions, values = [], []
        if query.strip():
            conditions.append("text LIKE ? ESCAPE '\\'")
            values.append(f"%{_escape_like(query.strip())}%")
        if app:
            conditions.append("app = ?")
            values.append(app)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._open() as db:
            total = db.execute(f"SELECT count(*) FROM dictations {where}", values).fetchone()[0]
            rows = db.execute(f"SELECT {_COLUMNS} FROM dictations {where} ORDER BY id DESC LIMIT ?",
                              [*values, int(limit)]).fetchall()
        return {"items": [dict(row) for row in rows], "total": total}

    def apps(self, limit: int = FILTER_APPS) -> list[str]:
        """The apps dictated into most, most used first."""
        with self._open() as db:
            rows = db.execute("SELECT app FROM dictations GROUP BY app ORDER BY count(*) DESC, max(id) DESC LIMIT ?",
                              [limit]).fetchall()
        return [row["app"] for row in rows]

    def summary(self, today: date | None = None) -> dict:
        """Counts for today and this month, and the latest few dictations, for Home."""
        today = today or date.today()
        with self._open() as db:
            words_today, dictations_today = db.execute(
                "SELECT coalesce(sum(words), 0), count(*) FROM dictations WHERE at >= ?", [today.isoformat()]).fetchone()
            words_month = db.execute("SELECT coalesce(sum(words), 0) FROM dictations WHERE at >= ?",
                                     [today.replace(day=1).isoformat()]).fetchone()[0]
            total = db.execute("SELECT count(*) FROM dictations").fetchone()[0]
            recent = db.execute(f"SELECT {_COLUMNS} FROM dictations ORDER BY id DESC LIMIT ?", [RECENT_COUNT]).fetchall()
        return {"words_today": words_today, "dictations_today": dictations_today, "words_month": words_month,
                "total": total, "recent": [dict(row) for row in recent]}

    def stamp(self) -> str:
        """Changes whenever a dictation is added or the history is cleared, so the window knows to refresh."""
        with self._open() as db:
            count, newest = db.execute("SELECT count(*), coalesce(max(id), 0) FROM dictations").fetchone()
        return f"{count}-{newest}"

    def clear(self) -> None:
        """Delete every dictation, then compact the file so the deleted text doesn't linger in it."""
        with self._open() as db:
            db.execute("DELETE FROM dictations")
            db.commit()
            db.execute("VACUUM")

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.executescript(_SCHEMA)
            with db:  # commits at the end, or undoes everything on an error
                yield db
        finally:
            db.close()


def _escape_like(text: str) -> str:
    """Make % and _ in a search match themselves instead of acting as wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
