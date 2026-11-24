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
