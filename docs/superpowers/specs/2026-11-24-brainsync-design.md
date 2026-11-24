# BrainSync design

Date: 2026-11-24. Status: draft for review.

## Purpose

BrainSync sets up and syncs Obsidian "Brain" vaults (modeled on `Brain/` in the Programming workspace) between Windows devices on one LAN. It does three jobs:

1. **Export / import.** Pack chosen parts of a vault into a `.brainpack` file and import it on another device, with a preview and a merge/diff view.
2. **Live share.** While sharing is on, another BrainSync instance on the LAN can browse the shared items and pull the ones it picks.
3. **Agent setup.** Install the Claude Code and Codex configuration (hooks, skills, settings, instruction templates) so both agents can use a vault on a new device.

It supports several vaults at once.

## Decisions

| Topic | Decision |
|---|---|
| Location | `D:\User\Documents\Programming\Applications\BrainSync`, own git repo, own `AGENTS.md` |
| Port | 26508 (next free in the `26500-26999` block; re-check at build time) |
| Stack | Python, uv, FastAPI, async. Runs natively on Windows with `run.bat`. No Docker |
| Network | Same LAN only. Plain HTTP |
| OS | Windows only |
| Private notes | Shareable only when the sharer explicitly ticks them |
| Conflicts | 3-way merge with a merge/diff view |
| ServiceHub | Binds `0.0.0.0`, `GET /health` returns 200 without auth, UI uses relative URLs only, unique host port |

## Vaults

- The registry is `.data/vaults.json` in the service state folder: `{id, name, path, private_folders}` per vault.
- Registering a vault checks that the folder has `.obsidian/` and `AGENTS.md`. Registering never modifies the vault. The one exception is "create": for a missing or empty folder, BrainSync creates `.obsidian/` so a Starter pack can be imported into it.
- Exactly one vault is **active** for agent setup (see Agent setup).

## Items and filters

The scanner walks a vault and keeps the files that the vault's own `.gitignore` whitelist allows: `*.md`, `*.canvas`, `*.base`, images, PDFs, `.obsidian/**` minus workspace state, and `_setup/**`.

Each item records path, sha256, size, mtime and, from frontmatter, `type`, `status`, `tags`, `created`.

Filters (combinable, each narrows the selection):

- folder or path glob
- `type` and `status`
- tags
- created or modified date range
- changed since last sync with peer X

Preset: **Starter**. It selects only structure: `AGENTS.md`, `CLAUDE.md`, `Templates/`, `.obsidian/`, `_setup/`, `00 Dashboard.md`. Use it to bootstrap a fresh vault.

## Privacy

- A note is private when its frontmatter has `private: true` or it sits in a folder listed in the vault's `private_folders`.
- Private items are off by default in every export and share. They appear in a separate group. They can be included only by ticking the **exact path**. A filter never selects a private item.
- **Hard blocks, no override:** `.env*`, `secrets/`, `.secrets/`, key files (`*.pem`, `*.key`, `*.pfx`, `*.p12`, `id_rsa*`, `id_ed25519*`), `.git/`, `.trash/`. They never enter a pack or a share.
- The sharer decides. An importer cannot widen what a sharer allows.
- Fail closed: if frontmatter cannot be read, the note counts as private.
- Imported paths are refused when absolute, when they contain `..`, or when they resolve outside the target vault. The pack is rejected as a whole, with an error that names no path.

## Pack format

`.brainpack` is a zip containing `manifest.json` and `files/<path>`.

- Manifest: `format`, `pack_id`, `source_device_id`, `vault_name`, `created`, and per item `path`, `sha256`, `size`, `mtime`, `private`.
- Zip creation and extraction run in worker threads and stream; nothing builds the whole pack in memory.
- Import checks every sha256 against the manifest. One mismatch rejects the pack.

## Sync base and 3-way merge

- Each install has a stable `device_id` (generated once, stored in the state folder).
- `.data/blobs/<sha256>` is a content-addressed store of file contents.
- `.data/bases/<vault_id>/<peer_device_id>.json` maps path to the sha last agreed with that peer.
- After a successful import (file or live pull), the base is updated for the items that moved. Export cannot know the receiving device, so it records nothing.
- The base lives in the state folder, never in the vault.

Import classifies each incoming item against mine and the base. Line endings are ignored for the comparison.

| State | Meaning | Default |
|---|---|---|
| new | not in my vault | import |
| identical | same content | skip |
| theirs-only | mine equals base | import automatically |
| mine-only | theirs equals base | keep mine |
| conflict | both changed | open merge view |
| no base | first sync, files differ | 2-way diff |

Items missing from the incoming pack are ignored. **Deletes never propagate.** The vault rule is to move to `Archive/`, never delete.

Merge view:

- Text files use the `merge3` library. Each conflict hunk shows mine and theirs side by side. Per hunk: mine, theirs, both, or edit by hand. A result pane shows the merged file. Apply stays disabled while unresolved conflicts remain.
- `index.md` and `log.md` offer a "union lines" shortcut, because they are a catalog and an append-only log.
- Binary files (images, PDFs) cannot merge. Choose mine, theirs, or keep both. The incoming copy is saved as `name (from <device>).ext`.

Apply:

- Write to a temp file, then replace atomically.
- Before overwriting, copy the old file to `.data/backups/<timestamp>/`, outside the vault.
- The vault's own SessionEnd hook commits and pushes the changes as usual.
- `validate_vault.py` may run on imported notes. It only warns and never blocks.

## Live share

Sharing is off at every start. Nothing persists across restarts: not the selection, not the code.

1. The sharer turns Share on, picks vaults and a selection (filters plus ticked items), and the service shows an 8-character random **pairing code**.
2. The peer enters the sharer's LAN IPv4 `ip:port` (hostnames and non-LAN addresses are refused) and the code. `POST /share/v1/pair` returns a session token for that device.
3. Later calls carry the token as a bearer header.
4. The sharer sees connected devices (name and id) and can revoke any of them. Revoking invalidates the token at once.
5. The share ends when the sharer turns it off or the service stops.

Pairing: constant-time code compare; 5 wrong tries lock pairing for 60 s per client IP. Recent peers are remembered (address and name only, never the code or token).

Endpoints (read-only; a peer can pull and cannot push):

- `GET /share/v1/vaults` lists shared vaults.
- `GET /share/v1/vaults/{id}/manifest` returns the manifest of the shared selection only.
- `POST /share/v1/vaults/{id}/pack` takes a list of paths and streams a `.brainpack`.
- A path outside the selection returns 404, the same as a missing file.

The peer then runs the normal import preview, merge and apply, using the sharer's `device_id` as the sync peer.

Security:

- Share routes refuse a client IP outside private ranges (`10/8`, `172.16/12`, `192.168/16`, link-local, loopback).
- The admin UI and API can read and write the vault, so they need `BRAINSYNC_ADMIN_PASSWORD` (header `X-Admin-Password`). **With no password set the service refuses to start.** `/health` stays open. Share tokens never grant access to admin routes.
- An audit log in the state folder records which device pulled which paths and when. The History tab shows it.

Known limits:

- Plain HTTP. A device that can sniff the LAN can read what is pulled, including private notes if shared. TLS is not included; it can be added later.
- No auto-discovery. The user types the address.

## Agent setup

A coded version of `Brain/_setup/SETUP-PROMPT.md`. It reads the vault's `_setup/` bundle, which travels in every pack.

Inputs: the vault, `PROJECTS_ROOT`, Codex yes or no.

It first builds a **plan**: every file operation with its diff, shown in the UI. Nothing is written until the user clicks Apply. Every overwritten file is backed up first.

Steps:

1. Copy `_setup/hooks/*.py` to `~/.claude/hooks`. Write `vault_path.txt` with the active vault path.
2. Copy the skills in `_setup/skills/` to `~/.claude/skills`. A name clash opens the diff view.
3. Merge `_setup/settings.snippet.json` into `~/.claude/settings.json`: back up to `settings.json.bak`, keep everything present, append arrays without duplicates, drop `_comment`, fill `<VAULT_PATH>`, `<PY>`, `<HOOKS_DIR>`, check the result is valid JSON.
4. Add the `user-CLAUDE.md.template` text to `~/.claude/CLAUDE.md` between `<!-- brainsync:begin -->` and `<!-- brainsync:end -->` markers. A re-run replaces the block and never duplicates it.
5. Codex only: add `user-AGENTS.md.template` to `~/.codex/AGENTS.md` the same way (respect `CODEX_HOME`). Create symlinks `~/.codex/skills/<name>` to `~/.claude/skills/<name>`; if Windows Developer Mode is off, report the error and do not copy. Add the vault to `writable_roots` in `config.toml` as a one-line text insert shown as a diff; if the file looks unusual, print manual instructions and do not edit.
6. If the vault is not a git repo, run `git init -b main`. Never add a remote, never touch credentials.
7. Verify: `validate_vault.py --all`, `ensure_daily.py`, `autocommit_vault.py --dry-run`, `git status`. Show a pass/fail table.

Multiple vaults: the hooks read a single `vault_path.txt`, so one vault is active and drives the hooks. Other vaults are added to `additionalDirectories` and Codex `writable_roots` only. Switching the active vault re-runs setup.

Bootstrap on a new device: install BrainSync (copy or clone the folder), create an empty vault folder in the UI, import a Starter pack (file or from a peer), then run Setup.

## UI

One page, `web/index.html`, served at `/` only, relative URLs only, console style per the `moss-console-frontend` skill. Tabs: Vaults, Export, Import, Share, Setup, History (audit log and backups).

## Layout

```
Applications/BrainSync/
  AGENTS.md  CLAUDE.md  README.md  CHANGELOG.md  .env.example
  pyproject.toml  run.bat
  src/  app.py ctx.py config.py errors.py fsutil.py vaults.py scanner.py filters.py
        packager.py merger.py importer.py state.py sharing.py routes_share.py
        routes_admin.py peer.py agent_setup.py security.py run.py
  web/index.html
  tests/
  docs/superpowers/specs/
```

`app.py` is glue. Logic lives in the other modules. Every blocking call (file IO, zip, subprocess) runs through `asyncio.to_thread` or an asyncio subprocess. Error messages never contain paths.

## Testing

Tests only for non-trivial logic, run once with `uv run pytest -q`:

- path safety and hard blocks
- privacy classification and filter selection (a filter never selects a private item)
- merge classification table
- pack roundtrip, including a bad-hash rejection
- share auth: code lockout, 404 outside the selection, LAN check
- settings merge and marker-block idempotence

No Docker checks, no full-suite sweep.

## Out of scope

TLS, mDNS discovery, push or write access from a peer, delete propagation, macOS and Linux, Docker, multi-user accounts.

## Revision 2 (2026-11-24): database settings and Citadel admin UI

Changes that replace earlier text where they differ.

- **No `.env`, no config file.** All run-time data is in `.data/brainsync.db` (SQLite): `settings`, `vaults`, `bases`, `audit`, and `meta` (device id, active vault, admin password hash). File blobs and backups stay as files in `.data/`. Replaces `vaults.json`, `device.json`, `bases/*.json` and `audit.jsonl`.
- **Live settings.** `device_name`, `max_pack_mb`, `share_max_fails`, `share_lock_seconds` are read on every use and apply at once. `bind` and `port` are stored too but apply at the next start. The Settings page edits them as a draft with Save and a per-field reset.
- **Admin password.** Not an environment variable. The first run has no password; only a request from localhost may set it. Login returns a 12-hour in-memory session token (`Authorization: Bearer`). Wrong tries lock an address using the same live limits as pairing. Changing the password ends every session. This replaces "refuse to start without `BRAINSYNC_ADMIN_PASSWORD`".
- **UI** is a Vue 3 + TypeScript admin app in `web/`, built to `web/dist` and served by the backend at `/` with a hash router and relative URLs. It uses copies of the Citadel admin components and tokens (drawers, `ToggleSwitch`, `PanelHelp`, `FieldLabel`, `ActionMessage`, `SettingsPanel`) and the Citadel rules. Replaces the single `index.html` page.
- Pages: Vaults, Export, Import, Share, Agent setup, History, Settings, and a Login page that doubles as first-run setup.
