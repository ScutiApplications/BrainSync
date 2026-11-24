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
