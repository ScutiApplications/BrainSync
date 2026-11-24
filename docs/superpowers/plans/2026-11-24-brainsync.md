# BrainSync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, inline, one agent, straight through. Workspace rules override the skill defaults: no worktree, no branch, no commit, no baseline run, no subagent review, no full-suite run. Steps use checkbox (`- [ ]`) syntax. Report once at the end.

**Goal:** Build BrainSync, a native Windows service that exports, imports, live-shares and sets up Obsidian Brain vaults (with Claude Code and Codex config) between devices on one LAN.

**Architecture:** A FastAPI app with small focused modules: scanner and filters pick items, a packager writes and verifies `.brainpack` zips, a per-peer sync base enables 3-way merge, a share manager serves a read-only LAN API, a peer client pulls from it, and an agent-setup module builds a diff plan before writing agent config. One vanilla-JS admin page drives it all.

**Tech Stack:** Python 3.11+, uv, FastAPI, uvicorn, httpx, merge3, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-brainsync-design.md` (read it first).

## Global Constraints

- Project folder: `D:\User\Documents\Programming\Applications\BrainSync`. Run every command from there.
- Windows only. Native run, no Docker. Port `26508` (re-check it is still free: grep `26508` in the workspace `AGENTS.md` files and compose files before Task 11).
- Never read or print `.env` files, `secrets/`, key files.
- Use uv, never pip. On this machine: `$env:UV_CACHE_DIR = "D:/User/.uv-cache"` before `uv` commands.
- All blocking work (file IO, zip, subprocess) runs in `asyncio.to_thread` inside request handlers.
- Error messages never contain paths.
- ServiceHub ruling: bind `0.0.0.0` by default, `GET /health` returns 200 without auth, UI uses relative URLs only (page served at `/` only), unique host port.
- No password = no start: `BRAINSYNC_ADMIN_PASSWORD` is required.
- Never git commit; `git init -b main` inside `BrainSync` only.
- Tests only for the logic listed in the spec. Run each task's test file once.

---

### Task 1: Scaffold and spec patch

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `run.bat`, `CLAUDE.md`, `src/__init__.py`, `src/errors.py`, `src/config.py`, `src/fsutil.py`, `tests/__init__.py`, `tests/helpers.py`
- Modify: `docs/superpowers/specs/2026-11-24-brainsync-design.md`

**Interfaces:**
- Produces: `errors.BrainSyncError`; `config.Settings(data_dir: Path, admin_password: str, home: Path, port: int = 26508, bind: str = "0.0.0.0")`; `config.load_settings() -> Settings`; `fsutil.write_atomic(path: Path, data: bytes) -> None`; `tests.helpers.make_vault(root: Path, files: dict[str, str | bytes]) -> Path`.

- [ ] **Step 1: Create the project files**

`pyproject.toml`:

```toml
[project]
name = "brainsync"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115", "uvicorn>=0.30", "httpx>=0.27", "merge3>=0.0.15"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`.gitignore`:

```
.venv/
.data/
.env
__pycache__/
*.pyc
```

`run.bat`:

```bat
@echo off
cd /d "%~dp0"
uv run python -m src.run --dotenv
```

`CLAUDE.md`:

```
@AGENTS.md
```

`src/__init__.py` and `tests/__init__.py`: empty files.

`src/errors.py`:

```python
"""Shared error base. Messages are safe to show to the user: they never contain paths."""


class BrainSyncError(Exception):
    """An expected failure with a user-safe message."""
```

`src/config.py`:

```python
"""Runtime settings read from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    admin_password: str
    home: Path
    port: int = 26508
    bind: str = "0.0.0.0"


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    return Settings(
        data_dir=Path(os.environ.get("BRAINSYNC_DATA_DIR") or root / ".data"),
        admin_password=os.environ.get("BRAINSYNC_ADMIN_PASSWORD", ""),
        home=Path(os.environ.get("BRAINSYNC_HOME") or Path.home()),
        port=int(os.environ.get("BRAINSYNC_PORT", "26508")),
        bind=os.environ.get("SERVICE_BIND", "0.0.0.0"),
    )
```

`src/fsutil.py`:

```python
"""Small file helpers."""
from __future__ import annotations

import os
from pathlib import Path


def write_atomic(path: Path, data: bytes) -> None:
    """Write to a temp file in the same folder, then replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".bs-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
```

`tests/helpers.py`:

```python
from __future__ import annotations

from pathlib import Path


def make_vault(root: Path, files: dict) -> Path:
    """Create a minimal vault folder plus the given files."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".obsidian").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return root
```

- [ ] **Step 2: Patch the spec** (small corrections found while planning). Apply these `Edit`s to `docs/superpowers/specs/2026-11-24-brainsync-design.md`:

1. Old: `- After a successful import or export, the base is updated for the items that moved.`
   New: `- After a successful import (file or live pull), the base is updated for the items that moved. Export cannot know the receiving device, so it records nothing.`
2. Old: `- Registering a vault checks that the folder has `.obsidian/` and `AGENTS.md`. Registering never modifies the vault.`
   New: `- Registering a vault checks that the folder has `.obsidian/` and `AGENTS.md`. Registering never modifies the vault. The one exception is "create": for a missing or empty folder, BrainSync creates `.obsidian/` so a Starter pack can be imported into it.`
3. Old: `  src/  app.py config.py vaults.py scanner.py filters.py packager.py\n        merger.py state.py sharing.py peer.py agent_setup.py security.py`
   New: `  src/  app.py ctx.py config.py errors.py fsutil.py vaults.py scanner.py filters.py\n        packager.py merger.py importer.py state.py sharing.py routes_share.py\n        routes_admin.py peer.py agent_setup.py security.py run.py`
4. Old: `One page, `web/index.html`, relative URLs only,`
   New: `One page, `web/index.html`, served at `/` only, relative URLs only,`
5. Old: `2. The peer enters the sharer's `ip:port` and the code.`
   New: `2. The peer enters the sharer's LAN IPv4 `ip:port` (hostnames and non-LAN addresses are refused) and the code.`

- [ ] **Step 3: Init and sync**

Run:

```powershell
git init -b main
$env:UV_CACHE_DIR = "D:/User/.uv-cache"; uv sync
```

Expected: `.venv` created, `merge3`, `fastapi`, `httpx`, `uvicorn`, `pytest` installed.

---

### Task 2: security.py

**Files:**
- Create: `src/security.py`, `tests/test_security.py`

**Interfaces:**
- Produces: `UnsafePath(BrainSyncError)`; `is_hard_blocked(rel: str) -> bool`; `check_rel(rel: str) -> None` (raises `UnsafePath`); `safe_join(root: Path, rel: str) -> Path`; `is_lan_ip(host: str) -> bool`.

- [ ] **Step 1: Write the failing test** `tests/test_security.py`

```python
import pytest

from src.security import UnsafePath, check_rel, is_hard_blocked, is_lan_ip, safe_join


def test_hard_blocks():
    for rel in [".env", "a/.env.local", "secrets/x.md", "x/.git/config", "k/id_rsa.pub", "a.pem", "b/.trash/n.md", ".secrets/a"]:
        assert is_hard_blocked(rel), rel
    for rel in ["Notes/a.md", "Notes/environment.md", "Projects/Secretary.md"]:
        assert not is_hard_blocked(rel), rel


@pytest.mark.parametrize("rel", ["", "/a", "../a", "a/../b", "a\\b", "C:/x", "a//b", "./a"])
def test_check_rel_rejects(rel):
    with pytest.raises(UnsafePath):
        check_rel(rel)


def test_safe_join(tmp_path):
    assert safe_join(tmp_path, "Notes/a.md") == (tmp_path / "Notes" / "a.md").resolve()
    with pytest.raises(UnsafePath):
        safe_join(tmp_path, "../x")


def test_lan():
    for ip in ["192.168.1.5", "10.0.0.2", "172.20.1.1", "127.0.0.1", "169.254.1.1", "::1", "fe80::1"]:
        assert is_lan_ip(ip), ip
    for ip in ["8.8.8.8", "172.32.0.1", "testclient", "", "100.64.0.1"]:
        assert not is_lan_ip(ip), ip
```

- [ ] **Step 2: Run, expect FAIL** (module missing)

Run: `uv run pytest -q tests/test_security.py`

- [ ] **Step 3: Implement** `src/security.py`

```python
"""Path safety, hard blocks and the LAN check."""
from __future__ import annotations

import ipaddress
from pathlib import Path, PurePosixPath

from src.errors import BrainSyncError


class UnsafePath(BrainSyncError):
    pass


_BLOCK_PARTS = {".git", ".trash", "secrets", ".secrets"}
_BLOCK_SUFFIX = {".pem", ".key", ".pfx", ".p12"}
_BLOCK_PREFIX = (".env", "id_rsa", "id_ed25519")
_LAN = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
              "127.0.0.0/8", "::1/128", "fe80::/10", "fc00::/7")
]


def is_hard_blocked(rel: str) -> bool:
    """True for files that must never enter a pack or a share."""
    parts = [p.lower() for p in PurePosixPath(rel.replace("\\", "/")).parts]
    if not parts or any(p in _BLOCK_PARTS for p in parts):
        return bool(parts)
    name = parts[-1]
    return name.startswith(_BLOCK_PREFIX) or PurePosixPath(name).suffix in _BLOCK_SUFFIX


def check_rel(rel: str) -> None:
    """Reject anything that is not a plain relative posix path."""
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/") or ":" in rel or "\x00" in rel:
        raise UnsafePath("unsafe path")
    if any(p in ("", ".", "..") for p in rel.split("/")):
        raise UnsafePath("unsafe path")


def safe_join(root: Path, rel: str) -> Path:
    """Join rel under root; refuse anything that leaves root."""
    check_rel(rel)
    base = root.resolve()
    p = (base / rel).resolve()
    if not p.is_relative_to(base):
        raise UnsafePath("unsafe path")
    return p


def is_lan_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in n for n in _LAN)
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_security.py`

---

### Task 3: scanner.py (items, frontmatter, privacy)

**Files:**
- Create: `src/scanner.py`, `tests/test_scanner.py`

**Interfaces:**
- Consumes: `security.is_hard_blocked`.
- Produces: `Item` frozen dataclass `(path, sha256, size, mtime, type="", status="", tags: tuple[str, ...]=(), created="", private=False)` with `to_dict() -> dict`; `parse_frontmatter(text) -> dict`; `FrontmatterError`; `scan_vault(root: Path, private_folders: list[str]) -> list[Item]` (sorted by path).

- [ ] **Step 1: Write the failing test** `tests/test_scanner.py`

```python
import pytest

from src.scanner import FrontmatterError, parse_frontmatter, scan_vault
from tests.helpers import make_vault


def test_frontmatter_forms():
    fm = parse_frontmatter("---\ntype: note\ntags:\n  - a\n  - b\nstatus: 'seed'\n---\nbody")
    assert fm == {"type": "note", "tags": ["a", "b"], "status": "seed"}
    assert parse_frontmatter("no front") == {}
    with pytest.raises(FrontmatterError):
        parse_frontmatter("---\ntitle: x\nno end")


def test_scan_privacy_and_whitelist(tmp_path):
    v = make_vault(tmp_path / "v", {
        "Notes/a.md": "---\ntype: note\nstatus: active\ntags: [x, y]\ncreated: 2026-01-02\n---\nbody",
        "Notes/p.md": "---\nprivate: true\n---\nP",
        "Notes/bad.md": "---\ntitle: x\nno end",
        "Priv/z.md": "plain",
        "secrets/s.md": "no", ".env": "K=1",
        ".obsidian/app.json": "{}", ".obsidian/workspace.json": "{}",
        "Notes/pic.png": b"\x89PNG", "Notes/x.exe": b"MZ", "_setup/hooks/h.py": "print(1)",
    })
    items = {i.path: i for i in scan_vault(v, ["Priv"])}
    for gone in ["secrets/s.md", ".env", ".obsidian/workspace.json", "Notes/x.exe"]:
        assert gone not in items
    for kept in [".obsidian/app.json", "_setup/hooks/h.py", "Notes/pic.png"]:
        assert kept in items
    a = items["Notes/a.md"]
    assert (a.type, a.status, a.tags, a.created, a.private) == ("note", "active", ("x", "y"), "2026-01-02", False)
    assert items["Notes/p.md"].private and items["Notes/bad.md"].private and items["Priv/z.md"].private
    assert not items["AGENTS.md"].private
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_scanner.py`

- [ ] **Step 3: Implement** `src/scanner.py`

```python
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
    lines = text.lstrip("\ufeff").splitlines()
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
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_scanner.py`

---

### Task 4: filters.py (selection and Starter preset)

**Files:**
- Create: `src/filters.py`, `tests/test_filters.py`

**Interfaces:**
- Consumes: `scanner.Item`.
- Produces: `Filter` dataclass `(paths, types, statuses, tags: list[str]; created_from, created_to, modified_from, modified_to: str; changed_since: dict[str,str] | None)`; `Selection(filter, include: set, include_private: set, exclude: set, use_filter: bool=True)` with `Selection.from_dict(d)`; `STARTER: Selection`; `select(items: list[Item], sel: Selection) -> list[Item]`.

- [ ] **Step 1: Write the failing test** `tests/test_filters.py`

```python
from src.filters import STARTER, Filter, Selection, select
from src.scanner import Item


def it(path, **kw):
    return Item(path=path, sha256=kw.pop("sha", "h"), size=1, mtime=kw.pop("mtime", 0.0), **kw)


ITEMS = [
    it("Notes/a.md", type="note", status="active", tags=("x",), created="2026-02-01"),
    it("Notes/b.md", type="note", status="seed", tags=("y",), created="2026-03-01"),
    it("Notes/p.md", type="note", private=True),
    it("Templates/t.md"), it("AGENTS.md"), it("_setup/s.json"), it(".obsidian/app.json"),
]


def paths(sel):
    return [i.path for i in select(ITEMS, sel)]


def test_private_never_by_filter():
    assert "Notes/p.md" not in paths(Selection())
    assert "Notes/p.md" not in paths(Selection(filter=Filter(paths=["Notes/*"])))
    assert "Notes/p.md" in paths(Selection(include_private={"Notes/p.md"}))


def test_filter_fields():
    assert paths(Selection(filter=Filter(types=["note"], statuses=["active"]))) == ["Notes/a.md"]
    assert paths(Selection(filter=Filter(tags=["y"]))) == ["Notes/b.md"]
    assert paths(Selection(filter=Filter(created_from="2026-02-15"))) == ["Notes/b.md"]
    assert paths(Selection(filter=Filter(created_to="2026-02-15"))) == ["Notes/a.md"]


def test_include_exclude_and_explicit_mode():
    assert paths(Selection(use_filter=False, include={"AGENTS.md"})) == ["AGENTS.md"]
    assert "Notes/a.md" not in paths(Selection(exclude={"Notes/a.md"}))


def test_changed_since():
    sel = Selection(filter=Filter(changed_since={"Notes/a.md": "h", "Notes/b.md": "old"}, paths=["Notes/*"]))
    assert paths(sel) == ["Notes/b.md"]


def test_starter():
    got = paths(STARTER)
    assert set(got) == {"Templates/t.md", "AGENTS.md", "_setup/s.json", ".obsidian/app.json"}
    assert Selection.from_dict({"filter": {"tags": ["x"]}, "include": ["AGENTS.md"]}).include == {"AGENTS.md"}
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_filters.py`

- [ ] **Step 3: Implement** `src/filters.py`

```python
"""Choose which items go into a pack or a share."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime

from src.scanner import Item

_FILTER_KEYS = ("paths", "types", "statuses", "tags", "created_from", "created_to", "modified_from", "modified_to")


@dataclass
class Filter:
    paths: list[str] = field(default_factory=list)  # fnmatch globs on the posix path; empty = all
    types: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_from: str = ""
    created_to: str = ""
    modified_from: str = ""
    modified_to: str = ""
    changed_since: dict[str, str] | None = None  # path -> sha last agreed with a peer


@dataclass
class Selection:
    filter: Filter = field(default_factory=Filter)
    include: set[str] = field(default_factory=set)
    include_private: set[str] = field(default_factory=set)  # exact paths only
    exclude: set[str] = field(default_factory=set)
    use_filter: bool = True  # False = only the explicit include lists

    @classmethod
    def from_dict(cls, d: dict) -> "Selection":
        f = d.get("filter") or {}
        flt = Filter(**{k: f[k] for k in _FILTER_KEYS if k in f})
        return cls(flt, set(d.get("include", [])), set(d.get("include_private", [])),
                   set(d.get("exclude", [])), bool(d.get("use_filter", True)))


STARTER = Selection(filter=Filter(paths=[
    "AGENTS.md", "CLAUDE.md", "Templates/*", ".obsidian/*", "_setup/*", "00 Dashboard.md"]))


def _match(it: Item, f: Filter) -> bool:
    if f.paths and not any(fnmatch.fnmatchcase(it.path, g) for g in f.paths):
        return False
    if f.types and it.type not in f.types:
        return False
    if f.statuses and it.status not in f.statuses:
        return False
    if f.tags and not set(f.tags) & set(it.tags):
        return False
    if f.created_from and (not it.created or it.created < f.created_from):
        return False
    if f.created_to and (not it.created or it.created > f.created_to):
        return False
    if f.modified_from or f.modified_to:
        mod = datetime.fromtimestamp(it.mtime).date().isoformat()
        if (f.modified_from and mod < f.modified_from) or (f.modified_to and mod > f.modified_to):
            return False
    if f.changed_since is not None and f.changed_since.get(it.path) == it.sha256:
        return False
    return True


def select(items: list[Item], sel: Selection) -> list[Item]:
    """Private items are chosen only by exact path in include_private, never by a filter."""
    out = []
    for it in items:
        if it.path in sel.exclude:
            continue
        if it.private:
            if it.path in sel.include_private:
                out.append(it)
        elif it.path in sel.include or (sel.use_filter and _match(it, sel.filter)):
            out.append(it)
    return out
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_filters.py`

---

### Task 5: packager.py

**Files:**
- Create: `src/packager.py`, `tests/test_packager.py`

**Interfaces:**
- Consumes: `scanner.Item`, `scan_vault`, `security.check_rel/is_hard_blocked/safe_join`.
- Produces: `PackError(BrainSyncError)`; `write_pack(dest: Path, root: Path, items, *, device_id: str, vault_name: str) -> dict`; `read_manifest(pack: Path) -> dict` (validates format, paths, device id); `read_file(pack: Path, entry: dict) -> bytes` (size-limited, sha-verified).
- Manifest: `{format, pack_id, source_device_id (32 hex), vault_name, created, items:[{path, sha256, size, mtime, private}]}`.

- [ ] **Step 1: Write the failing test** `tests/test_packager.py`

```python
import json
import zipfile

import pytest

from src.packager import PackError, read_file, read_manifest, write_pack
from src.scanner import scan_vault
from tests.helpers import make_vault

DEV = "a" * 32


def test_roundtrip_and_tamper(tmp_path):
    v = make_vault(tmp_path / "v", {"Notes/a.md": "hello"})
    pack = tmp_path / "p.brainpack"
    write_pack(pack, v, scan_vault(v, []), device_id=DEV, vault_name="v")
    m = read_manifest(pack)
    entry = next(e for e in m["items"] if e["path"] == "Notes/a.md")
    assert read_file(pack, entry) == b"hello"
    bad = tmp_path / "bad.brainpack"
    with zipfile.ZipFile(pack) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, b"tampered" if n == "files/Notes/a.md" else src.read(n))
    with pytest.raises(PackError):
        read_file(bad, entry)


@pytest.mark.parametrize("path", ["../x", "/abs", ".env", "a/secrets/b.md"])
def test_manifest_rejects_bad_paths(tmp_path, path):
    pack = tmp_path / "m.brainpack"
    m = {"format": 1, "pack_id": "p", "source_device_id": DEV, "vault_name": "v", "created": "x",
         "items": [{"path": path, "sha256": "0", "size": 0, "mtime": 0, "private": False}]}
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
    with pytest.raises(PackError):
        read_manifest(pack)


def test_not_a_pack(tmp_path):
    p = tmp_path / "x.brainpack"
    p.write_bytes(b"nope")
    with pytest.raises(PackError):
        read_manifest(p)
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_packager.py`

- [ ] **Step 3: Implement** `src/packager.py`

```python
"""Write, read and verify .brainpack zips. Blocking: call through asyncio.to_thread."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from src.errors import BrainSyncError
from src.scanner import Item
from src.security import UnsafePath, check_rel, is_hard_blocked, safe_join

FORMAT = 1
MAX_FILE = 100 * 1024 * 1024
MAX_MANIFEST = 50 * 1024 * 1024
_DEVICE = re.compile(r"[0-9a-f]{32}")


class PackError(BrainSyncError):
    pass


def write_pack(dest: Path, root: Path, items: Iterable[Item], *, device_id: str, vault_name: str) -> dict:
    entries = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for it in items:
            data = safe_join(root, it.path).read_bytes()
            z.writestr(f"files/{it.path}", data)
            entries.append({"path": it.path, "sha256": hashlib.sha256(data).hexdigest(),
                            "size": len(data), "mtime": it.mtime, "private": it.private})
        manifest = {"format": FORMAT, "pack_id": uuid4().hex, "source_device_id": device_id,
                    "vault_name": vault_name,
                    "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": entries}
        z.writestr("manifest.json", json.dumps(manifest))
    return manifest


def read_manifest(pack: Path) -> dict:
    try:
        with zipfile.ZipFile(pack) as z:
            if z.getinfo("manifest.json").file_size > MAX_MANIFEST:
                raise PackError("not a valid pack")
            m = json.loads(z.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise PackError("not a valid pack") from None
    if not isinstance(m, dict) or m.get("format") != FORMAT or not isinstance(m.get("items"), list):
        raise PackError("unsupported pack")
    if not isinstance(m.get("source_device_id"), str) or not _DEVICE.fullmatch(m["source_device_id"]):
        raise PackError("unsupported pack")
    for e in m["items"]:
        try:
            check_rel(e["path"])
        except (UnsafePath, KeyError, TypeError):
            raise PackError("pack has an unsafe path") from None
        if is_hard_blocked(e["path"]):
            raise PackError("pack has a blocked path")
    return m


def read_file(pack: Path, entry: dict) -> bytes:
    """Return one file's bytes after checking size and sha256."""
    try:
        with zipfile.ZipFile(pack) as z:
            info = z.getinfo("files/" + entry["path"])
            if info.file_size > MAX_FILE:
                raise PackError("pack failed verification")
            data = z.read(info)
    except (zipfile.BadZipFile, KeyError, OSError):
        raise PackError("pack failed verification") from None
    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        raise PackError("pack failed verification")
    return data
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_packager.py`

---

### Task 6: state.py and vaults.py (no own tests; covered by Tasks 8, 9, 11)

**Files:**
- Create: `src/state.py`, `src/vaults.py`

**Interfaces:**
- Consumes: `fsutil.write_atomic`, `errors.BrainSyncError`.
- Produces `State(root: Path)`: `.root`, `device_id() -> str` (32 hex), `put_blob(data) -> str`, `get_blob(sha) -> bytes | None`, `load_base(vault_id, peer_id) -> dict[str, str]`, `update_base(vault_id, peer_id, updates: dict[str, str])`, `backup_file(stamp: str, rel: str, src: Path)`, `audit(event: str, **fields)`, `read_audit(limit=200) -> list[dict]`, `list_backups() -> list[str]`.
- Produces `VaultRegistry(file: Path)`: `list() -> list[dict]` (each `{id, name, path, private_folders, active}`), `get(id) -> dict`, `add(name, path, create=False) -> dict`, `remove(id)`, `set_private_folders(id, folders)`, `set_active(id)`, `active() -> dict | None`; `VaultError(BrainSyncError)`.

- [ ] **Step 1: Implement** `src/state.py`

```python
"""Service state: device id, content blobs, per-peer sync bases, backups, audit log."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from src.fsutil import write_atomic

_ID = re.compile(r"[0-9a-f]{32}")


def _check_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("bad id")
    return value


class State:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def device_id(self) -> str:
        f = self.root / "device.json"
        if f.is_file():
            return json.loads(f.read_text("utf-8"))["device_id"]
        did = uuid4().hex
        write_atomic(f, json.dumps({"device_id": did}).encode())
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

    def _base_file(self, vault_id: str, peer_id: str) -> Path:
        return self.root / "bases" / _check_id(vault_id) / f"{_check_id(peer_id)}.json"

    def load_base(self, vault_id: str, peer_id: str) -> dict[str, str]:
        f = self._base_file(vault_id, peer_id)
        return json.loads(f.read_text("utf-8")) if f.is_file() else {}

    def update_base(self, vault_id: str, peer_id: str, updates: dict[str, str]) -> None:
        if not updates:
            return
        base = self.load_base(vault_id, peer_id)
        base.update(updates)
        write_atomic(self._base_file(vault_id, peer_id), json.dumps(base).encode())

    def backup_file(self, stamp: str, rel: str, src: Path) -> None:
        dst = self.root / "backups" / stamp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def list_backups(self) -> list[str]:
        d = self.root / "backups"
        return sorted((p.name for p in d.iterdir()), reverse=True) if d.is_dir() else []

    def audit(self, event: str, **fields) -> None:
        line = json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields})
        with (self.root / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_audit(self, limit: int = 200) -> list[dict]:
        f = self.root / "audit.jsonl"
        if not f.is_file():
            return []
        return [json.loads(x) for x in f.read_text("utf-8").splitlines()[-limit:]][::-1]
```

- [ ] **Step 2: Implement** `src/vaults.py`

```python
"""Registry of known vaults. Never modifies a vault except the one 'create' exception."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from src.errors import BrainSyncError
from src.fsutil import write_atomic


class VaultError(BrainSyncError):
    pass


class VaultRegistry:
    def __init__(self, file: Path):
        self.file = file

    def _load(self) -> dict:
        return json.loads(self.file.read_text("utf-8")) if self.file.is_file() else {"vaults": [], "active": None}

    def _save(self, data: dict) -> None:
        write_atomic(self.file, json.dumps(data, indent=2).encode())

    def list(self) -> list[dict]:
        d = self._load()
        return [{**v, "active": v["id"] == d["active"]} for v in d["vaults"]]

    def get(self, vault_id: str) -> dict:
        for v in self._load()["vaults"]:
            if v["id"] == vault_id:
                return v
        raise VaultError("unknown vault")

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
        d = self._load()
        if any(Path(v["path"]) == p for v in d["vaults"]):
            raise VaultError("vault already registered")
        v = {"id": uuid4().hex, "name": name, "path": str(p), "private_folders": []}
        d["vaults"].append(v)
        d["active"] = d["active"] or v["id"]
        self._save(d)
        return v

    def remove(self, vault_id: str) -> None:
        d = self._load()
        d["vaults"] = [v for v in d["vaults"] if v["id"] != vault_id]
        if d["active"] == vault_id:
            d["active"] = d["vaults"][0]["id"] if d["vaults"] else None
        self._save(d)

    def set_private_folders(self, vault_id: str, folders: list[str]) -> None:
        d = self._load()
        v = next((v for v in d["vaults"] if v["id"] == vault_id), None)
        if v is None:
            raise VaultError("unknown vault")
        v["private_folders"] = [f.strip().strip("/") for f in folders if f.strip().strip("/")]
        self._save(d)

    def set_active(self, vault_id: str) -> None:
        self.get(vault_id)
        d = self._load()
        d["active"] = vault_id
        self._save(d)

    def active(self) -> dict | None:
        d = self._load()
        return next((v for v in d["vaults"] if v["id"] == d["active"]), None)
```

- [ ] **Step 3: Import check**

Run: `uv run python -c "import src.state, src.vaults; print('ok')"`
Expected: `ok`

---

### Task 7: merger.py

**Files:**
- Create: `src/merger.py`, `tests/test_merger.py`

**Interfaces:**
- Produces: `MergeError(BrainSyncError)`; `norm(b: bytes) -> bytes`; `classify(mine: bytes | None, theirs: bytes, base: bytes | None) -> str` returning `new | identical | no_base | theirs_only | mine_only | conflict`; `is_text(b) -> bool`; `merge_hunks(base: bytes | None, mine: bytes, theirs: bytes) -> list[dict]` (hunks `{"kind":"clean","lines":[...]}` or `{"kind":"conflict","mine":[...],"theirs":[...]}`); `conflict_count(hunks) -> int`; `resolve(hunks, choices: dict) -> str` (choice per conflict index, key int or str: `"mine" | "theirs" | "both" | {"text": str}`); `union_lines(mine: str, theirs: str) -> str`; `keep_both_name(rel: str, device: str) -> str`.

- [ ] **Step 1: Write the failing test** `tests/test_merger.py`

```python
import pytest

from src.merger import (MergeError, classify, conflict_count, is_text, keep_both_name,
                        merge_hunks, resolve, union_lines)


def test_classify_table():
    assert classify(None, b"t", None) == "new"
    assert classify(b"a\r\nb", b"a\nb", None) == "identical"
    assert classify(b"m", b"t", None) == "no_base"
    assert classify(b"base", b"t", b"base") == "theirs_only"
    assert classify(b"m", b"base", b"base") == "mine_only"
    assert classify(b"m", b"t", b"base") == "conflict"


def test_clean_three_way():
    h = merge_hunks(b"one\ntwo\nthree\n", b"ONE\ntwo\nthree\n", b"one\ntwo\nTHREE\n")
    assert conflict_count(h) == 0
    assert resolve(h, {}) == "ONE\ntwo\nTHREE\n"


def test_conflict_choices():
    h = merge_hunks(b"x\n", b"B\n", b"A\n")
    assert conflict_count(h) == 1
    with pytest.raises(MergeError):
        resolve(h, {})
    assert resolve(h, {"0": "mine"}) == "B\n"
    assert resolve(h, {0: "theirs"}) == "A\n"
    assert resolve(h, {0: "both"}) == "B\nA\n"
    assert resolve(h, {0: {"text": "edited\n"}}) == "edited\n"


def test_two_way_when_no_base():
    h = merge_hunks(None, b"same\nmine\n", b"same\ntheirs\n")
    assert conflict_count(h) == 1
    assert resolve(h, {0: "theirs"}) == "same\ntheirs\n"


def test_helpers():
    assert union_lines("a\nb\n", "b\nc\nc\n") == "a\nb\nc\n"
    assert keep_both_name("Notes/pic.png", "Lap/top") == "Notes/pic (from Lap_top).png"
    assert is_text(b"hi") and not is_text(b"\x00\x01") and not is_text(b"\xff\xfe\xfa")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_merger.py`

- [ ] **Step 3: Implement** `src/merger.py`

```python
"""Classification and 3-way text merge."""
from __future__ import annotations

import difflib
import re
from pathlib import PurePosixPath

from merge3 import Merge3

from src.errors import BrainSyncError


class MergeError(BrainSyncError):
    pass


def norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def classify(mine: bytes | None, theirs: bytes, base: bytes | None) -> str:
    if mine is None:
        return "new"
    if norm(mine) == norm(theirs):
        return "identical"
    if base is None:
        return "no_base"
    if norm(mine) == norm(base):
        return "theirs_only"
    if norm(theirs) == norm(base):
        return "mine_only"
    return "conflict"


def is_text(b: bytes) -> bool:
    if b"\x00" in b:
        return False
    try:
        b.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _lines(b: bytes) -> list[str]:
    return norm(b).decode("utf-8").splitlines(keepends=True)


def merge_hunks(base: bytes | None, mine: bytes, theirs: bytes) -> list[dict]:
    a, b = _lines(mine), _lines(theirs)
    out: list[dict] = []
    if base is None:  # first sync: 2-way diff, every difference is a hunk to decide
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                out.append({"kind": "clean", "lines": a[i1:i2]})
            else:
                out.append({"kind": "conflict", "mine": a[i1:i2], "theirs": b[j1:j2]})
        return out
    for g in Merge3(_lines(base), a, b).merge_groups():
        if g[0] == "conflict":
            out.append({"kind": "conflict", "mine": g[2], "theirs": g[3]})
        else:
            out.append({"kind": "clean", "lines": g[1]})
    return out


def conflict_count(hunks: list[dict]) -> int:
    return sum(1 for h in hunks if h["kind"] == "conflict")


def _end_nl(lines: list[str]) -> list[str]:
    return lines[:-1] + [lines[-1] + "\n"] if lines and not lines[-1].endswith("\n") else lines


def resolve(hunks: list[dict], choices: dict) -> str:
    choices = {int(k): v for k, v in choices.items()}
    parts: list[str] = []
    n = 0
    for h in hunks:
        if h["kind"] == "clean":
            parts += h["lines"]
            continue
        c = choices.get(n)
        if c == "mine":
            parts += h["mine"]
        elif c == "theirs":
            parts += h["theirs"]
        elif c == "both":
            parts += _end_nl(h["mine"]) + h["theirs"]
        elif isinstance(c, dict) and isinstance(c.get("text"), str):
            parts.append(c["text"])
        else:
            raise MergeError("unresolved conflict")
        n += 1
    return "".join(parts)


def union_lines(mine: str, theirs: str) -> str:
    have = set(mine.splitlines())
    extra = []
    for ln in theirs.splitlines():
        if ln not in have:
            have.add(ln)
            extra.append(ln)
    lead = mine if mine.endswith("\n") or not mine else mine + "\n"
    return lead + "".join(x + "\n" for x in extra)


def keep_both_name(rel: str, device: str) -> str:
    safe = re.sub(r"[^\w .-]", "_", device)[:40] or "peer"
    p = PurePosixPath(rel)
    return p.with_name(f"{p.stem} (from {safe}){p.suffix}").as_posix()
```

- [ ] **Step 4: Run, expect PASS.** If `merge_groups` is missing in the installed `merge3`, read `uv run python -c "import merge3,inspect;print(inspect.getsource(merge3.Merge3))"` and adapt `merge_hunks` to the real group tuples; do not change the test.

Run: `uv run pytest -q tests/test_merger.py`

---

### Task 8: importer.py (preview and apply)

**Files:**
- Create: `src/importer.py`, `tests/test_importer.py`

**Interfaces:**
- Consumes: `packager.read_file`, `merger.*`, `state.State`, `security.safe_join`, `fsutil.write_atomic`.
- Produces: `DecisionError(BrainSyncError)`; `build_preview(root: Path, pack: Path, manifest: dict, state: State, vault_id: str) -> list[dict]` (row: `{path, state, private, binary, default}` plus `hunks`, `conflicts` for text conflicts; `default` is one of `import | skip | merge | unresolved`); `apply_import(root, pack, manifest, state, vault_id, decisions: dict[str, dict], device_name: str = "peer") -> dict` returning `{applied: [...], skipped: [...], backup: str | None}`.
- Decision: `{"action": "import" | "theirs" | "mine" | "both" | "merge" | "union" | "skip", "choices": {...}}`. Items absent from `decisions` are skipped. Base is updated to the incoming content for items that are applied, kept as mine, or identical.

- [ ] **Step 1: Write the failing test** `tests/test_importer.py`

```python
import pytest

from src.importer import apply_import, build_preview
from src.merger import MergeError
from src.packager import read_manifest, write_pack
from src.scanner import scan_vault
from src.state import State
from tests.helpers import make_vault


def export(vault, state):
    pack = vault.parent / f"{vault.name}-{len(list(vault.parent.glob('*.brainpack')))}.brainpack"
    write_pack(pack, vault, scan_vault(vault, []), device_id=state.device_id(), vault_name="v")
    return pack, read_manifest(pack)


def rows_of(b, pack, m, sb):
    return {r["path"]: r for r in build_preview(b, pack, m, sb, "b" * 32)}


def test_import_then_auto_merge(tmp_path):
    a = make_vault(tmp_path / "a", {"Notes/x.md": "one\ntwo\nthree\n", "Notes/y.md": "y1\n"})
    b = make_vault(tmp_path / "b", {})
    sa, sb = State(tmp_path / "sa"), State(tmp_path / "sb")
    pack, m = export(a, sa)
    rows = rows_of(b, pack, m, sb)
    assert rows["Notes/x.md"]["state"] == "new" and rows["AGENTS.md"]["state"] == "identical"
    decisions = {p: {"action": r["default"]} for p, r in rows.items() if r["default"] != "skip"}
    apply_import(b, pack, m, sb, "b" * 32, decisions)
    assert (b / "Notes/x.md").read_text() == "one\ntwo\nthree\n"

    (a / "Notes/x.md").write_text("ONE\ntwo\nthree\n")
    (b / "Notes/x.md").write_text("one\ntwo\nTHREE\n")
    pack2, m2 = export(a, sa)
    rows = rows_of(b, pack2, m2, sb)
    assert rows["Notes/x.md"]["state"] == "conflict" and rows["Notes/x.md"]["default"] == "merge"
    assert rows["Notes/y.md"]["state"] == "identical"
    res = apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/x.md": {"action": "merge"}})
    assert (b / "Notes/x.md").read_text() == "ONE\ntwo\nTHREE\n"
    assert res["applied"] == ["Notes/x.md"] and any((sb.root / "backups").rglob("x.md"))


def test_conflict_needs_choice_and_absent_means_skip(tmp_path):
    a = make_vault(tmp_path / "a", {"Notes/c.md": "base\n"})
    b = make_vault(tmp_path / "b", {})
    sa, sb = State(tmp_path / "sa"), State(tmp_path / "sb")
    pack, m = export(a, sa)
    apply_import(b, pack, m, sb, "b" * 32, {"Notes/c.md": {"action": "import"}})
    (a / "Notes/c.md").write_text("A\n")
    (b / "Notes/c.md").write_text("B\n")
    pack2, m2 = export(a, sa)
    assert rows_of(b, pack2, m2, sb)["Notes/c.md"]["default"] == "unresolved"
    with pytest.raises(MergeError):
        apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/c.md": {"action": "merge"}})
    assert (b / "Notes/c.md").read_text() == "B\n"
    apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/c.md": {"action": "merge", "choices": {"0": "both"}}})
    assert (b / "Notes/c.md").read_text() == "B\nA\n"
    # nothing decided -> nothing written
    (a / "Notes/c.md").write_text("A2\n")
    pack3, m3 = export(a, sa)
    assert apply_import(b, pack3, m3, sb, "b" * 32, {})["applied"] == []
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_importer.py`

- [ ] **Step 3: Implement** `src/importer.py`

```python
"""Preview and apply an import. Blocking: call through asyncio.to_thread."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.errors import BrainSyncError
from src.fsutil import write_atomic
from src.merger import (classify, conflict_count, is_text, keep_both_name, merge_hunks, resolve,
                        union_lines)
from src.packager import read_file
from src.security import safe_join
from src.state import State

DEFAULT = {"new": "import", "identical": "skip", "theirs_only": "import", "mine_only": "skip",
           "conflict": "unresolved", "no_base": "unresolved"}
_ACTIONS = {"import", "theirs", "mine", "both", "merge", "union", "skip"}


class DecisionError(BrainSyncError):
    pass


def _mine(root: Path, rel: str) -> bytes | None:
    p = safe_join(root, rel)
    return p.read_bytes() if p.is_file() else None


def _base(state: State, base_map: dict, rel: str) -> bytes | None:
    sha = base_map.get(rel)
    return state.get_blob(sha) if sha else None


def build_preview(root: Path, pack: Path, manifest: dict, state: State, vault_id: str) -> list[dict]:
    base_map = state.load_base(vault_id, manifest["source_device_id"])
    rows = []
    for e in manifest["items"]:
        theirs = read_file(pack, e)
        mine = _mine(root, e["path"])
        base = _base(state, base_map, e["path"])
        st = classify(mine, theirs, base)
        row = {"path": e["path"], "state": st, "private": bool(e.get("private")), "default": DEFAULT[st],
               "binary": not is_text(theirs) or (mine is not None and not is_text(mine))}
        if st in ("conflict", "no_base") and not row["binary"]:
            hunks = merge_hunks(base if st == "conflict" else None, mine, theirs)
            row["hunks"], row["conflicts"] = hunks, conflict_count(hunks)
            if st == "conflict" and row["conflicts"] == 0:
                row["default"] = "merge"
        rows.append(row)
    return rows


def apply_import(root: Path, pack: Path, manifest: dict, state: State, vault_id: str,
                 decisions: dict[str, dict], device_name: str = "peer") -> dict:
    peer = manifest["source_device_id"]
    base_map = state.load_base(vault_id, peer)
    writes: list[tuple[Path, str, bytes, bool]] = []  # (target, rel, data, backup_existing)
    updates: dict[str, str] = {}
    applied, skipped = [], []
    for e in manifest["items"]:
        rel = e["path"]
        theirs = read_file(pack, e)
        mine = _mine(root, rel)
        base = _base(state, base_map, rel)
        st = classify(mine, theirs, base)
        if st == "identical":
            updates[rel] = state.put_blob(theirs)
        d = decisions.get(rel)
        action = (d or {}).get("action", "skip")
        if action not in _ACTIONS:
            raise DecisionError("invalid decision")
        if action == "skip":
            skipped.append(rel)
            continue
        if mine is None and action not in ("import", "theirs"):
            raise DecisionError("invalid decision")
        if action in ("import", "theirs"):
            writes.append((safe_join(root, rel), rel, theirs, mine is not None))
        elif action == "both":
            alt = keep_both_name(rel, device_name)
            n = 1
            while safe_join(root, alt).exists():
                alt, n = keep_both_name(rel, f"{device_name} {n}"), n + 1
            writes.append((safe_join(root, alt), alt, theirs, False))
        elif action in ("merge", "union"):
            if not (is_text(theirs) and is_text(mine)):
                raise DecisionError("invalid decision")
            if action == "union":
                text = union_lines(mine.decode("utf-8"), theirs.decode("utf-8"))
            else:
                text = resolve(merge_hunks(base if st == "conflict" else None, mine, theirs),
                               (d or {}).get("choices", {}))
            data = text.encode("utf-8")
            writes.append((safe_join(root, rel), rel, data.replace(b"\n", b"\r\n") if b"\r\n" in mine else data, True))
        # "mine": keep the file, only record the base
        updates[rel] = state.put_blob(theirs)
        applied.append(rel)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backed = False
    for target, rel, data, backup in writes:  # phase 2: all decisions valid, now write
        if backup and target.is_file():
            state.backup_file(stamp, rel, target)
            backed = True
        write_atomic(target, data)
    state.update_base(vault_id, peer, updates)
    state.audit("import", vault_id=vault_id, peer=peer, count=len(applied))
    return {"applied": applied, "skipped": skipped, "backup": stamp if backed else None}
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_importer.py`

---

### Task 9: sharing.py, routes_share.py, peer.py, ctx.py

**Files:**
- Create: `src/sharing.py`, `src/ctx.py`, `src/routes_share.py`, `src/peer.py`, `src/app.py`, `tests/test_sharing.py`
- `src/app.py` is written in this task (Step 6) because the route test needs `create_app`. It imports the admin router lazily, so it works before Task 11 adds `routes_admin.py`.

**Interfaces:**
- Produces `ShareError(BrainSyncError)` with `.status: int`; `ShareManager(clock=time.monotonic)`: `active: bool`, `code: str`, `selections: dict[str, Selection]`, `start(selections) -> str`, `stop()`, `pair(code, device_id, name, ip) -> str`, `check(token) -> Peer | None`, `revoke(device_id)`, `peers() -> list[dict]`.
- Produces `AppContext(settings, state, vaults, share, conns)` with `tmp_file(suffix=".brainpack") -> Path`, `incoming(pack_id) -> Path`.
- Produces `build_share_router(ctx) -> APIRouter` (prefix `/share/v1`): `POST /pair`, `GET /vaults`, `GET /vaults/{vid}/manifest`, `POST /vaults/{vid}/pack`.
- Produces `PeerClient(address: str, client: httpx.AsyncClient | None = None)`: `pair(code, device_id, name) -> dict`, `vaults(token)`, `manifest(token, vid)`, `pull(token, vid, paths, dest: Path)`, `aclose()`; `PeerError(BrainSyncError)`.

- [ ] **Step 1: Write the failing test** `tests/test_sharing.py`

```python
import asyncio

import httpx
import pytest

from src.app import create_app
from src.config import Settings
from src.filters import Filter, Selection
from src.packager import read_manifest
from src.peer import PeerClient, PeerError
from src.sharing import ShareError, ShareManager
from tests.helpers import make_vault


def test_lockout_and_inactive():
    t = [0.0]
    m = ShareManager(clock=lambda: t[0])
    with pytest.raises(ShareError) as e:
        m.pair("X", "a" * 32, "n", "10.0.0.2")
    assert e.value.status == 404
    m.start({})
    for _ in range(5):
        with pytest.raises(ShareError) as e:
            m.pair("WRONG123", "a" * 32, "n", "10.0.0.2")
        assert e.value.status == 403
    with pytest.raises(ShareError) as e:
        m.pair(m.code, "a" * 32, "n", "10.0.0.2")
    assert e.value.status == 429
    t[0] = 61
    tok = m.pair(m.code, "a" * 32, "n", "10.0.0.2")
    assert m.check(tok).device_id == "a" * 32
    m.revoke("a" * 32)
    assert m.check(tok) is None


def test_share_pull_roundtrip(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", admin_password="pw", home=tmp_path / "home"))
    ctx = app.state.ctx
    v = make_vault(tmp_path / "v", {"Notes/a.md": "A\n", "Notes/p.md": "---\nprivate: true\n---\nP\n", "Other/o.md": "O\n"})
    vault = ctx.vaults.add("v", str(v))
    ctx.share.start({vault["id"]: Selection(filter=Filter(paths=["Notes/*"]))})

    async def run():
        t = httpx.ASGITransport(app=app, client=("127.0.0.1", 5))
        async with httpx.AsyncClient(transport=t, base_url="http://x") as hc:
            pc = PeerClient("127.0.0.1:26508", client=hc)
            tok = (await pc.pair(ctx.share.code, "b" * 32, "dev"))["token"]
            man = await pc.manifest(tok, vault["id"])
            assert [i["path"] for i in man["items"]] == ["Notes/a.md"]
            dest = tmp_path / "got.brainpack"
            await pc.pull(tok, vault["id"], ["Notes/a.md"], dest)
            assert [e["path"] for e in read_manifest(dest)["items"]] == ["Notes/a.md"]
            for bad in ("Notes/p.md", "Other/o.md"):
                with pytest.raises(PeerError):
                    await pc.pull(tok, vault["id"], [bad], tmp_path / "no.brainpack")
            assert not (tmp_path / "no.brainpack").exists()
        t = httpx.ASGITransport(app=app, client=("8.8.8.8", 5))
        async with httpx.AsyncClient(transport=t, base_url="http://x") as hc:
            r = await hc.post("/share/v1/pair", json={"code": ctx.share.code, "device_id": "c" * 32, "name": "x"})
            assert r.status_code == 403

    asyncio.run(run())


def test_peer_address_must_be_lan():
    for bad in ["8.8.8.8:26508", "example.com:26508", "10.0.0.2", "10.0.0.2:0", "10.0.0.2:x"]:
        with pytest.raises(PeerError):
            PeerClient(bad)
```

- [ ] **Step 2: Implement** `src/sharing.py`

```python
"""Live share state: pairing code, lockout, device tokens, per-vault selections."""
from __future__ import annotations

import hmac
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from src.errors import BrainSyncError
from src.filters import Selection

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_DEVICE = re.compile(r"[0-9a-f]{32}")
MAX_FAILS, LOCK_SECONDS = 5, 60


class ShareError(BrainSyncError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Peer:
    device_id: str
    name: str
    ip: str
    token: str
    since: str


class ShareManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.active = False
        self.code = ""
        self.selections: dict[str, Selection] = {}
        self._tokens: dict[str, Peer] = {}
        self._fails: dict[str, list[float]] = {}  # ip -> [count, locked_until]

    def start(self, selections: dict[str, Selection]) -> str:
        self.stop()
        self.active = True
        self.selections = dict(selections)
        self.code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        return self.code

    def stop(self) -> None:
        self.active, self.code = False, ""
        self.selections, self._tokens, self._fails = {}, {}, {}

    def pair(self, code: str, device_id: str, name: str, ip: str) -> str:
        if not self.active:
            raise ShareError(404, "not found")
        fail = self._fails.setdefault(ip, [0, 0.0])
        if self._clock() < fail[1]:
            raise ShareError(429, "too many tries")
        if not hmac.compare_digest(code.encode(), self.code.encode()):
            fail[0] += 1
            if fail[0] >= MAX_FAILS:
                fail[0], fail[1] = 0, self._clock() + LOCK_SECONDS
            raise ShareError(403, "bad code")
        if not _DEVICE.fullmatch(device_id or ""):
            raise ShareError(400, "bad device id")
        self.revoke(device_id)
        token = secrets.token_urlsafe(32)
        self._tokens[token] = Peer(device_id, re.sub(r"[^\w .-]", "_", name)[:40] or "device", ip, token,
                                   time.strftime("%Y-%m-%d %H:%M:%S"))
        self._fails.pop(ip, None)
        return token

    def check(self, token: str) -> Peer | None:
        return self._tokens.get(token) if self.active else None

    def revoke(self, device_id: str) -> None:
        self._tokens = {t: p for t, p in self._tokens.items() if p.device_id != device_id}

    def peers(self) -> list[dict]:
        return [{"device_id": p.device_id, "name": p.name, "ip": p.ip, "since": p.since}
                for p in self._tokens.values()]
```

- [ ] **Step 3: Implement** `src/ctx.py`

```python
"""Objects shared by the route modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from src.config import Settings
from src.sharing import ShareManager
from src.state import State
from src.vaults import VaultRegistry


@dataclass
class AppContext:
    settings: Settings
    state: State
    vaults: VaultRegistry
    share: ShareManager
    conns: dict = field(default_factory=dict)  # connection id -> peer connection info

    def tmp_file(self, suffix: str = ".brainpack") -> Path:
        d = self.settings.data_dir / "tmp"
        d.mkdir(parents=True, exist_ok=True)
        return d / (uuid4().hex + suffix)

    def incoming(self, pack_id: str) -> Path:
        d = self.settings.data_dir / "incoming"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{pack_id}.brainpack"
```

- [ ] **Step 4: Implement** `src/routes_share.py`

```python
"""Read-only LAN share API. Only active while sharing is on."""
from __future__ import annotations

import asyncio
import socket
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from src.ctx import AppContext
from src.filters import select
from src.packager import write_pack
from src.scanner import scan_vault
from src.security import is_lan_ip
from src.sharing import ShareError
from src.vaults import VaultError


class PairBody(BaseModel):
    code: str
    device_id: str
    name: str = ""


class PackBody(BaseModel):
    paths: list[str] = Field(max_length=5000)


def build_share_router(ctx: AppContext) -> APIRouter:
    r = APIRouter(prefix="/share/v1")

    def gate(request: Request) -> str:
        host = request.client.host if request.client else ""
        if not is_lan_ip(host):
            raise HTTPException(403, "not allowed")
        if not ctx.share.active:
            raise HTTPException(404, "not found")
        return host

    def peer_auth(host: str = Depends(gate), authorization: str = Header("")):
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        peer = ctx.share.check(token)
        if peer is None:
            raise HTTPException(401, "bad token")
        return peer

    async def shared(vid: str):
        sel = ctx.share.selections.get(vid)
        try:
            v = ctx.vaults.get(vid)
        except VaultError:
            v = None
        if sel is None or v is None:
            raise HTTPException(404, "not found")
        items = await asyncio.to_thread(scan_vault, Path(v["path"]), v["private_folders"])
        return v, {i.path: i for i in select(items, sel)}

    @r.post("/pair")
    async def pair(body: PairBody, host: str = Depends(gate)):
        try:
            token = ctx.share.pair(body.code, body.device_id, body.name, host)
        except ShareError as e:
            raise HTTPException(e.status, str(e)) from None
        ctx.state.audit("pair", device=body.device_id, ip=host)
        return {"token": token, "device_id": ctx.state.device_id(), "name": socket.gethostname()}

    @r.get("/vaults")
    async def vaults(peer=Depends(peer_auth)):
        out = []
        for vid in ctx.share.selections:
            try:
                out.append({"id": vid, "name": ctx.vaults.get(vid)["name"]})
            except VaultError:
                pass
        return {"vaults": out}

    @r.get("/vaults/{vid}/manifest")
    async def manifest(vid: str, peer=Depends(peer_auth)):
        v, items = await shared(vid)
        return {"device_id": ctx.state.device_id(), "vault_name": v["name"],
                "items": [i.to_dict() for i in items.values()]}

    @r.post("/vaults/{vid}/pack")
    async def pack(vid: str, body: PackBody, peer=Depends(peer_auth)):
        v, items = await shared(vid)
        if any(p not in items for p in body.paths):  # outside the selection looks like missing
            raise HTTPException(404, "not found")
        tmp = ctx.tmp_file()
        await asyncio.to_thread(write_pack, tmp, Path(v["path"]), [items[p] for p in body.paths],
                                device_id=ctx.state.device_id(), vault_name=v["name"])
        ctx.state.audit("pull", device=peer.device_id, name=peer.name, vault_id=vid, paths=body.paths[:200])
        return FileResponse(tmp, media_type="application/zip", filename="share.brainpack",
                            background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))

    return r
```

- [ ] **Step 5: Implement** `src/peer.py`

```python
"""Client for another BrainSync's share API."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from src.errors import BrainSyncError
from src.security import is_lan_ip


class PeerError(BrainSyncError):
    pass


class PeerClient:
    def __init__(self, address: str, client: httpx.AsyncClient | None = None):
        host, _, port = address.strip().partition(":")
        if not is_lan_ip(host) or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise PeerError("address must be a LAN IPv4 ip:port")
        self.base = f"http://{host}:{port}/share/v1"
        self._c = client or httpx.AsyncClient(timeout=httpx.Timeout(10, read=120))

    async def aclose(self) -> None:
        await self._c.aclose()

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code == 429:
            raise PeerError("too many tries, wait a minute")
        if r.status_code in (401, 403):
            raise PeerError("peer refused the code or token")
        if r.status_code != 200:
            raise PeerError("peer refused the request")

    async def _get(self, path: str, token: str) -> dict:
        try:
            r = await self._c.get(self.base + path, headers=self._headers(token))
        except httpx.HTTPError:
            raise PeerError("peer unreachable") from None
        self._check(r)
        return r.json()

    async def pair(self, code: str, device_id: str, name: str) -> dict:
        try:
            r = await self._c.post(self.base + "/pair", json={"code": code, "device_id": device_id, "name": name})
        except httpx.HTTPError:
            raise PeerError("peer unreachable") from None
        self._check(r)
        return r.json()

    async def vaults(self, token: str) -> dict:
        return await self._get("/vaults", token)

    async def manifest(self, token: str, vid: str) -> dict:
        return await self._get(f"/vaults/{vid}/manifest", token)

    async def pull(self, token: str, vid: str, paths: list[str], dest: Path) -> None:
        try:
            async with self._c.stream("POST", f"{self.base}/vaults/{vid}/pack", json={"paths": paths},
                                      headers=self._headers(token)) as r:
                self._check(r)
                f = await asyncio.to_thread(dest.open, "wb")
                try:
                    async for chunk in r.aiter_bytes():
                        await asyncio.to_thread(f.write, chunk)
                finally:
                    await asyncio.to_thread(f.close)
        except httpx.HTTPError:
            dest.unlink(missing_ok=True)
            raise PeerError("peer unreachable") from None
```

- [ ] **Step 6: Implement** `src/app.py` (the full file; admin router arrives in Task 11, so import it lazily)

```python
"""App factory: wiring only."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from src.config import Settings
from src.ctx import AppContext
from src.errors import BrainSyncError
from src.routes_share import build_share_router
from src.sharing import ShareManager
from src.state import State
from src.vaults import VaultRegistry

WEB = Path(__file__).resolve().parents[1] / "web"


def create_app(settings: Settings) -> FastAPI:
    if not settings.admin_password:
        raise RuntimeError("BRAINSYNC_ADMIN_PASSWORD is required")
    for sub in ("tmp", "incoming"):  # leftovers from a previous run
        shutil.rmtree(settings.data_dir / sub, ignore_errors=True)
    ctx = AppContext(settings, State(settings.data_dir), VaultRegistry(settings.data_dir / "vaults.json"),
                     ShareManager())
    app = FastAPI(title="BrainSync", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx

    @app.exception_handler(BrainSyncError)
    async def known_error(request: Request, exc: BrainSyncError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def page():
        return FileResponse(WEB / "index.html")

    app.include_router(build_share_router(ctx))
    try:
        from src.routes_admin import build_admin_router
    except ImportError:  # admin routes arrive in a later task
        pass
    else:
        app.include_router(build_admin_router(ctx))
    return app
```

- [ ] **Step 7: Run, expect PASS**

Run: `uv run pytest -q tests/test_sharing.py`

---

### Task 10: agent_setup.py

**Files:**
- Create: `src/agent_setup.py`, `tests/test_agent_setup.py`

**Interfaces:**
- Produces: `SetupError(BrainSyncError)`; `Op` dataclass `(label, target: Path | None = None, new: bytes | None = None, link_to: Path | None = None, cmd: list[str] | None = None, manual: str | None = None, before: bytes | None = None)`; `replace_block(text, body) -> str`; `merge_settings(existing: dict, snippet: dict, subs: dict, extra_dirs: list[str]) -> dict`; `insert_writable_roots(text: str, roots: list[str]) -> str | None`; `build_plan(vault: Path, *, home: Path, projects_root: str, codex: bool, others: list[Path], py: str = "py", codex_home: Path | None = None) -> list[Op]`; `render_diff(op: Op) -> str`; `apply_plan(ops, selected: set[int], backup_dir: Path) -> list[dict]` (each `{id, label, status: ok | unchanged | manual | error, detail}`); `verify(vault: Path, home: Path, py: str = "py") -> list[dict]` (each `{name, ok, detail}`).

- [ ] **Step 1: Write the failing test** `tests/test_agent_setup.py`

```python
import json
import tomllib

from src.agent_setup import BEGIN, apply_plan, build_plan, insert_writable_roots, merge_settings, replace_block
from tests.helpers import make_vault

SNIP = {"_comment": "x",
        "permissions": {"additionalDirectories": ["<VAULT_PATH>"], "deny": ["Read(**/.env)"]},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": '<PY> "<HOOKS_DIR>/ensure_daily.py"'}]}]}}


def test_merge_settings_idempotent():
    subs = {"<VAULT_PATH>": "D:/v", "<PY>": "py", "<HOOKS_DIR>": "C:/h"}
    existing = {"model": "x", "permissions": {"deny": ["Bash(rm -rf:*)"]},
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "other"}]}]}}
    once = merge_settings(existing, SNIP, subs, ["E:/other"])
    twice = merge_settings(once, SNIP, subs, ["E:/other"])
    assert once == twice and "_comment" not in once and once["model"] == "x"
    assert once["permissions"]["additionalDirectories"] == ["D:/v", "E:/other"]
    assert once["permissions"]["deny"] == ["Bash(rm -rf:*)", "Read(**/.env)"]
    assert len(once["hooks"]["SessionStart"]) == 2
    assert once["hooks"]["SessionStart"][1]["hooks"][0]["command"] == 'py "C:/h/ensure_daily.py"'


def test_block_idempotent():
    a = replace_block("keep\n", "body1")
    b = replace_block(a, "body2")
    assert replace_block(b, "body2") == b and "body1" not in b and b.startswith("keep\n") and b.count(BEGIN) == 1


def test_toml_roots():
    roots = lambda s: tomllib.loads(s)["sandbox_workspace_write"]["writable_roots"]  # noqa: E731
    assert roots(insert_writable_roots("", ["D:/Brain"])) == ["D:/Brain"]
    r = insert_writable_roots("[sandbox_workspace_write]\nnetwork_access = true\n", ["D:/Brain"])
    assert roots(r) == ["D:/Brain"] and tomllib.loads(r)["sandbox_workspace_write"]["network_access"] is True
    r = insert_writable_roots('[sandbox_workspace_write]\nwritable_roots = ["C:/a"]\n', ["D:/Brain"])
    assert roots(r) == ["C:/a", "D:/Brain"] and insert_writable_roots(r, ["D:/Brain"]) == r
    assert insert_writable_roots('[sandbox_workspace_write]\nwritable_roots = [\n "C:/a",\n]\n', ["D:/Brain"]) is None


def test_plan_apply_twice(tmp_path):
    v = make_vault(tmp_path / "v", {
        "_setup/hooks/validate_vault.py": "print(1)", "_setup/skills/s1/SKILL.md": "skill",
        "_setup/settings.snippet.json": json.dumps(SNIP),
        "_setup/user-CLAUDE.md.template": "vault <VAULT_PATH>", "_setup/user-AGENTS.md.template": "a <VAULT_PATH>"})
    home = tmp_path / "home"

    def run(n):
        ops = build_plan(v, home=home, projects_root="D:/p", codex=False, others=[], py="py")
        assert any(o.cmd for o in ops)  # git init planned: vault has no .git
        return apply_plan(ops, {i for i, o in enumerate(ops) if o.cmd is None}, tmp_path / f"bk{n}")

    first, second = run(1), run(2)
    assert all(r["status"] in ("ok", "unchanged") for r in first)
    assert all(r["status"] == "unchanged" for r in second)
    assert (home / ".claude/skills/s1/SKILL.md").read_text() == "skill"
    assert (home / ".claude/hooks/vault_path.txt").read_text().strip() == v.as_posix()
    assert "vault " + v.as_posix() in (home / ".claude/CLAUDE.md").read_text()
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_agent_setup.py`

- [ ] **Step 3: Implement** `src/agent_setup.py`

```python
"""Plan, apply and verify the Claude Code and Codex setup for a vault. Blocking: use asyncio.to_thread."""
from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from src.errors import BrainSyncError
from src.fsutil import write_atomic

BEGIN, END = "<!-- brainsync:begin -->", "<!-- brainsync:end -->"


class SetupError(BrainSyncError):
    pass


@dataclass
class Op:
    label: str
    target: Path | None = None
    new: bytes | None = None
    link_to: Path | None = None
    cmd: list[str] | None = None
    manual: str | None = None
    before: bytes | None = None


def replace_block(text: str, body: str) -> str:
    block = f"{BEGIN}\n{body.strip()}\n{END}"
    if BEGIN in text and END in text:
        s = text.index(BEGIN)
        return text[:s] + block + text[text.index(END, s) + len(END):]
    lead = "" if not text or text.endswith("\n") else "\n"
    return text + lead + ("\n" if text else "") + block + "\n"


def _sub(v, subs: dict):
    if isinstance(v, str):
        for k, x in subs.items():
            v = v.replace(k, x)
        return v
    if isinstance(v, list):
        return [_sub(i, subs) for i in v]
    if isinstance(v, dict):
        return {k: _sub(x, subs) for k, x in v.items() if k != "_comment"}
    return v


def _merge(dst, src):
    if isinstance(dst, dict) and isinstance(src, dict):
        for k, v in src.items():
            dst[k] = _merge(dst[k], v) if k in dst else v
    elif isinstance(dst, list) and isinstance(src, list):
        dst.extend(x for x in src if x not in dst)
    return dst


def merge_settings(existing: dict, snippet: dict, subs: dict, extra_dirs: list[str]) -> dict:
    out = _merge(copy.deepcopy(existing), _sub(snippet, subs))
    dirs = out.setdefault("permissions", {}).setdefault("additionalDirectories", [])
    dirs.extend(d for d in extra_dirs if d not in dirs)
    return out


def insert_writable_roots(text: str, roots: list[str]) -> str | None:
    """Add roots to [sandbox_workspace_write].writable_roots; None means edit by hand."""
    want = [r.replace("\\", "/") for r in roots]
    lines = text.splitlines(keepends=True)
    hdr = next((i for i, l in enumerate(lines) if l.strip() == "[sandbox_workspace_write]"), None)
    arr = lambda xs: "writable_roots = [" + ", ".join(json.dumps(x) for x in xs) + "]\n"  # noqa: E731
    if hdr is None:
        lead = "" if not text or text.endswith("\n") else "\n"
        new = text + lead + ("\n" if text else "") + "[sandbox_workspace_write]\n" + arr(want)
    else:
        end = next((i for i in range(hdr + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        idx = next((i for i in range(hdr + 1, end) if lines[i].split("=")[0].strip() == "writable_roots"), None)
        if idx is None:
            lines.insert(hdr + 1, arr(want))
        else:
            if "[" not in lines[idx] or "]" not in lines[idx]:
                return None
            try:
                have = tomllib.loads(lines[idx].strip())["writable_roots"]
            except (tomllib.TOMLDecodeError, KeyError):
                return None
            missing = [r for r in want if r not in have]
            if not missing:
                return text
            lines[idx] = arr(have + missing)
        new = "".join(lines)
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        return None
    return new


def build_plan(vault: Path, *, home: Path, projects_root: str, codex: bool, others: list[Path],
               py: str = "py", codex_home: Path | None = None) -> list[Op]:
    setup = vault / "_setup"
    if not setup.is_dir():
        raise SetupError("vault has no _setup folder")
    claude = home / ".claude"
    hooks = claude / "hooks"
    subs = {"<VAULT_PATH>": vault.as_posix(), "<PROJECTS_ROOT>": projects_root.replace("\\", "/"),
            "<PY>": py, "<HOOKS_DIR>": hooks.as_posix()}
    ops: list[Op] = []

    def put(label: str, target: Path, data: bytes) -> None:
        ops.append(Op(label, target, data, before=target.read_bytes() if target.is_file() else None))

    def block(label: str, target: Path, template: Path) -> None:
        old = target.read_text("utf-8") if target.is_file() else ""
        put(label, target, replace_block(old, _sub(template.read_text("utf-8"), subs)).encode("utf-8"))

    if (setup / "hooks").is_dir():
        for f in sorted((setup / "hooks").glob("*.py")):
            put(f"hook {f.name}", hooks / f.name, f.read_bytes())
    put("vault path", hooks / "vault_path.txt", (vault.as_posix() + "\n").encode())
    skills = sorted(p for p in (setup / "skills").iterdir() if p.is_dir()) if (setup / "skills").is_dir() else []
    for d in skills:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                rel = f.relative_to(d)
                put(f"skill {d.name}/{rel.as_posix()}", claude / "skills" / d.name / rel, f.read_bytes())
    sp = claude / "settings.json"
    try:
        existing = json.loads(sp.read_text("utf-8")) if sp.is_file() else {}
    except ValueError:
        existing = None
    if not isinstance(existing, dict):
        ops.append(Op("settings.json", sp, manual="settings.json is not valid JSON. Fix it by hand, then plan again."))
    else:
        snippet = json.loads((setup / "settings.snippet.json").read_text("utf-8"))
        merged = merge_settings(existing, snippet, subs, [o.as_posix() for o in others])
        put("settings.json", sp, (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    block("CLAUDE.md block", claude / "CLAUDE.md", setup / "user-CLAUDE.md.template")
    if codex:
        ch = codex_home or Path(os.environ.get("CODEX_HOME") or home / ".codex")
        block("Codex AGENTS.md block", ch / "AGENTS.md", setup / "user-AGENTS.md.template")
        for d in skills:
            ops.append(Op(f"Codex skill link {d.name}", ch / "skills" / d.name, link_to=claude / "skills" / d.name))
        cfg = ch / "config.toml"
        roots = [vault.as_posix(), *[o.as_posix() for o in others]]
        new = insert_writable_roots(cfg.read_text("utf-8") if cfg.is_file() else "", roots)
        if new is None:
            ops.append(Op("Codex config.toml", cfg, manual="Add these to [sandbox_workspace_write] writable_roots by hand: "
                          + ", ".join(roots)))
        else:
            put("Codex config.toml", cfg, new.encode("utf-8"))
    if not (vault / ".git").exists():
        ops.append(Op("git init", cmd=["git", "-C", str(vault), "init", "-b", "main"]))
    return ops


def render_diff(op: Op) -> str:
    if op.manual:
        return op.manual
    if op.cmd:
        return "run: " + " ".join(op.cmd)
    if op.link_to:
        return f"link {op.target} -> {op.link_to}"
    if op.before == op.new:
        return "no change"
    old = (op.before or b"").decode("utf-8", "replace").splitlines()
    new = (op.new or b"").decode("utf-8", "replace").splitlines()
    head = "new file\n" if op.before is None else ""
    return head + "\n".join(difflib.unified_diff(old, new, "before", "after", lineterm=""))


def apply_plan(ops: list[Op], selected: set[int], backup_dir: Path) -> list[dict]:
    results = []
    for i, op in enumerate(ops):
        if i not in selected:
            continue
        r = {"id": i, "label": op.label, "status": "ok", "detail": ""}
        try:
            if op.manual:
                r.update(status="manual", detail=op.manual)
            elif op.cmd:
                p = subprocess.run(op.cmd, capture_output=True, text=True, timeout=30)
                if p.returncode:
                    r.update(status="error", detail=(p.stderr or p.stdout).strip()[:200])
            elif op.link_to:
                if op.target.is_symlink() or op.target.exists():
                    same = op.target.resolve() == op.link_to.resolve()
                    r.update(status="unchanged" if same else "error",
                             detail="" if same else "something else is already there; remove it by hand")
                else:
                    op.target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.symlink(op.link_to, op.target, target_is_directory=True)
                    except OSError:
                        r.update(status="error", detail="symlink failed; turn on Windows Developer Mode")
            elif op.before == op.new:
                r["status"] = "unchanged"
            else:
                if op.target.is_file():
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(op.target, backup_dir / f"{i:03d}-{op.target.name}")
                write_atomic(op.target, op.new)
        except (OSError, subprocess.SubprocessError) as e:
            r.update(status="error", detail=type(e).__name__)
        results.append(r)
    return results


def verify(vault: Path, home: Path, py: str = "py") -> list[dict]:
    if not shutil.which(py):
        py = sys.executable
    hooks = home / ".claude" / "hooks"
    env = {**os.environ, "BRAIN_VAULT": str(vault)}
    checks = [
        ("validate_vault --all", [py, str(hooks / "validate_vault.py"), "--all"], lambda p: "vault OK" in p.stdout),
        ("ensure_daily", [py, str(hooks / "ensure_daily.py")], lambda p: p.returncode == 0),
        ("autocommit --dry-run", [py, str(hooks / "autocommit_vault.py"), "--dry-run"], lambda p: p.returncode == 0),
        ("git status clean", ["git", "-C", str(vault), "status", "--porcelain"],
         lambda p: p.returncode == 0 and not p.stdout.strip()),
    ]
    rows = []
    for name, cmd, ok in checks:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
            rows.append({"name": name, "ok": bool(ok(p)), "detail": (p.stdout or p.stderr).strip()[:200]})
        except (OSError, subprocess.SubprocessError) as e:
            rows.append({"name": name, "ok": False, "detail": type(e).__name__})
    skills = vault / "_setup" / "skills"
    names = [d.name for d in skills.iterdir() if d.is_dir()] if skills.is_dir() else []
    missing = [n for n in names if not (home / ".claude" / "skills" / n).is_dir()]
    rows.append({"name": "skills installed", "ok": not missing, "detail": ", ".join(missing)})
    return rows
```

- [ ] **Step 4: Run, expect PASS**

Run: `uv run pytest -q tests/test_agent_setup.py`

---

### Task 11: routes_admin.py, run.py, app test

**Files:**
- Create: `src/routes_admin.py`, `src/run.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: everything above. `app.py` (Task 9) already imports `build_admin_router(ctx)` from `src.routes_admin`.
- Produces: `build_admin_router(ctx) -> APIRouter` (prefix `/api`, every route needs header `X-Admin-Password`).
- Endpoints (these are what `web/index.html` calls in Task 12): `GET /api/vaults`; `POST /api/vaults {name,path,create}`; `DELETE /api/vaults/{vid}`; `PUT /api/vaults/{vid}/private-folders {folders}`; `POST /api/vaults/{vid}/active`; `POST /api/vaults/{vid}/select {selection}` returns `{all, selected}`; `POST /api/vaults/{vid}/export {selection}` returns the pack; `POST /api/import/upload?vault_id=` (raw body) returns the preview; `POST /api/import/apply {vault_id, pack_id, decisions}`; `POST /api/share/start {selections}`; `POST /api/share/stop`; `GET /api/share/status`; `DELETE /api/share/peers/{device_id}`; `POST /api/peer/connect {address, code}`; `GET /api/peer/{cid}/vaults`; `GET /api/peer/{cid}/vaults/{vid}/manifest`; `POST /api/peer/{cid}/vaults/{vid}/pull {paths, vault_id}` returns the preview; `DELETE /api/peer/{cid}`; `POST /api/setup/plan|apply|verify`; `GET /api/history`.
- Selection JSON in requests: `{filter:{paths,types,statuses,tags,created_from,created_to,modified_from,modified_to, changed_since_peer}, include, include_private, exclude, use_filter}`.

- [ ] **Step 1: Write the failing test** `tests/test_app.py`

```python
import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings
from tests.helpers import make_vault


def app_for(tmp_path):
    return create_app(Settings(data_dir=tmp_path / "data", admin_password="pw", home=tmp_path / "home"))


def test_refuses_without_password(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(Settings(data_dir=tmp_path / "d", admin_password="", home=tmp_path))


def test_auth_and_health(tmp_path):
    c = TestClient(app_for(tmp_path), client=("127.0.0.1", 1))
    assert c.get("/health").status_code == 200
    assert c.get("/api/vaults").status_code == 401
    assert c.get("/api/vaults", headers={"X-Admin-Password": "bad"}).status_code == 401
    assert c.get("/api/vaults", headers={"X-Admin-Password": "pw"}).status_code == 200
    assert c.get("/share/v1/vaults").status_code == 404  # sharing is off at start


def test_export_import_over_api(tmp_path):
    c = TestClient(app_for(tmp_path), client=("127.0.0.1", 1))
    h = {"X-Admin-Password": "pw"}
    src = make_vault(tmp_path / "src", {"Notes/a.md": "A\n", "Notes/p.md": "---\nprivate: true\n---\nP\n"})
    vid = c.post("/api/vaults", headers=h, json={"name": "s", "path": str(src), "create": False}).json()["id"]
    sel = {"selection": {"filter": {"paths": ["Notes/*"]}}}
    assert c.post(f"/api/vaults/{vid}/select", headers=h, json=sel).json()["selected"] == ["Notes/a.md"]
    pack = c.post(f"/api/vaults/{vid}/export", headers=h, json=sel).content
    dst = tmp_path / "dst"
    did = c.post("/api/vaults", headers=h, json={"name": "d", "path": str(dst), "create": True}).json()["id"]
    prev = c.post(f"/api/import/upload?vault_id={did}", headers=h, content=pack).json()
    row = next(r for r in prev["rows"] if r["path"] == "Notes/a.md")
    assert row["state"] == "new"
    res = c.post("/api/import/apply", headers=h, json={"vault_id": did, "pack_id": prev["pack_id"],
                                                        "decisions": {"Notes/a.md": {"action": "import"}}})
    assert res.json()["applied"] == ["Notes/a.md"] and (dst / "Notes/a.md").read_text() == "A\n"
    assert not (dst / "Notes/p.md").exists()
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run pytest -q tests/test_app.py`

- [ ] **Step 3: Implement** `src/routes_admin.py`

```python
"""Admin API. Every route needs the admin password header."""
from __future__ import annotations

import asyncio
import hmac
import re
import socket
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from src import agent_setup
from src.ctx import AppContext
from src.filters import Selection, select
from src.importer import apply_import, build_preview
from src.packager import read_manifest, write_pack
from src.peer import PeerClient, PeerError
from src.scanner import scan_vault

MAX_PACK = 2 * 1024 ** 3
_PACK_ID = re.compile(r"[0-9a-f]{32}")


class VaultIn(BaseModel):
    name: str
    path: str
    create: bool = False


class FoldersIn(BaseModel):
    folders: list[str]


class SelIn(BaseModel):
    selection: dict = {}


class ApplyIn(BaseModel):
    vault_id: str
    pack_id: str
    decisions: dict[str, dict] = {}


class ShareIn(BaseModel):
    selections: dict[str, dict]


class ConnectIn(BaseModel):
    address: str
    code: str


class PullIn(BaseModel):
    paths: list[str]
    vault_id: str


class SetupIn(BaseModel):
    vault_id: str
    projects_root: str
    codex: bool = False
    selected: list[int] = []


def build_admin_router(ctx: AppContext) -> APIRouter:
    def auth(x_admin_password: str = Header("")):
        if not hmac.compare_digest(x_admin_password.encode(), ctx.settings.admin_password.encode()):
            raise HTTPException(401, "wrong admin password")

    r = APIRouter(prefix="/api", dependencies=[Depends(auth)])

    def selection(vid: str, d: dict) -> Selection:
        sel = Selection.from_dict(d)
        peer = (d.get("filter") or {}).get("changed_since_peer")
        if peer:
            sel.filter.changed_since = ctx.state.load_base(vid, peer)
        return sel

    async def scan(vid: str):
        v = ctx.vaults.get(vid)
        return v, await asyncio.to_thread(scan_vault, Path(v["path"]), v["private_folders"])

    # ---- vaults
    @r.get("/vaults")
    async def vaults():
        return {"vaults": ctx.vaults.list()}

    @r.post("/vaults")
    async def add_vault(b: VaultIn):
        return await asyncio.to_thread(ctx.vaults.add, b.name, b.path, b.create)

    @r.delete("/vaults/{vid}")
    async def del_vault(vid: str):
        ctx.vaults.remove(vid)
        return {"ok": True}

    @r.put("/vaults/{vid}/private-folders")
    async def private_folders(vid: str, b: FoldersIn):
        ctx.vaults.set_private_folders(vid, b.folders)
        return {"ok": True}

    @r.post("/vaults/{vid}/active")
    async def active(vid: str):
        ctx.vaults.set_active(vid)
        return {"ok": True}

    @r.post("/vaults/{vid}/select")
    async def select_items(vid: str, b: SelIn):
        _, items = await scan(vid)
        chosen = select(items, selection(vid, b.selection))
        return {"all": [i.to_dict() for i in items], "selected": [i.path for i in chosen]}

    # ---- export
    @r.post("/vaults/{vid}/export")
    async def export(vid: str, b: SelIn):
        v, items = await scan(vid)
        chosen = select(items, selection(vid, b.selection))
        tmp = ctx.tmp_file()
        await asyncio.to_thread(write_pack, tmp, Path(v["path"]), chosen,
                                device_id=ctx.state.device_id(), vault_name=v["name"])
        ctx.state.audit("export", vault_id=vid, count=len(chosen))
        name = re.sub(r"[^\w.-]+", "_", v["name"])[:40] or "vault"
        return FileResponse(tmp, media_type="application/zip", filename=f"{name}.brainpack",
                            background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))

    # ---- import
    async def preview(vault_id: str, pack_id: str) -> dict:
        v = ctx.vaults.get(vault_id)
        dest = ctx.incoming(pack_id)
        try:
            m = await asyncio.to_thread(read_manifest, dest)
            rows = await asyncio.to_thread(build_preview, Path(v["path"]), dest, m, ctx.state, vault_id)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return {"pack_id": pack_id, "source_device_id": m["source_device_id"],
                "vault_name": m["vault_name"], "rows": rows}

    @r.post("/import/upload")
    async def upload(request: Request, vault_id: str):
        ctx.vaults.get(vault_id)
        pack_id = uuid4().hex
        dest, size = ctx.incoming(pack_id), 0
        f = await asyncio.to_thread(dest.open, "wb")
        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_PACK:
                    raise HTTPException(413, "pack too large")
                await asyncio.to_thread(f.write, chunk)
        except BaseException:
            await asyncio.to_thread(f.close)
            dest.unlink(missing_ok=True)
            raise
        await asyncio.to_thread(f.close)
        return await preview(vault_id, pack_id)

    @r.post("/import/apply")
    async def apply(b: ApplyIn):
        if not _PACK_ID.fullmatch(b.pack_id) or not ctx.incoming(b.pack_id).is_file():
            raise HTTPException(404, "pack not found")
        v, dest = ctx.vaults.get(b.vault_id), ctx.incoming(b.pack_id)
        m = await asyncio.to_thread(read_manifest, dest)
        res = await asyncio.to_thread(apply_import, Path(v["path"]), dest, m, ctx.state, b.vault_id,
                                      b.decisions, "peer")
        dest.unlink(missing_ok=True)
        return res

    # ---- share
    @r.post("/share/start")
    async def share_start(b: ShareIn):
        sels = {}
        for vid, d in b.selections.items():
            ctx.vaults.get(vid)
            sels[vid] = selection(vid, d)
        return {"code": ctx.share.start(sels)}

    @r.post("/share/stop")
    async def share_stop():
        ctx.share.stop()
        return {"ok": True}

    @r.get("/share/status")
    async def share_status():
        return {"active": ctx.share.active, "code": ctx.share.code, "peers": ctx.share.peers()}

    @r.delete("/share/peers/{device_id}")
    async def share_revoke(device_id: str):
        ctx.share.revoke(device_id)
        return {"ok": True}

    # ---- peer (this device pulls from another)
    def conn(cid: str) -> dict:
        c = ctx.conns.get(cid)
        if c is None:
            raise HTTPException(404, "not connected")
        return c

    @r.post("/peer/connect")
    async def peer_connect(b: ConnectIn):
        pc = PeerClient(b.address)
        try:
            info = await pc.pair(b.code, ctx.state.device_id(), socket.gethostname())
        except PeerError:
            await pc.aclose()
            raise
        cid = uuid4().hex
        ctx.conns[cid] = {"client": pc, "token": info["token"], "peer_id": info["device_id"], "name": info["name"]}
        return {"cid": cid, "name": info["name"]}

    @r.get("/peer/{cid}/vaults")
    async def peer_vaults(cid: str):
        c = conn(cid)
        return await c["client"].vaults(c["token"])

    @r.get("/peer/{cid}/vaults/{vid}/manifest")
    async def peer_manifest(cid: str, vid: str):
        c = conn(cid)
        return await c["client"].manifest(c["token"], vid)

    @r.post("/peer/{cid}/vaults/{vid}/pull")
    async def peer_pull(cid: str, vid: str, b: PullIn):
        c = conn(cid)
        ctx.vaults.get(b.vault_id)
        pack_id = uuid4().hex
        await c["client"].pull(c["token"], vid, b.paths, ctx.incoming(pack_id))
        return await preview(b.vault_id, pack_id)

    @r.delete("/peer/{cid}")
    async def peer_close(cid: str):
        c = ctx.conns.pop(cid, None)
        if c:
            await c["client"].aclose()
        return {"ok": True}

    # ---- agent setup
    def plan(b: SetupIn):
        v = ctx.vaults.get(b.vault_id)
        if not b.projects_root.strip():
            raise agent_setup.SetupError("projects root is required")
        others = [Path(x["path"]) for x in ctx.vaults.list() if x["id"] != b.vault_id]
        return agent_setup.build_plan(Path(v["path"]), home=ctx.settings.home, projects_root=b.projects_root,
                                      codex=b.codex, others=others)

    @r.post("/setup/plan")
    async def setup_plan(b: SetupIn):
        ops = await asyncio.to_thread(plan, b)
        return {"ops": [{"id": i, "label": o.label, "diff": agent_setup.render_diff(o),
                         "manual": bool(o.manual)} for i, o in enumerate(ops)]}

    @r.post("/setup/apply")
    async def setup_apply(b: SetupIn):
        ops = await asyncio.to_thread(plan, b)
        stamp = ctx.state.root / "backups" / ("setup-" + uuid4().hex[:8])
        res = await asyncio.to_thread(agent_setup.apply_plan, ops, set(b.selected), stamp)
        ctx.vaults.set_active(b.vault_id)
        ctx.state.audit("setup", vault_id=b.vault_id, count=len(res))
        return {"results": res}

    @r.post("/setup/verify")
    async def setup_verify(b: SetupIn):
        v = ctx.vaults.get(b.vault_id)
        return {"rows": await asyncio.to_thread(agent_setup.verify, Path(v["path"]), ctx.settings.home)}

    @r.get("/history")
    async def history():
        return {"audit": ctx.state.read_audit(), "backups": ctx.state.list_backups()}

    return r
```

- [ ] **Step 4: Implement** `src/run.py`

```python
"""Entry point: uv run python -m src.run [--dotenv]."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from src.app import create_app
from src.config import load_settings


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def main() -> None:
    if "--dotenv" in sys.argv:
        _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    s = load_settings()
    if not s.admin_password:
        sys.exit("BRAINSYNC_ADMIN_PASSWORD is required")
    uvicorn.run(create_app(s), host=s.bind, port=s.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run, expect PASS**

Run: `uv run pytest -q tests/test_app.py`

(`web/index.html` does not exist yet; `GET /` is not tested here and returns an error until Task 12.)

---

### Task 12: web/index.html

**Files:**
- Create: `web/index.html`

**Interfaces:**
- Consumes: the `/api/*` endpoints from Task 11. All URLs relative, no leading slash.

- [ ] **Step 1: Create the page.** Complete working version first (plain, light and dark CSS tokens). Write `web/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BrainSync</title>
<style>
:root{--bg:#f6f5f1;--fg:#1d2a22;--card:#fff;--line:#d9d6cb;--acc:#3f6b45;--acc-fg:#fff;--bad:#a33;--mute:#6b746d}
@media (prefers-color-scheme:dark){:root{--bg:#161a17;--fg:#e4e8e2;--card:#1f2521;--line:#34403a;--acc:#7fb283;--acc-fg:#10150f;--bad:#e07a7a;--mute:#9aa59c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0 8px 0 0}nav{display:flex;gap:4px;flex-wrap:wrap}
button,select,input,textarea{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:5px 9px}
button{cursor:pointer}button.on,button.pri{background:var(--acc);color:var(--acc-fg);border-color:var(--acc)}
main{max-width:1000px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}label{display:flex;gap:6px;align-items:center}
table{width:100%;border-collapse:collapse}td,th{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
pre{margin:4px 0;white-space:pre-wrap;word-break:break-word;font:12px/1.4 ui-monospace,Consolas,monospace;background:var(--bg);padding:6px;border-radius:6px;max-height:240px;overflow:auto}
.mute{color:var(--mute)}.bad{color:var(--bad)}.tag{border:1px solid var(--line);border-radius:10px;padding:0 6px;font-size:12px}
#msg{position:sticky;top:0;z-index:2;padding:8px 16px;display:none}#msg.err{display:block;background:var(--bad);color:#fff}#msg.ok{display:block;background:var(--acc);color:var(--acc-fg)}
input[type=text],input[type=password],textarea{min-width:200px}textarea{width:100%;min-height:60px}
</style>
</head>
<body>
<header><h1>BrainSync</h1><nav id="nav"></nav><span style="flex:1"></span><button id="lock">Admin password</button></header>
<div id="msg"></div>
<main id="view"></main>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const TABS=["Vaults","Export","Import","Share","Setup","History"];
let PW=sessionStorage.getItem("pw")||"",TAB="Vaults",VAULTS=[],PREV=null,CONN=null,MAN=null;
function say(t,bad){const m=$("#msg");m.textContent=t;m.className=bad?"err":"ok";clearTimeout(say.t);if(!bad)say.t=setTimeout(()=>m.className="",3000)}
async function api(path,{method="GET",body,raw,blob}={}){
  const h={"X-Admin-Password":PW},init={method,headers:h};
  if(raw){init.body=raw;h["Content-Type"]="application/octet-stream"}else if(body!==undefined){init.body=JSON.stringify(body);h["Content-Type"]="application/json"}
  const r=await fetch(path,init);
  if(!r.ok){let m=r.statusText;try{m=(await r.json()).detail||m}catch{}throw new Error(r.status===401?"Wrong admin password":m)}
  return blob?r.blob():r.json()}
const run=f=>async(...a)=>{try{await f(...a)}catch(e){say(e.message,true)}};
function vaultSelect(id,withPick){return`<select id="${id}">${VAULTS.map(v=>`<option value="${v.id}">${esc(v.name)}${v.active?" (active)":""}</option>`).join("")}</select>`}
async function loadVaults(){VAULTS=(await api("api/vaults")).vaults}
function nav(){$("#nav").innerHTML=TABS.map(t=>`<button class="${t==TAB?"on":""}" data-t="${t}">${t}</button>`).join("");
  document.querySelectorAll("#nav button").forEach(b=>b.onclick=()=>{TAB=b.dataset.t;show()})}
$("#lock").onclick=()=>{PW=prompt("Admin password")||"";sessionStorage.setItem("pw",PW);show()};
const show=run(async()=>{nav();if(!PW){$("#view").innerHTML='<p class="mute">Enter the admin password (top right).</p>';return}
  await loadVaults();await VIEWS[TAB]()});

/* ---------- Vaults ---------- */
const VIEWS={};
VIEWS.Vaults=async()=>{
  $("#view").innerHTML=`<div class="card"><b>Add a vault</b><div class="row"><input id="vn" type="text" placeholder="name"><input id="vp" type="text" placeholder="D:\\path\\to\\vault" size="40">
  <label><input type="checkbox" id="vc"> create (new or empty folder)</label><button class="pri" id="vadd">Add</button></div></div>
  ${VAULTS.map(v=>`<div class="card"><b>${esc(v.name)}</b> ${v.active?'<span class="tag">active</span>':""}<div class="mute">${esc(v.path)}</div>
  <div class="row"><label>Private folders (comma separated)<input type="text" data-pf="${v.id}" value="${esc(v.private_folders.join(", "))}"></label>
  <button data-save="${v.id}">Save</button><button data-act="${v.id}">Make active</button><button data-rm="${v.id}">Remove from list</button></div></div>`).join("")||'<p class="mute">No vaults yet.</p>'}`;
  $("#vadd").onclick=run(async()=>{await api("api/vaults",{method:"POST",body:{name:$("#vn").value,path:$("#vp").value,create:$("#vc").checked}});say("Vault added");show()});
  document.querySelectorAll("[data-save]").forEach(b=>b.onclick=run(async()=>{const f=document.querySelector(`[data-pf="${b.dataset.save}"]`).value.split(",");await api(`api/vaults/${b.dataset.save}/private-folders`,{method:"PUT",body:{folders:f}});say("Saved")}));
  document.querySelectorAll("[data-act]").forEach(b=>b.onclick=run(async()=>{await api(`api/vaults/${b.dataset.act}/active`,{method:"POST"});show()}));
  document.querySelectorAll("[data-rm]").forEach(b=>b.onclick=run(async()=>{if(confirm("Remove from the list? Files are not touched.")){await api(`api/vaults/${b.dataset.rm}`,{method:"DELETE"});show()}}))};

/* ---------- Selection UI (Export and Share) ---------- */
function filterHTML(p){return`<div class="row"><label>Paths (globs)<input type="text" id="${p}paths" placeholder="Notes/*, Projects/*" size="30"></label>
  <label>Types<input type="text" id="${p}types" size="12"></label><label>Status<input type="text" id="${p}status" size="12"></label><label>Tags<input type="text" id="${p}tags" size="12"></label></div>
  <div class="row"><label>Created from<input type="text" id="${p}cf" placeholder="YYYY-MM-DD" size="10"></label><label>to<input type="text" id="${p}ct" size="10"></label>
  <label>Modified from<input type="text" id="${p}mf" size="10"></label><label>to<input type="text" id="${p}mt" size="10"></label>
  <label>Changed since peer id<input type="text" id="${p}peer" size="14"></label><button data-starter="${p}">Starter preset</button></div>`}
const csv=id=>($(id).value||"").split(",").map(s=>s.trim()).filter(Boolean);
function readFilter(p){return{paths:csv(`#${p}paths`),types:csv(`#${p}types`),statuses:csv(`#${p}status`),tags:csv(`#${p}tags`),created_from:$(`#${p}cf`).value.trim(),created_to:$(`#${p}ct`).value.trim(),modified_from:$(`#${p}mf`).value.trim(),modified_to:$(`#${p}mt`).value.trim(),changed_since_peer:$(`#${p}peer`).value.trim()}}
function wireStarter(p){document.querySelectorAll(`[data-starter="${p}"]`).forEach(b=>b.onclick=()=>{$(`#${p}paths`).value="AGENTS.md, CLAUDE.md, Templates/*, .obsidian/*, _setup/*, 00 Dashboard.md"})}

/* ---------- Export ---------- */
let EXP=null;
VIEWS.Export=async()=>{
  $("#view").innerHTML=`<div class="card">${vaultSelect("xv")}${filterHTML("x")}<div class="row"><button id="xprev">Preview</button><button class="pri" id="xgo">Export ticked items</button></div></div><div id="xlist"></div>`;
  wireStarter("x");
  const list=()=>{if(!EXP)return;const priv=EXP.all.filter(i=>i.private),pub=EXP.all.filter(i=>!i.private),sel=new Set(EXP.selected);
    $("#xlist").innerHTML=`<div class="card"><b>${sel.size} of ${pub.length} shareable items selected</b><table>${pub.map(i=>`<tr><td><input type="checkbox" data-p="${esc(i.path)}" ${sel.has(i.path)?"checked":""}></td><td>${esc(i.path)}</td><td class="mute">${esc(i.type)} ${esc(i.status)}</td></tr>`).join("")}</table></div>
    <div class="card"><b>Private items</b> <span class="mute">off by default; tick one to include it</span><table>${priv.map(i=>`<tr><td><input type="checkbox" data-pp="${esc(i.path)}"></td><td>${esc(i.path)} <span class="tag">private</span></td></tr>`).join("")||'<tr><td class="mute">none</td></tr>'}</table></div>`};
  $("#xprev").onclick=run(async()=>{EXP=await api(`api/vaults/${$("#xv").value}/select`,{method:"POST",body:{selection:{filter:readFilter("x")}}});list()});
  $("#xgo").onclick=run(async()=>{if(!EXP)throw new Error("Preview first");
    const inc=[...document.querySelectorAll("[data-p]:checked")].map(e=>e.dataset.p),pr=[...document.querySelectorAll("[data-pp]:checked")].map(e=>e.dataset.pp);
    if(pr.length&&!confirm(`${pr.length} private item(s) will go into the pack. Continue?`))return;
    const blob=await api(`api/vaults/${$("#xv").value}/export`,{method:"POST",body:{selection:{use_filter:false,include:inc,include_private:pr}},blob:true});
    const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="vault.brainpack";a.click();say("Pack downloaded")})};

/* ---------- Import (file and peer) ---------- */
const OPTS={new:["import","skip"],theirs_only:["import","skip"],identical:["skip"],mine_only:["skip","theirs"],conflict:["merge","mine","theirs","both","skip"],no_base:["merge","mine","theirs","both","skip"]};
function previewHTML(P){return`<div class="card"><b>Preview</b> <span class="mute">from ${esc(P.vault_name)}</span><table>${P.rows.map((r,i)=>{
  let opts=[...OPTS[r.state]];if(r.binary)opts=opts.filter(o=>o!="merge");else if(/^(index|log)\.md$/.test(r.path))opts.push("union");
  const def=r.default=="unresolved"?"skip":r.default;
  const hunks=(r.hunks||[]).map((h,k)=>h.kind=="conflict"?{h,k}:null).filter(Boolean);let n=-1;
  const hv=(r.hunks||[]).filter(h=>h.kind=="conflict").map((h,j)=>`<div class="card"><div class="mute">Conflict ${j+1}</div><b>mine</b><pre>${esc(h.mine.join(""))}</pre><b>theirs</b><pre>${esc(h.theirs.join(""))}</pre>
   ${["mine","theirs","both"].map(c=>`<label><input type="radio" name="h${i}_${j}" value="${c}">${c}</label>`).join(" ")}</div>`).join("");
  return`<tr><td>${esc(r.path)} ${r.private?'<span class="tag">private</span>':""}${r.binary?'<span class="tag">binary</span>':""}<div class="mute">${r.state.replace("_"," ")}</div>${r.state=="conflict"||r.state=="no_base"?`<details><summary>${r.conflicts??"binary"} conflict(s)</summary>${hv}</details>`:""}</td>
  <td><select data-i="${i}">${opts.map(o=>`<option ${o==def?"selected":""}>${o}</option>`).join("")}</select></td></tr>`}).join("")}</table>
  <div class="row"><button class="pri" id="iapply">Apply</button></div></div>`}
function wirePreview(P,vault){$("#iapply").onclick=run(async()=>{const decisions={};
  P.rows.forEach((r,i)=>{const a=document.querySelector(`select[data-i="${i}"]`).value;if(a=="skip")return;const choices={};
    (r.hunks||[]).filter(h=>h.kind=="conflict").forEach((h,j)=>{const c=document.querySelector(`input[name="h${i}_${j}"]:checked`);if(c)choices[j]=c.value});
    decisions[r.path]={action:a,choices}});
  const res=await api("api/import/apply",{method:"POST",body:{vault_id:vault,pack_id:P.pack_id,decisions}});
  $("#ires").innerHTML=`<div class="card">Applied ${res.applied.length}, skipped ${res.skipped.length}${res.backup?`. Backup: ${esc(res.backup)}`:""}</div>`;say("Import done")})}
VIEWS.Import=async()=>{
  $("#view").innerHTML=`<div class="card"><b>From a pack file</b><div class="row">Into ${vaultSelect("iv")}<input type="file" id="ifile" accept=".brainpack"><button id="iup">Preview</button></div></div>
  <div class="card"><b>From a device on the LAN</b><div class="row"><input type="text" id="paddr" placeholder="192.168.1.20:26508"><input type="text" id="pcode" placeholder="pairing code" size="10"><button id="pcon">Connect</button></div><div id="pbox"></div></div><div id="ipreview"></div><div id="ires"></div>`;
  $("#iup").onclick=run(async()=>{const f=$("#ifile").files[0];if(!f)throw new Error("Choose a pack file");const vault=$("#iv").value;
    PREV=await api(`api/import/upload?vault_id=${vault}`,{method:"POST",raw:f});$("#ipreview").innerHTML=previewHTML(PREV);wirePreview(PREV,vault)});
  $("#pcon").onclick=run(async()=>{const c=await api("api/peer/connect",{method:"POST",body:{address:$("#paddr").value,code:$("#pcode").value}});CONN=c.cid;
    const v=(await api(`api/peer/${CONN}/vaults`)).vaults;$("#pbox").innerHTML=`<div class="row">Connected to ${esc(c.name)}. Their vault: <select id="pvs">${v.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select><button id="pls">List items</button></div><div id="plist"></div>`;
    $("#pls").onclick=run(async()=>{MAN=await api(`api/peer/${CONN}/vaults/${$("#pvs").value}/manifest`);
      $("#plist").innerHTML=`<table>${MAN.items.map(i=>`<tr><td><input type="checkbox" data-pl="${esc(i.path)}" checked></td><td>${esc(i.path)} ${i.private?'<span class="tag">private</span>':""}</td></tr>`).join("")}</table><button class="pri" id="ppull">Pull ticked into ${esc(VAULTS.find(v=>v.id==$("#iv").value)?.name||"")}</button>`;
      $("#ppull").onclick=run(async()=>{const paths=[...document.querySelectorAll("[data-pl]:checked")].map(e=>e.dataset.pl),vault=$("#iv").value;
        PREV=await api(`api/peer/${CONN}/vaults/${$("#pvs").value}/pull`,{method:"POST",body:{paths,vault_id:vault}});$("#ipreview").innerHTML=previewHTML(PREV);wirePreview(PREV,vault)})})})};

/* ---------- Share ---------- */
VIEWS.Share=async()=>{
  const st=await api("api/share/status");
  $("#view").innerHTML=st.active?`<div class="card"><b>Sharing is ON</b><p>Pairing code: <b style="font-size:22px;letter-spacing:3px">${esc(st.code)}</b></p>
  <div class="mute">Other device: Import tab, connect to this device's LAN IP and port, enter the code.</div>
  <table>${st.peers.map(p=>`<tr><td>${esc(p.name)} <span class="mute">${esc(p.ip)} · ${esc(p.since)}</span></td><td><button data-rev="${p.device_id}">Revoke</button></td></tr>`).join("")||'<tr><td class="mute">No device connected</td></tr>'}</table>
  <div class="row"><button id="sstop" class="pri">Stop sharing</button><button id="sref">Refresh</button></div></div>`
  :`<div class="card"><b>Choose what to share</b> <span class="mute">Private notes only by exact path below.</span>
  ${VAULTS.map(v=>`<div class="card"><label><input type="checkbox" data-sv="${v.id}"> <b>${esc(v.name)}</b></label>${filterHTML("s"+v.id)}
  <label>Private paths to share (one per line, exact)</label><textarea data-sp="${v.id}"></textarea></div>`).join("")||'<p class="mute">Add a vault first.</p>'}
  <button id="sstart" class="pri">Start sharing</button></div>`;
  VAULTS.forEach(v=>wireStarter("s"+v.id));
  const bind=(id,f)=>{const e=$(id);if(e)e.onclick=run(f)};
  bind("#sstart",async()=>{const selections={};
    document.querySelectorAll("[data-sv]:checked").forEach(c=>{const id=c.dataset.sv,pv=document.querySelector(`[data-sp="${id}"]`).value.split("\n").map(s=>s.trim()).filter(Boolean);
      selections[id]={filter:readFilter("s"+id),include_private:pv}});
    if(!Object.keys(selections).length)throw new Error("Tick at least one vault");
    if(Object.values(selections).some(s=>s.include_private.length)&&!confirm("Private notes will be visible to devices that pair. Continue?"))return;
    await api("api/share/start",{method:"POST",body:{selections}});show()});
  bind("#sstop",async()=>{await api("api/share/stop",{method:"POST"});show()});bind("#sref",async()=>show());
  document.querySelectorAll("[data-rev]").forEach(b=>b.onclick=run(async()=>{await api(`api/share/peers/${b.dataset.rev}`,{method:"DELETE"});show()}))};

/* ---------- Setup ---------- */
VIEWS.Setup=async()=>{
  $("#view").innerHTML=`<div class="card"><b>Agent setup</b><div class="row">${vaultSelect("sv")}<input type="text" id="sroot" placeholder="projects root, e.g. D:\\Code" size="30"><label><input type="checkbox" id="scodex"> also Codex</label>
  <button id="splan">Plan</button><button id="sver">Verify</button></div><div class="mute">Plan shows every change. Nothing is written until Apply.</div></div><div id="sbox"></div>`;
  const body=()=>({vault_id:$("#sv").value,projects_root:$("#sroot").value,codex:$("#scodex").checked,selected:[...document.querySelectorAll("[data-op]:checked")].map(e=>+e.dataset.op)});
  $("#splan").onclick=run(async()=>{const p=await api("api/setup/plan",{method:"POST",body:body()});
    $("#sbox").innerHTML=`<div class="card">${p.ops.map(o=>`<div><label><input type="checkbox" data-op="${o.id}" ${o.manual?"disabled":"checked"}> <b>${esc(o.label)}</b></label><pre>${esc(o.diff)}</pre></div>`).join("")}<button class="pri" id="sapply">Apply ticked</button></div>`;
    $("#sapply").onclick=run(async()=>{const r=await api("api/setup/apply",{method:"POST",body:body()});
      $("#sbox").innerHTML=`<div class="card"><table>${r.results.map(x=>`<tr><td>${esc(x.label)}</td><td class="${x.status=="error"?"bad":""}">${esc(x.status)}</td><td class="mute">${esc(x.detail)}</td></tr>`).join("")}</table><div class="mute">Restart Claude Code (and Codex) to load the settings.</div></div>`;say("Setup applied")})});
  $("#sver").onclick=run(async()=>{const r=await api("api/setup/verify",{method:"POST",body:body()});
    $("#sbox").innerHTML=`<div class="card"><table>${r.rows.map(x=>`<tr><td>${esc(x.name)}</td><td class="${x.ok?"":"bad"}">${x.ok?"pass":"FAIL"}</td><td class="mute">${esc(x.detail)}</td></tr>`).join("")}</table></div>`})};

/* ---------- History ---------- */
VIEWS.History=async()=>{const h=await api("api/history");
  $("#view").innerHTML=`<div class="card"><b>Backups</b> <span class="mute">in the service data folder, outside the vault</span><div>${h.backups.map(esc).join("<br>")||'<span class="mute">none</span>'}</div></div>
  <div class="card"><b>Audit log</b><table>${h.audit.map(a=>`<tr><td class="mute">${esc(a.ts)}</td><td>${esc(a.event)}</td><td class="mute">${esc(JSON.stringify(Object.fromEntries(Object.entries(a).filter(([k])=>k!="ts"&&k!="event"))))}</td></tr>`).join("")}</table></div>`};
show();
</script>
</body>
</html>
```

- [ ] **Step 2: Restyle.** Invoke the `moss-console-frontend` skill and restyle the page in that console style (CSS and markup classes only; keep every `id`, `data-*` attribute and the JS logic). No new test.

- [ ] **Step 3: Smoke check the served page.** Run:

```powershell
$env:BRAINSYNC_ADMIN_PASSWORD = "smoke"; $env:BRAINSYNC_DATA_DIR = "$env:TEMP\brainsync-smoke"
uv run python -c "from fastapi.testclient import TestClient; from src.app import create_app; from src.config import load_settings; c=TestClient(create_app(load_settings())); r=c.get('/'); print(r.status_code, '<title>BrainSync</title>' in r.text)"
```

Expected: `200 True`.

---

### Task 13: Docs and final check

**Files:**
- Create: `AGENTS.md`, `README.md`, `CHANGELOG.md`, `.env.example`

- [ ] **Step 1: Write the docs.**

`.env.example`:

```
# Required. The service refuses to start without it.
BRAINSYNC_ADMIN_PASSWORD=
# Optional
BRAINSYNC_PORT=26508
# Never set a loopback value: ServiceHub cannot reach a loopback-only service.
SERVICE_BIND=0.0.0.0
# BRAINSYNC_DATA_DIR=
# BRAINSYNC_HOME=
```

`AGENTS.md`:

````markdown
# BrainSync

Sets up and syncs Obsidian Brain vaults between Windows devices on one LAN: export/import packs with 3-way merge, live LAN share, and Claude Code + Codex setup. Port 26508 (workspace block 26500-26999). Design: `docs/superpowers/specs/2026-11-24-brainsync-design.md`.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv`, managed by uv)
- Install: `uv sync` (on this machine set `UV_CACHE_DIR=D:/User/.uv-cache`)
- Test: `uv run pytest -q`
- Run: `run.bat`, or `uv run python -m src.run --dotenv`

## Rules
- Native Windows service, no Docker. It writes to the vault and to `~/.claude` and `~/.codex`.
- Never read or print `.env`.
- `BRAINSYNC_ADMIN_PASSWORD` is required; without it the service refuses to start. `/health` is open. Admin API: header `X-Admin-Password`. Share API (`/share/v1`): LAN IPs only, pairing code, bearer token, read-only, only while sharing is on.
- ServiceHub: bind `0.0.0.0` (never default to loopback), UI at `/` only with relative URLs.
- Private notes (`private: true` frontmatter or a private folder) are shared only by exact path. A filter never selects one. Hard blocks (`.env*`, `secrets/`, keys, `.git/`, `.trash/`) never enter a pack or share. Unreadable frontmatter counts as private.
- Deletes never propagate. Overwritten files are backed up under `.data/backups/`, outside the vault.
- Every blocking call runs through `asyncio.to_thread`. Error messages never contain paths.
- Agent setup shows a plan first and writes nothing until Apply. It never adds a git remote or touches credentials.
- Behaviour changes update `README.md`, `AGENTS.md`, `CHANGELOG.md` and `.env.example` together.
````

`README.md`:

````markdown
# BrainSync

Set up and sync Obsidian "Brain" vaults between Windows devices on one LAN.

## Run

1. Copy `.env.example` to `.env`, set `BRAINSYNC_ADMIN_PASSWORD`.
2. `run.bat`. Open `http://localhost:26508/` and enter the admin password.

## What it does

- **Vaults:** register several vaults; one is "active" for the agent hooks.
- **Export:** filter by path, type, status, tags, dates or "changed since peer", tick items, download a `.brainpack`. Private notes are off unless you tick them.
- **Import:** from a pack file or from a device sharing on the LAN. Preview, then per-item action; conflicts open a per-hunk merge view. Old files are backed up outside the vault.
- **Share:** turn sharing on, give the 8-character code to the other device. Read-only, LAN only. Stops when you stop it or the service restarts.
- **Setup:** installs hooks, skills, settings and instruction templates for Claude Code and Codex from the vault's `_setup/` folder. Plan first, Apply second.

## New device

Install BrainSync, add an empty folder as a vault with "create", import a Starter pack (Starter preset in Export), then run Setup.

## Limits

Plain HTTP on the LAN (no TLS), no auto-discovery, Windows only. Codex symlinks need Windows Developer Mode.
````

`CHANGELOG.md`:

```markdown
# Changelog

## 0.1.0
- First version: vaults, export/import with 3-way merge, live LAN share, agent setup.
```

- [ ] **Step 2: Run the whole BrainSync suite once** (new project, small; this is the only multi-file run)

Run: `uv run pytest -q`
Expected: all tests in the 8 test files pass. If it runs longer than 2 minutes, stop and report.

- [ ] **Step 3: ServiceHub checklist (read, no run).** Confirm by reading: `routes`/`app.py` `GET /health` needs no auth; `config.py` default bind is `0.0.0.0`; `web/index.html` has no URL starting with `/` or `http`; port 26508 is not in any other project's files (grep `26508` in the workspace once).

- [ ] **Step 4: Final report.** Say what changed, which commands ran, and what was not run: no browser walkthrough of the UI, no second-device test over a real LAN, no Codex symlink or `config.toml` apply on the real home folder, no `Brain/Projects/BrainSync.md` project note (use the `project-sync` skill when asked).

---

## Self-review (spec coverage)

| Spec section | Task |
|---|---|
| Vaults, create exception | 6, 1 (spec patch) |
| Items, filters, Starter preset | 3, 4 |
| Privacy, hard blocks, fail closed, path safety | 2, 3, 4, 5, 9 |
| Pack format | 5 |
| Sync base, 3-way merge, classification, union, keep both, backups | 6, 7, 8 |
| Live share, pairing, lockout, read-only, 404 outside selection, LAN check, audit | 9, 11 |
| Admin password, refuse start | 11 (`create_app`, `run.py`) |
| Agent setup (plan, apply, marker blocks, settings merge, Codex, git init, verify, multi-vault) | 10, 11 |
| UI tabs | 12 |
| Layout, docs | 1, 13 |
| Testing list | tests in 2, 3, 4, 5, 7, 8, 9, 10, 11 |

Known shortcuts (each is a deliberate limit): the setup plan is rebuilt at Apply time, so a file changed between Plan and Apply is not re-shown; the typed peer address accepts only a LAN IPv4 `ip:port`; zip size caps are per file (100 MB) and per upload (2 GB); `config.toml` trailing comments on the `writable_roots` line are lost when it is rewritten.
