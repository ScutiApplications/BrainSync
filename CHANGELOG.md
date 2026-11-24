# Changelog

## 0.2.0
- Sync notes page and run drawer: Claude Code or Codex updates project notes with project-sync; Settings → Agents (allow, command, default agent, time limit, projects folder, after-sync commit/push). Agent setup can ask an agent to flag duplicate plan rows (advice only).
- Agent setup: new read-first step; Claude Code and Codex are two independent switches (ticked when found on this computer; Codex-only skips hooks, settings.json and CLAUDE.md). Panels always have a gap between them.
- Agent setup page redesigned as three steps (choose, review changes, done) with a plain list of what it installs; the projects folder starts from the vault's parent folder and has a folder picker.
- Logins persist across restarts (session hashes in the db, token kept in localStorage). Changing the password or logging out still ends them.
- First-run password prompt also works through this computer's own LAN address, not only localhost. Password field focus ring no longer shows a double border (also fixed in the Citadel admin apps).
- No `.env`: settings, vaults, sync bases, audit log, device id and the admin password hash live in one SQLite db. Settings apply at once; port and listen address at the next start.
- Admin password is set on first run from localhost, then login with a session token.
- UI rebuilt as a Vue admin app in the Citadel admin design.

## 0.1.0
- First version: vaults, export/import with 3-way merge, live LAN share, agent setup.
