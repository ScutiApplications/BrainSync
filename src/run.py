"""Entry point: uv run python -m src.run. All settings live in the db and are edited in the UI."""
from __future__ import annotations

import uvicorn

from src.app import create_app
from src.config import default_paths


def main() -> None:
    app = create_app(default_paths())
    s = app.state.ctx.settings
    uvicorn.run(app, host=s.get("bind"), port=s.get("port"))


if __name__ == "__main__":
    main()
