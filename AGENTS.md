# BrainSync

Sets up and syncs Obsidian Brain vaults between Windows devices on one LAN: export/import packs with 3-way merge, live LAN share, and Claude Code + Codex setup. Port 26508 (workspace block 26500-26999). Design: `docs/superpowers/specs/2026-11-24-brainsync-design.md` (revision 2 at the end).

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands
- Backend (from this folder, venv `.venv`, uv; on this machine set `UV_CACHE_DIR=D:/User/.uv-cache`): `uv sync`, `uv run pytest -q`.
- UI (from `web/`, pnpm): `pnpm install`, `pnpm exec vue-tsc -b`, `pnpm test`, `pnpm run build` (writes `web/dist`, which the backend serves).
- Run: `run.bat` (builds the UI first if `web/dist` is missing), or `uv run python -m src.run`.

## Rules
- Native Windows service, no Docker. It writes to the vault and to `~/.claude` and `~/.codex`.
- **No `.env`, no config file.** Everything that changes at run time is in one SQLite file, `.data/brainsync.db` (`src/db.py`): settings, vaults, sync bases, audit log, device id, password hash. Blobs and backups stay as files in `.data/`. A setting is added in `src/settings.py` `OPTIONS` and read with `ctx.settings.get(key)` on every use, never cached in a module, so a saved change applies at once. Only `restart=True` options (`bind`, `port`) wait for the next start.
- **First run:** no password exists. Only a request from localhost may set it (`POST /api/auth/setup`); other devices are refused. After that, `POST /api/auth/login` returns a session token (header `Authorization: Bearer`, 12 h; only its hash is stored in the db `sessions` table, so logins survive a restart; the browser keeps it in localStorage). `/health` is open.
- Share API (`/share/v1`): LAN IPs only, pairing code, bearer token, read-only, only while sharing is on.
- ServiceHub: bind `0.0.0.0` (never default to loopback), UI at `/` with relative URLs only, hash router.
- Private notes (`private: true` frontmatter or a private folder) are shared only by exact path. A filter never selects one. Hard blocks (`.env*`, `secrets/`, keys, `.git/`, `.trash/`) never enter a pack or share. Unreadable frontmatter counts as private.
- Deletes never propagate. Overwritten files are backed up under `.data/backups/`, outside the vault.
- Every blocking call in a request runs through `asyncio.to_thread`. Error messages never contain paths.
- Agent setup shows a plan first and writes nothing until Apply. It never adds a git remote or touches credentials.
- UI follows the Citadel admin design: `web/src` holds copies of the Citadel admin components (`PageLayout`, `RecordDrawer`, `ConfirmModal`, `ToggleSwitch`, `PanelHelp`, `FieldLabel`, `ActionMessage`, `SettingsPanel`, `AdminSearch`, `DraftActions`, `ThemeSelect`, `style.css` tokens). Read `Citadel/.agents/skills/ember-frontend-design/SKILL.md` before UI work. Rules from there: anything opened from a panel is a drawer, only `ConfirmModal` is a modal; no checkboxes (use `ToggleSwitch`); every panel header has a `PanelHelp`; every setting has a `FieldLabel` help; radius and colour only through tokens; never reduced-motion code. Components are copied, not shared: a fix to a copy is applied to the Citadel apps too.
- Agents (`src/agents.py`, `src/routes_sync.py`): BrainSync starts `claude -p` or `codex exec` headless for project-note syncs (`sync_prompt`, vault as working folder, project code read-only by prompt) and read-only plan checks (`check_prompt`, advice only, never applied automatically). One job at a time, started only from this computer, output polled at `/api/jobs/{id}`. The command settings must name `claude` or `codex`. Agent settings are in `OPTIONS` group "Agents".
- Behaviour changes update `README.md`, `AGENTS.md` and `CHANGELOG.md` together.
