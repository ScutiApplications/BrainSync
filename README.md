# BrainSync

Set up and sync Obsidian "Brain" vaults between Windows devices on one LAN.

## Run

1. `run.bat`. The first run builds the UI (needs Node and pnpm).
2. Open `http://localhost:26508/` **on this computer** and set the admin password. Only localhost can set it; after that any device can log in.

There is no `.env` and no config file. Every setting is kept in the database (`.data/brainsync.db`) and is edited on the Settings page; a saved change applies at once, except Listen address and Port, which apply at the next start.

## What it does

- **Vaults:** register several vaults; one is "active" for the agent hooks.
- **Export:** filter by path, type, status, tags, dates or "changed since device", tick items, download a `.brainpack`. Private notes are off unless you tick them.
- **Import:** from a pack file or from a device sharing on the LAN. Preview, then per-note action; conflicts open a per-conflict merge view. Old files are backed up outside the vault.
- **Share:** turn sharing on, give the 8-character code to the other device. Read-only, LAN only. Off at every start.
- **Agent setup:** installs hooks, skills, settings and instruction text for Claude Code and Codex from the vault's `_setup/` folder. Plan first, Apply second.
- **History:** activity log and the backups made before files were replaced.

## New device

Install BrainSync, set the password, add an empty folder as a vault with "Create the folder", import a Starter pack (Starter preset on Export), then run Agent setup.

## Development

Backend: `uv run pytest -q`. UI: in `web/`, `pnpm exec vue-tsc -b` and `pnpm run build`. `pnpm dev` serves the UI on 26509 and proxies `/api` to a running backend.

## Limits

Plain HTTP on the LAN (no TLS), no auto-discovery, Windows only. Codex symlinks need Windows Developer Mode.
