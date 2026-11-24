"""Admin password (scrypt hash in the db) and in-memory login sessions."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Callable

from src.db import Db
from src.errors import BrainSyncError
from src.lockout import Lockout

SESSION_SECONDS = 12 * 3600
MIN_PASSWORD = 8


class AuthError(BrainSyncError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


class Auth:
    def __init__(self, db: Db, limits: Callable[[], tuple[int, int]], clock: Callable[[], float] = time.monotonic):
        self._db = db
        self._clock = clock
        self._lockout = Lockout(limits, clock)
        self._sessions: dict[str, float] = {}

    def configured(self) -> bool:
        return bool(self._db.run("SELECT 1 FROM meta WHERE key = 'password'"))

    def _store(self, password: str) -> None:
        if not MIN_PASSWORD <= len(password) <= 128:
            raise AuthError(400, f"password must have {MIN_PASSWORD} to 128 characters")
        salt = os.urandom(16)
        value = f"scrypt${salt.hex()}${_hash(password, salt).hex()}"
        self._db.run("INSERT OR REPLACE INTO meta(key, value) VALUES ('password', ?)", (value,))

    def _verify(self, password: str) -> bool:
        rows = self._db.run("SELECT value FROM meta WHERE key = 'password'")
        if not rows:
            return False
        _, salt, digest = rows[0]["value"].split("$")
        return hmac.compare_digest(_hash(password, bytes.fromhex(salt)), bytes.fromhex(digest))

    def _new_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = self._clock() + SESSION_SECONDS
        return token

    def setup(self, password: str) -> str:
        if self.configured():
            raise AuthError(409, "password is already set")
        self._store(password)
        return self._new_session()

    def login(self, password: str, ip: str) -> str:
        if self._lockout.locked(ip):
            raise AuthError(429, "too many tries")
        if not self._verify(password):
            self._lockout.fail(ip)
            raise AuthError(401, "wrong password")
        self._lockout.clear(ip)
        return self._new_session()

    def check(self, token: str) -> bool:
        exp = self._sessions.get(token)
        if exp is None:
            return False
        if self._clock() >= exp:
            self._sessions.pop(token, None)
            return False
        return True

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def change_password(self, current: str, new: str, ip: str) -> str:
        if self._lockout.locked(ip):
            raise AuthError(429, "too many tries")
        if not self._verify(current):
            self._lockout.fail(ip)
            raise AuthError(401, "wrong password")
        self._store(new)
        self._sessions.clear()  # every other device must log in again
        return self._new_session()
