"""Lock a key (an IP) for a while after too many failures. Limits are read live."""
from __future__ import annotations

import time
from typing import Callable


class Lockout:
    def __init__(self, limits: Callable[[], tuple[int, int]], clock: Callable[[], float] = time.monotonic):
        self._limits = limits  # () -> (max_fails, lock_seconds)
        self._clock = clock
        self._fails: dict[str, list[float]] = {}  # key -> [count, locked_until]

    def locked(self, key: str) -> bool:
        return self._clock() < self._fails.get(key, [0, 0.0])[1]

    def fail(self, key: str) -> None:
        max_fails, seconds = self._limits()
        rec = self._fails.setdefault(key, [0, 0.0])
        rec[0] += 1
        if rec[0] >= max_fails:
            rec[0], rec[1] = 0, self._clock() + seconds

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._fails.clear()
        else:
            self._fails.pop(key, None)
