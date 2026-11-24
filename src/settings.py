"""Run-time settings kept in the db. A change applies at once; `restart` options at the next start."""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
from dataclasses import dataclass
from typing import Any, Callable

from src.db import Db
from src.errors import BrainSyncError


class SettingError(BrainSyncError):
    pass


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    help: str
    kind: str  # "int" | "str"
    default: Any
    restart: bool = False
    min: int | None = None
    max: int | None = None


OPTIONS: tuple[Option, ...] = (
    Option("device_name", "Device name",
           "How this device is shown to other devices when it pairs. Empty uses the computer name.",
           "str", ""),
    Option("max_pack_mb", "Largest pack (MB)",
           "Biggest .brainpack file this device accepts when you upload one. Larger uploads are refused.",
           "int", 2048, min=1, max=20480),
    Option("share_max_fails", "Wrong codes before lock",
           "How many wrong pairing codes or admin passwords one address may try before it is locked.",
           "int", 5, min=1, max=50),
    Option("share_lock_seconds", "Lock time (seconds)",
           "How long an address stays locked after too many wrong tries.",
           "int", 60, min=5, max=3600),
    Option("bind", "Listen address",
           "Network address the service listens on. Keep 0.0.0.0 so ServiceHub and other devices can reach it. "
           "Applies at the next start.", "str", "0.0.0.0", restart=True),
    Option("port", "Port",
           "TCP port of the service. Applies at the next start.", "int", 26508, restart=True, min=1024, max=65535),
)
_BY_KEY = {o.key: o for o in OPTIONS}


def _check(opt: Option, value: Any) -> Any:
    if opt.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingError("value must be a whole number")
        if (opt.min is not None and value < opt.min) or (opt.max is not None and value > opt.max):
            raise SettingError(f"value must be between {opt.min} and {opt.max}")
        return value
    if not isinstance(value, str) or len(value) > 64:
        raise SettingError("value must be text of at most 64 characters")
    value = value.strip()
    if opt.key == "bind":
        try:
            ipaddress.ip_address(value)
        except ValueError:
            raise SettingError("value must be an IP address") from None
    return value


class LiveSettings:
    def __init__(self, db: Db):
        self._db = db
        self._lock = threading.RLock()
        self._values: dict[str, Any] | None = None
        self._listeners: list[Callable[[str, Any], None]] = []

    def _load(self) -> dict[str, Any]:
        if self._values is None:
            self._values = {r["key"]: json.loads(r["value"]) for r in self._db.run("SELECT key, value FROM settings")}
        return self._values

    def get(self, key: str) -> Any:
        opt = _BY_KEY[key]
        with self._lock:
            return self._load().get(key, opt.default)

    def device_name(self) -> str:
        return self.get("device_name") or socket.gethostname()

    def limits(self) -> tuple[int, int]:
        return self.get("share_max_fails"), self.get("share_lock_seconds")

    def snapshot(self) -> list[dict]:
        with self._lock:
            vals = self._load()
            return [{"key": o.key, "label": o.label, "help": o.help, "kind": o.kind, "default": o.default,
                     "restart": o.restart, "min": o.min, "max": o.max, "value": vals.get(o.key, o.default),
                     "changed": o.key in vals} for o in OPTIONS]

    def set(self, key: str, value: Any) -> Any:
        opt = _BY_KEY.get(key)
        if opt is None:
            raise SettingError("unknown setting")
        value = _check(opt, value)
        with self._lock:
            self._db.run("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
            self._load()[key] = value
        self._notify(key, value)
        return value

    def reset(self, key: str) -> Any:
        opt = _BY_KEY.get(key)
        if opt is None:
            raise SettingError("unknown setting")
        with self._lock:
            self._db.run("DELETE FROM settings WHERE key = ?", (key,))
            self._load().pop(key, None)
        self._notify(key, opt.default)
        return opt.default

    def on_change(self, cb: Callable[[str, Any], None]) -> None:
        self._listeners.append(cb)

    def _notify(self, key: str, value: Any) -> None:
        for cb in self._listeners:
            cb(key, value)
