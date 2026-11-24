"""Client for another BrainSync's share API."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from src.errors import BrainSyncError
from src.security import is_lan_ip


class PeerError(BrainSyncError):
    pass


class PeerClient:
    def __init__(self, address: str, client: httpx.AsyncClient | None = None):
        host, _, port = address.strip().partition(":")
        if not is_lan_ip(host) or not port.isdigit() or not 1 <= int(port) <= 65535:
            raise PeerError("address must be a LAN IPv4 ip:port")
        self.base = f"http://{host}:{port}/share/v1"
        self._c = client or httpx.AsyncClient(timeout=httpx.Timeout(10, read=120))

    async def aclose(self) -> None:
        await self._c.aclose()

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code == 429:
            raise PeerError("too many tries, wait a minute")
        if r.status_code in (401, 403):
            raise PeerError("peer refused the code or token")
        if r.status_code != 200:
            raise PeerError("peer refused the request")

    async def _get(self, path: str, token: str) -> dict:
        try:
            r = await self._c.get(self.base + path, headers=self._headers(token))
        except httpx.HTTPError:
            raise PeerError("peer unreachable") from None
        self._check(r)
        return r.json()

    async def pair(self, code: str, device_id: str, name: str) -> dict:
        try:
            r = await self._c.post(self.base + "/pair", json={"code": code, "device_id": device_id, "name": name})
        except httpx.HTTPError:
            raise PeerError("peer unreachable") from None
        self._check(r)
        return r.json()

    async def vaults(self, token: str) -> dict:
        return await self._get("/vaults", token)

    async def manifest(self, token: str, vid: str) -> dict:
        return await self._get(f"/vaults/{vid}/manifest", token)

    async def pull(self, token: str, vid: str, paths: list[str], dest: Path) -> None:
        try:
            async with self._c.stream("POST", f"{self.base}/vaults/{vid}/pack", json={"paths": paths},
                                      headers=self._headers(token)) as r:
                self._check(r)
                f = await asyncio.to_thread(dest.open, "wb")
                try:
                    async for chunk in r.aiter_bytes():
                        await asyncio.to_thread(f.write, chunk)
                finally:
                    await asyncio.to_thread(f.close)
        except httpx.HTTPError:
            dest.unlink(missing_ok=True)
            raise PeerError("peer unreachable") from None
