"""App factory: wiring only."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from src.auth import Auth
from src.config import Paths
from src.ctx import AppContext
from src.db import Db
from src.errors import BrainSyncError
from src.routes_admin import build_admin_router
from src.routes_auth import build_auth_router
from src.routes_share import build_share_router
from src.settings import LiveSettings
from src.sharing import ShareManager
from src.state import State
from src.vaults import VaultRegistry

DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def create_app(paths: Paths) -> FastAPI:
    for sub in ("tmp", "incoming"):  # leftovers from a previous run
        shutil.rmtree(paths.data_dir / sub, ignore_errors=True)
    db = Db(paths.data_dir / "brainsync.db")
    settings = LiveSettings(db)
    ctx = AppContext(paths, State(paths.data_dir, db), settings, Auth(db, settings.limits), VaultRegistry(db),
                     ShareManager(limits=settings.limits))
    app = FastAPI(title="BrainSync", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx

    @app.exception_handler(BrainSyncError)
    async def known_error(request: Request, exc: BrainSyncError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(build_auth_router(ctx))
    app.include_router(build_share_router(ctx))
    app.include_router(build_admin_router(ctx))
    if (DIST / "index.html").is_file():  # mounted last: API routes win
        app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
    else:
        @app.get("/")
        async def no_ui():
            return PlainTextResponse("UI not built. Run: pnpm install && pnpm build (in web/)", status_code=503)
    return app
