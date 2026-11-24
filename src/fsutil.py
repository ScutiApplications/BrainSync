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
