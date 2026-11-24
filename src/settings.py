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
    kind: str  # "int" | "str" | "bool" | "choice"
    default: Any
    restart: bool = False
    min: int | None = None
    max: int | None = None
    group: str = "Behaviour"
    choices: tuple[str, ...] = ()


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
    Option("projects_root", "Projects folder",
           "The folder that holds your code projects. The Sync page looks for git projects inside it. Empty uses the folder that holds the active vault.",
           "str", "", group="Agents"),
    Option("agent_claude_enabled", "Allow Claude Code",
           "Let BrainSync start Claude Code to sync project notes and to check the Agent setup plan for duplicates.",
           "bool", True, group="Agents"),
    Option("agent_claude_command", "Claude Code command",
           "Name or full path of the claude command. Empty finds it on the PATH. The file must be named claude.",
           "str", "", group="Agents"),
    Option("agent_codex_enabled", "Allow Codex",
           "Let BrainSync start Codex to sync project notes and to check the Agent setup plan for duplicates.",
           "bool", True, group="Agents"),
    Option("agent_codex_command", "Codex command",
           "Name or full path of the codex command. Empty finds it on the PATH. The file must be named codex.",
           "str", "", group="Agents"),
    Option("agent_default", "Default agent",
           "The agent a sync or a duplicate check uses unless you pick another one.",
           "choice", "claude", group="Agents", choices=("claude", "codex")),
    Option("agent_timeout_min", "Agent time limit (minutes)",
           "An agent run that takes longer is stopped.", "int", 10, min=1, max=120, group="Agents"),
    Option("sync_after", "After a project sync",
           "What BrainSync does with the vault when a sync finishes. Commit and push only push when the vault already has a remote; BrainSync never adds one.",
           "choice", "nothing", group="Agents", choices=("nothing", "commit", "commit_push")),
    Option("bind", "Listen address",
           "Network address the service listens on. Keep 0.0.0.0 so ServiceHub and other devices can reach it. "
           "Applies at the next start.", "str", "0.0.0.0", restart=True),
    Option("port", "Port",
           "TCP port of the service. Applies at the next start.", "int", 26508, restart=True, min=1024, max=65535),
)
_BY_KEY = {o.key: o for o in OPTIONS}


_COMMAND_NAMES = {"agent_claude_command": "claude", "agent_codex_command": "codex"}


def _check(opt: Option, value: Any) -> Any:
    if opt.kind == "bool":
        if not isinstance(value, bool):
            raise SettingError("value must be on or off")
        return value
    if opt.kind == "choice":
        if value not in opt.choices:
            raise SettingError("value must be one of: " + ", ".join(opt.choices))
        return value
    if opt.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingError("value must be a whole number")
        if (opt.min is not None and value < opt.min) or (opt.max is not None and value > opt.max):
            raise SettingError(f"value must be between {opt.min} and {opt.max}")
        return value
    if not isinstance(value, str) or len(value) > 260:
        raise SettingError("value must be text of at most 260 characters")
    value = value.strip()
    want = _COMMAND_NAMES.get(opt.key)
    if want and value:
        name = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        stem, _, ext = name.partition(".")
        if stem != want or ext not in ("", "exe", "cmd", "bat"):
            raise SettingError(f"the command file must be named {want}")
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
                     "restart": o.restart, "min": o.min, "max": o.max, "group": o.group,
                     "choices": list(o.choices), "value": vals.get(o.key, o.default),
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
