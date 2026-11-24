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
