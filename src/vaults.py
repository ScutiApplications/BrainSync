"""Registry of known vaults (db table). Never modifies a vault except the one 'create' exception."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from src.db import Db
from src.errors import BrainSyncError


class VaultError(BrainSyncError):
    pass


def _row(r, active_id: str | None) -> dict:
    return {"id": r["id"], "name": r["name"], "path": r["path"],
            "private_folders": json.loads(r["private_folders"]), "active": r["id"] == active_id}


class VaultRegistry:
    def __init__(self, db: Db):
        self._db = db

    def _active_id(self) -> str | None:
        rows = self._db.run("SELECT value FROM meta WHERE key = 'active_vault'")
        return rows[0]["value"] if rows else None

    def list(self) -> list[dict]:
        a = self._active_id()
        return [_row(r, a) for r in self._db.run("SELECT * FROM vaults ORDER BY position")]

    def get(self, vault_id: str) -> dict:
        rows = self._db.run("SELECT * FROM vaults WHERE id = ?", (vault_id,))
        if not rows:
            raise VaultError("unknown vault")
        return _row(rows[0], self._active_id())

    def add(self, name: str, path: str, create: bool = False) -> dict:
        name = (name or "").strip()
        if not name:
            raise VaultError("name is required")
        p = Path(path).expanduser().resolve()
        if create:
            if p.exists() and (not p.is_dir() or any(p.iterdir())):
                raise VaultError("folder is not empty")
            p.mkdir(parents=True, exist_ok=True)
            (p / ".obsidian").mkdir(exist_ok=True)
        elif not ((p / ".obsidian").is_dir() and (p / "AGENTS.md").is_file()):
            raise VaultError("folder is not a Brain vault")
        if self._db.run("SELECT 1 FROM vaults WHERE path = ?", (str(p),)):
            raise VaultError("vault already registered")
        vid = uuid4().hex
        pos = self._db.run("SELECT COALESCE(MAX(position), 0) + 1 AS n FROM vaults")[0]["n"]
        self._db.run("INSERT INTO vaults(id, name, path, private_folders, position) VALUES (?, ?, ?, '[]', ?)",
                     (vid, name, str(p), pos))
        if self._active_id() is None:
            self.set_active(vid)
        return self.get(vid)

    def remove(self, vault_id: str) -> None:
        self._db.run("DELETE FROM vaults WHERE id = ?", (vault_id,))
        self._db.run("DELETE FROM bases WHERE vault_id = ?", (vault_id,))
        if self._active_id() == vault_id:
            self._db.run("DELETE FROM meta WHERE key = 'active_vault'")
            first = self.list()
            if first:
                self.set_active(first[0]["id"])

    def set_private_folders(self, vault_id: str, folders: list[str]) -> None:
        self.get(vault_id)
        clean = [f.strip().strip("/") for f in folders if f.strip().strip("/")]
        self._db.run("UPDATE vaults SET private_folders = ? WHERE id = ?", (json.dumps(clean), vault_id))

    def set_active(self, vault_id: str) -> None:
        self.get(vault_id)
        self._db.run("INSERT OR REPLACE INTO meta(key, value) VALUES ('active_vault', ?)", (vault_id,))

    def active(self) -> dict | None:
        a = self._active_id()
        return self.get(a) if a else None
