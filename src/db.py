"""One SQLite file for everything that changes at run time."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vaults(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
  private_folders TEXT NOT NULL DEFAULT '[]', position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS bases(
  vault_id TEXT NOT NULL, peer_id TEXT NOT NULL, path TEXT NOT NULL, sha TEXT NOT NULL,
  PRIMARY KEY(vault_id, peer_id, path));
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL);
"""


class Db:
    """Thread-safe SQLite wrapper. Calls are short; use through asyncio.to_thread when batching."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.executescript(_SCHEMA)

    def run(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._c.execute(sql, params).fetchall()

    def run_many(self, sql: str, rows: Iterable[tuple]) -> None:
        with self._lock:
            self._c.execute("BEGIN")
            try:
                self._c.executemany(sql, list(rows))
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._c.close()
