"""Admin API. Every route needs the admin password header."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from src import agent_setup, agents
from src.ctx import AppContext
from src.filters import Selection, select
from src.importer import apply_import, build_preview
from src.packager import read_manifest, write_pack
from src.peer import PeerClient, PeerError
from src.routes_auth import bearer
from src.routes_sync import add_sync_routes
from src.scanner import scan_vault
from src.security import is_this_machine

_PACK_ID = re.compile(r"[0-9a-f]{32}")


_PICK_SCRIPT = r"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Title = 'Choose the vault folder'
$d.ValidateNames = $false
$d.CheckFileExists = $false
$d.CheckPathExists = $true
$d.FileName = 'Select this folder'
if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write((Split-Path -Parent $d.FileName)) }
"""


async def _pick_folder() -> str:
    """Open the Windows folder dialog on this computer (modern file dialog) and return the chosen folder, or empty."""
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-STA", "-Command", _PICK_SCRIPT,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 300)
    except asyncio.TimeoutError:
        proc.kill()
        return ""
    return out.decode("utf-8", "replace").strip()


class VaultIn(BaseModel):
    name: str
    path: str
    create: bool = False


class FoldersIn(BaseModel):
    folders: list[str]


class SelIn(BaseModel):
    selection: dict = {}


class ApplyIn(BaseModel):
    vault_id: str
    pack_id: str
    decisions: dict[str, dict] = {}


class ShareIn(BaseModel):
    selections: dict[str, dict]


class ConnectIn(BaseModel):
    address: str
    code: str


class PullIn(BaseModel):
    paths: list[str]
    vault_id: str


class SettingIn(BaseModel):
    value: bool | int | str


class SetupIn(BaseModel):
    vault_id: str
    projects_root: str = ""
    claude: bool = True
    codex: bool = False
    selected: list[int] = []


def build_admin_router(ctx: AppContext) -> APIRouter:
    def auth(authorization: str = Header("")):
        if not ctx.auth.check(bearer(authorization)):
            raise HTTPException(401, "login required")

    r = APIRouter(prefix="/api", dependencies=[Depends(auth)])
    add_sync_routes(r, ctx)

    def selection(vid: str, d: dict) -> Selection:
        sel = Selection.from_dict(d)
        peer = (d.get("filter") or {}).get("changed_since_peer")
        if peer:
            sel.filter.changed_since = ctx.state.load_base(vid, peer)
        return sel

    async def scan(vid: str):
        v = ctx.vaults.get(vid)
        return v, await asyncio.to_thread(scan_vault, Path(v["path"]), v["private_folders"])

    # ---- folder picker: the dialog opens on the computer BrainSync runs on, so only that computer may ask
    @r.post("/fs/pick")
    async def fs_pick(request: Request):
        if not is_this_machine(request.client.host if request.client else ""):
            raise HTTPException(403, "the folder dialog only opens on the computer BrainSync runs on")
        return {"path": await _pick_folder()}

    # ---- vaults
    @r.get("/vaults")
    async def vaults():
        return {"vaults": ctx.vaults.list()}

    @r.post("/vaults")
    async def add_vault(b: VaultIn):
        return await asyncio.to_thread(ctx.vaults.add, b.name, b.path, b.create)

    @r.get("/vaults/{vid}/peers")
    async def vault_peers(vid: str):
        ctx.vaults.get(vid)
        return {"peers": ctx.state.list_peers(vid)}

    @r.delete("/vaults/{vid}")
    async def del_vault(vid: str):
        ctx.vaults.remove(vid)
        return {"ok": True}

    @r.put("/vaults/{vid}/private-folders")
    async def private_folders(vid: str, b: FoldersIn):
        ctx.vaults.set_private_folders(vid, b.folders)
        return {"ok": True}

    @r.post("/vaults/{vid}/active")
    async def active(vid: str):
        ctx.vaults.set_active(vid)
        return {"ok": True}

    @r.post("/vaults/{vid}/select")
    async def select_items(vid: str, b: SelIn):
        _, items = await scan(vid)
        chosen = select(items, selection(vid, b.selection))
        return {"all": [i.to_dict() for i in items], "selected": [i.path for i in chosen]}

    # ---- export
    @r.post("/vaults/{vid}/export")
    async def export(vid: str, b: SelIn):
        v, items = await scan(vid)
        chosen = select(items, selection(vid, b.selection))
        tmp = ctx.tmp_file()
        await asyncio.to_thread(write_pack, tmp, Path(v["path"]), chosen,
                                device_id=ctx.state.device_id(), vault_name=v["name"])
        ctx.state.audit("export", vault_id=vid, count=len(chosen))
        name = re.sub(r"[^\w.-]+", "_", v["name"])[:40] or "vault"
        return FileResponse(tmp, media_type="application/zip", filename=f"{name}.brainpack",
                            background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))

    # ---- import
    async def preview(vault_id: str, pack_id: str) -> dict:
        v = ctx.vaults.get(vault_id)
        dest = ctx.incoming(pack_id)
        try:
            m = await asyncio.to_thread(read_manifest, dest)
            rows = await asyncio.to_thread(build_preview, Path(v["path"]), dest, m, ctx.state, vault_id)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return {"pack_id": pack_id, "source_device_id": m["source_device_id"],
                "vault_name": m["vault_name"], "rows": rows}

    @r.post("/import/upload")
    async def upload(request: Request, vault_id: str):
        ctx.vaults.get(vault_id)
        pack_id = uuid4().hex
        dest, size = ctx.incoming(pack_id), 0
        f = await asyncio.to_thread(dest.open, "wb")
        try:
            async for chunk in request.stream():
                size += len(chunk)
                if size > ctx.settings.get("max_pack_mb") * 1024 * 1024:  # read live on every upload
                    raise HTTPException(413, "pack too large")
                await asyncio.to_thread(f.write, chunk)
        except BaseException:
            await asyncio.to_thread(f.close)
            dest.unlink(missing_ok=True)
            raise
        await asyncio.to_thread(f.close)
        return await preview(vault_id, pack_id)

    @r.post("/import/apply")
    async def apply(b: ApplyIn):
        if not _PACK_ID.fullmatch(b.pack_id) or not ctx.incoming(b.pack_id).is_file():
            raise HTTPException(404, "pack not found")
        v, dest = ctx.vaults.get(b.vault_id), ctx.incoming(b.pack_id)
        m = await asyncio.to_thread(read_manifest, dest)
        res = await asyncio.to_thread(apply_import, Path(v["path"]), dest, m, ctx.state, b.vault_id,
                                      b.decisions, "peer")
        dest.unlink(missing_ok=True)
        return res

    # ---- share
    @r.post("/share/start")
    async def share_start(b: ShareIn):
        sels = {}
        for vid, d in b.selections.items():
            ctx.vaults.get(vid)
            sels[vid] = selection(vid, d)
        return {"code": ctx.share.start(sels)}

    @r.post("/share/stop")
    async def share_stop():
        ctx.share.stop()
        return {"ok": True}

    @r.get("/share/status")
    async def share_status():
        return {"active": ctx.share.active, "code": ctx.share.code, "peers": ctx.share.peers()}

    @r.delete("/share/peers/{device_id}")
    async def share_revoke(device_id: str):
        ctx.share.revoke(device_id)
        return {"ok": True}

    # ---- peer (this device pulls from another)
    def conn(cid: str) -> dict:
        c = ctx.conns.get(cid)
        if c is None:
            raise HTTPException(404, "not connected")
        return c

    @r.post("/peer/connect")
    async def peer_connect(b: ConnectIn):
        pc = PeerClient(b.address)
        try:
            info = await pc.pair(b.code, ctx.state.device_id(), ctx.settings.device_name())
        except PeerError:
            await pc.aclose()
            raise
        cid = uuid4().hex
        ctx.conns[cid] = {"client": pc, "token": info["token"], "peer_id": info["device_id"], "name": info["name"]}
        return {"cid": cid, "name": info["name"]}

    @r.get("/peer/{cid}/vaults")
    async def peer_vaults(cid: str):
        c = conn(cid)
        return await c["client"].vaults(c["token"])

    @r.get("/peer/{cid}/vaults/{vid}/manifest")
    async def peer_manifest(cid: str, vid: str):
        c = conn(cid)
        return await c["client"].manifest(c["token"], vid)

    @r.post("/peer/{cid}/vaults/{vid}/pull")
    async def peer_pull(cid: str, vid: str, b: PullIn):
        c = conn(cid)
        ctx.vaults.get(b.vault_id)
        pack_id = uuid4().hex
        await c["client"].pull(c["token"], vid, b.paths, ctx.incoming(pack_id))
        return await preview(b.vault_id, pack_id)

    @r.delete("/peer/{cid}")
    async def peer_close(cid: str):
        c = ctx.conns.pop(cid, None)
        if c:
            await c["client"].aclose()
        return {"ok": True}

    # ---- agent setup
    def plan(b: SetupIn):
        v = ctx.vaults.get(b.vault_id)
        if not b.projects_root.strip():
            raise agent_setup.SetupError("projects root is required")
        others = [Path(x["path"]) for x in ctx.vaults.list() if x["id"] != b.vault_id]
        return agent_setup.build_plan(Path(v["path"]), home=ctx.paths.home, projects_root=b.projects_root,
                                      codex=b.codex, others=others, claude_on=b.claude)

    @r.get("/setup/detect")
    async def setup_detect():
        """Which agents look installed on this computer (config folder or command found)."""
        st = agents.status(ctx.settings, ctx.paths.home)
        return {"claude": st["claude"]["found"], "codex": st["codex"]["found"]}

    @r.post("/setup/plan")
    async def setup_plan(b: SetupIn):
        ops = await asyncio.to_thread(plan, b)
        return {"ops": [{"id": i, "label": o.label, "diff": agent_setup.render_diff(o),
                         "manual": bool(o.manual)} for i, o in enumerate(ops)]}

    @r.post("/setup/apply")
    async def setup_apply(b: SetupIn):
        ops = await asyncio.to_thread(plan, b)
        stamp = ctx.state.root / "backups" / ("setup-" + uuid4().hex[:8])
        res = await asyncio.to_thread(agent_setup.apply_plan, ops, set(b.selected), stamp)
        ctx.vaults.set_active(b.vault_id)
        ctx.state.audit("setup", vault_id=b.vault_id, count=len(res))
        return {"results": res}

    @r.post("/setup/verify")
    async def setup_verify(b: SetupIn):
        v = ctx.vaults.get(b.vault_id)
        return {"rows": await asyncio.to_thread(agent_setup.verify, Path(v["path"]), ctx.paths.home)}

    # ---- settings (stored in the db, applied at once)
    @r.get("/settings")
    async def settings_list():
        return {"options": ctx.settings.snapshot()}

    @r.put("/settings/{key}")
    async def settings_set(key: str, b: SettingIn):
        value = ctx.settings.set(key, b.value)
        ctx.state.audit("setting", key=key, value=value)
        return {"options": ctx.settings.snapshot()}

    @r.delete("/settings/{key}")
    async def settings_reset(key: str):
        ctx.settings.reset(key)
        ctx.state.audit("setting-reset", key=key)
        return {"options": ctx.settings.snapshot()}

    @r.get("/history")
    async def history():
        return {"audit": ctx.state.read_audit(), "backups": ctx.state.list_backups()}

    return r
