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
from src.lockout import Lockout

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_DEVICE = re.compile(r"[0-9a-f]{32}")


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
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 limits: Callable[[], tuple[int, int]] = lambda: (5, 60)):
        self._lockout = Lockout(limits, clock)
        self.active = False
        self.code = ""
        self.selections: dict[str, Selection] = {}
        self._tokens: dict[str, Peer] = {}

    def start(self, selections: dict[str, Selection]) -> str:
        self.stop()
        self.active = True
        self.selections = dict(selections)
        self.code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        return self.code

    def stop(self) -> None:
        self.active, self.code = False, ""
        self.selections, self._tokens = {}, {}
        self._lockout.clear()

    def pair(self, code: str, device_id: str, name: str, ip: str) -> str:
        if not self.active:
            raise ShareError(404, "not found")
        if self._lockout.locked(ip):
            raise ShareError(429, "too many tries")
        if not hmac.compare_digest(code.encode(), self.code.encode()):
            self._lockout.fail(ip)
            raise ShareError(403, "bad code")
        if not _DEVICE.fullmatch(device_id or ""):
            raise ShareError(400, "bad device id")
        self.revoke(device_id)
        token = secrets.token_urlsafe(32)
        self._tokens[token] = Peer(device_id, re.sub(r"[^\w .-]", "_", name)[:40] or "device", ip, token,
                                   time.strftime("%Y-%m-%d %H:%M:%S"))
        self._lockout.clear(ip)
        return token

    def check(self, token: str) -> Peer | None:
        return self._tokens.get(token) if self.active else None

    def revoke(self, device_id: str) -> None:
        self._tokens = {t: p for t, p in self._tokens.items() if p.device_id != device_id}

    def peers(self) -> list[dict]:
        return [{"device_id": p.device_id, "name": p.name, "ip": p.ip, "since": p.since}
                for p in self._tokens.values()]
