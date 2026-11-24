# Changelog

## 0.2.0
- Logins persist across restarts (session hashes in the db, token kept in localStorage). Changing the password or logging out still ends them.
- First-run password prompt also works through this computer's own LAN address, not only localhost. Password field focus ring no longer shows a double border (also fixed in the Citadel admin apps).
- No `.env`: settings, vaults, sync bases, audit log, device id and the admin password hash live in one SQLite db. Settings apply at once; port and listen address at the next start.
- Admin password is set on first run from localhost, then login with a session token.
- UI rebuilt as a Vue admin app in the Citadel admin design.

## 0.1.0
- First version: vaults, export/import with 3-way merge, live LAN share, agent setup.
