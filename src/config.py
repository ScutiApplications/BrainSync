"""Where the service keeps its files. Everything else lives in the db (see settings.py)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    data_dir: Path  # brainsync.db, blobs, backups, temporary uploads
    home: Path  # user home that holds .claude and .codex


def default_paths() -> Paths:
    return Paths(data_dir=Path(__file__).resolve().parents[1] / ".data", home=Path.home())
