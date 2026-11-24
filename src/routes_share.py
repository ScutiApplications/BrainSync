"""Read-only LAN share API. Only active while sharing is on."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from src.ctx import AppContext
from src.filters import select
from src.packager import write_pack
from src.scanner import scan_vault
from src.security import is_lan_ip
from src.sharing import ShareError
from src.vaults import VaultError


class PairBody(BaseModel):
    code: str
    device_id: str
    name: str = ""


class PackBody(BaseModel):
    paths: list[str] = Field(max_length=5000)


def build_share_router(ctx: AppContext) -> APIRouter:
    r = APIRouter(prefix="/share/v1")

    def gate(request: Request) -> str:
        host = request.client.host if request.client else ""
        if not is_lan_ip(host):
            raise HTTPException(403, "not allowed")
        if not ctx.share.active:
            raise HTTPException(404, "not found")
        return host

    def peer_auth(host: str = Depends(gate), authorization: str = Header("")):
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        peer = ctx.share.check(token)
        if peer is None:
            raise HTTPException(401, "bad token")
        return peer

    async def shared(vid: str):
        sel = ctx.share.selections.get(vid)
        try:
            v = ctx.vaults.get(vid)
        except VaultError:
            v = None
        if sel is None or v is None:
            raise HTTPException(404, "not found")
        items = await asyncio.to_thread(scan_vault, Path(v["path"]), v["private_folders"])
        return v, {i.path: i for i in select(items, sel)}

    @r.post("/pair")
    async def pair(body: PairBody, host: str = Depends(gate)):
        try:
            token = ctx.share.pair(body.code, body.device_id, body.name, host)
        except ShareError as e:
            raise HTTPException(e.status, str(e)) from None
        ctx.state.audit("pair", device=body.device_id, ip=host)
        return {"token": token, "device_id": ctx.state.device_id(), "name": ctx.settings.device_name()}

    @r.get("/vaults")
    async def vaults(peer=Depends(peer_auth)):
        out = []
        for vid in ctx.share.selections:
            try:
                out.append({"id": vid, "name": ctx.vaults.get(vid)["name"]})
            except VaultError:
                pass
        return {"vaults": out}

    @r.get("/vaults/{vid}/manifest")
    async def manifest(vid: str, peer=Depends(peer_auth)):
        v, items = await shared(vid)
        return {"device_id": ctx.state.device_id(), "vault_name": v["name"],
                "items": [i.to_dict() for i in items.values()]}

    @r.post("/vaults/{vid}/pack")
    async def pack(vid: str, body: PackBody, peer=Depends(peer_auth)):
        v, items = await shared(vid)
        if any(p not in items for p in body.paths):  # outside the selection looks like missing
            raise HTTPException(404, "not found")
        tmp = ctx.tmp_file()
        await asyncio.to_thread(write_pack, tmp, Path(v["path"]), [items[p] for p in body.paths],
                                device_id=ctx.state.device_id(), vault_name=v["name"])
        ctx.state.audit("pull", device=peer.device_id, name=peer.name, vault_id=vid, paths=body.paths[:200])
        return FileResponse(tmp, media_type="application/zip", filename="share.brainpack",
                            background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))

    return r
