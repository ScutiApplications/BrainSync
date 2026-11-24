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
