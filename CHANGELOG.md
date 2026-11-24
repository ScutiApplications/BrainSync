# Changelog

## 0.2.0
- No `.env`: settings, vaults, sync bases, audit log, device id and the admin password hash live in one SQLite db. Settings apply at once; port and listen address at the next start.
- Admin password is set on first run from localhost, then login with a session token.
- UI rebuilt as a Vue admin app in the Citadel admin design.

## 0.1.0
- First version: vaults, export/import with 3-way merge, live LAN share, agent setup.
