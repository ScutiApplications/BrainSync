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
    if not parts:
        return False
    if any(p in _BLOCK_PARTS for p in parts):
        return True
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


def is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def is_lan_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in n for n in _LAN)
