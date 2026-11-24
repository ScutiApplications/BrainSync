"""Service state: device id, sync bases and audit log in the db; content blobs and backups as files."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from src.db import Db
from src.fsutil import write_atomic

_ID = re.compile(r"[0-9a-f]{32}")


def _check_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("bad id")
    return value


class State:
    def __init__(self, root: Path, db: Db | None = None):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.db = db or Db(root / "brainsync.db")

    def device_id(self) -> str:
        rows = self.db.run("SELECT value FROM meta WHERE key = 'device_id'")
        if rows:
            return rows[0]["value"]
        did = uuid4().hex
        self.db.run("INSERT INTO meta(key, value) VALUES ('device_id', ?)", (did,))
        return did

    def put_blob(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        p = self.root / "blobs" / sha
        if not p.exists():
            write_atomic(p, data)
        return sha

    def get_blob(self, sha: str) -> bytes | None:
        if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
            return None
        p = self.root / "blobs" / sha
        return p.read_bytes() if p.is_file() else None

    def load_base(self, vault_id: str, peer_id: str) -> dict[str, str]:
        rows = self.db.run("SELECT path, sha FROM bases WHERE vault_id = ? AND peer_id = ?",
                           (_check_id(vault_id), _check_id(peer_id)))
        return {r["path"]: r["sha"] for r in rows}

    def update_base(self, vault_id: str, peer_id: str, updates: dict[str, str]) -> None:
        _check_id(vault_id), _check_id(peer_id)
        self.db.run_many("INSERT OR REPLACE INTO bases(vault_id, peer_id, path, sha) VALUES (?, ?, ?, ?)",
                         [(vault_id, peer_id, p, s) for p, s in updates.items()])

    def backup_file(self, stamp: str, rel: str, src: Path) -> None:
        dst = self.root / "backups" / stamp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def list_backups(self) -> list[str]:
        d = self.root / "backups"
        return sorted((p.name for p in d.iterdir()), reverse=True) if d.is_dir() else []

    def audit(self, event: str, **fields) -> None:
        self.db.run("INSERT INTO audit(ts, event, data) VALUES (?, ?, ?)",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), event, json.dumps(fields)))

    def read_audit(self, limit: int = 200) -> list[dict]:
        rows = self.db.run("SELECT ts, event, data FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [{"ts": r["ts"], "event": r["event"], **json.loads(r["data"])} for r in rows]
