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
