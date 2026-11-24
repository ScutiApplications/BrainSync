"""Objects shared by the route modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from src.agents import JobManager
from src.auth import Auth
from src.config import Paths
from src.settings import LiveSettings
from src.sharing import ShareManager
from src.state import State
from src.vaults import VaultRegistry


@dataclass
class AppContext:
    paths: Paths
    state: State
    settings: LiveSettings
    auth: Auth
    vaults: VaultRegistry
    share: ShareManager
    jobs: JobManager = field(default_factory=JobManager)
    conns: dict = field(default_factory=dict)  # connection id -> peer connection info

    def tmp_file(self, suffix: str = ".brainpack") -> Path:
        d = self.paths.data_dir / "tmp"
        d.mkdir(parents=True, exist_ok=True)
        return d / (uuid4().hex + suffix)

    def incoming(self, pack_id: str) -> Path:
        d = self.paths.data_dir / "incoming"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{pack_id}.brainpack"
