"""Walk a vault and describe its shareable items."""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from src.errors import BrainSyncError
from src.security import is_hard_blocked

_EXT = {".md", ".canvas", ".base", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
_OBS_SKIP = {".obsidian/workspace.json", ".obsidian/workspaces.json", ".obsidian/graph.json"}
_PRUNE = {".git", ".trash", "node_modules"}


class FrontmatterError(BrainSyncError):
    pass


@dataclass(frozen=True)
class Item:
    path: str
    sha256: str
    size: int
    mtime: float
    type: str = ""
    status: str = ""
    tags: tuple[str, ...] = ()
    created: str = ""
    private: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tags"] = list(self.tags)
        return d


def is_content(rel: str) -> bool:
    """The vault's own .gitignore whitelist, as code."""
    if is_hard_blocked(rel):
        return False
    if rel.startswith("_setup/"):
        return True
    if rel.startswith(".obsidian/"):
        name = rel.rsplit("/", 1)[-1]
        if rel in _OBS_SKIP or rel.startswith(".obsidian/cache"):
            return False
        if rel.startswith(".obsidian/plugins/") and name in ("main.js", "styles.css", "data.json.bak"):
            return False
        return True
    return PurePosixPath(rel).suffix.lower() in _EXT


def parse_frontmatter(text: str) -> dict:
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise FrontmatterError("unterminated frontmatter")
    out: dict = {}
    key = None
    for ln in lines[1:end]:
        s = ln.strip()
        if s.startswith("- ") and key is not None:
            cur = out.get(key)
            if not isinstance(cur, list):
                cur = [] if cur in ("", None) else [cur]
                out[key] = cur
            cur.append(s[2:].strip().strip("'\""))
        elif ":" in ln and not ln.startswith((" ", "\t")):
            k, _, v = ln.partition(":")
            key, v = k.strip().lower(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                out[key] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            else:
                out[key] = v.strip("'\"")
    return out


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _in_private_folder(rel: str, folders: list[str]) -> bool:
    for f in folders:
        f = f.strip().strip("/")
        if f and (rel == f or rel.startswith(f + "/")):
            return True
    return False


def _item(root: Path, rel: str, private_folders: list[str]) -> Item:
    p = root / rel
    st = p.stat()
    private = _in_private_folder(rel, private_folders)
    fm: dict = {}
    if rel.endswith(".md"):
        try:
            fm = parse_frontmatter(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, FrontmatterError):
            private = True  # fail closed: unreadable means private
        if str(fm.get("private", "")).lower() == "true":
            private = True
    tags = fm.get("tags", [])
    tags = tuple(tags) if isinstance(tags, list) else ((tags,) if tags else ())
    return Item(rel, _sha(p), st.st_size, st.st_mtime, str(fm.get("type", "")), str(fm.get("status", "")),
                tags, str(fm.get("created", "")), private)


def scan_vault(root: Path, private_folders: list[str]) -> list[Item]:
    """Blocking: call through asyncio.to_thread."""
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE]
        for name in filenames:
            rel = (Path(dirpath) / name).relative_to(root).as_posix()
            if is_content(rel):
                items.append(_item(root, rel, private_folders))
    return sorted(items, key=lambda i: i.path)
