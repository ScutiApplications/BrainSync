@echo off
cd /d "%~dp0"
if not exist "web\dist\index.html" (
  pushd web
  call pnpm install && call pnpm build
  popd
)
uv run python -m src.run
