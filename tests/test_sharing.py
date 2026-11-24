import asyncio

import httpx
import pytest

from src.app import create_app
from src.config import Paths
from src.filters import Filter, Selection
from src.packager import read_manifest
from src.peer import PeerClient, PeerError
from src.sharing import ShareError, ShareManager
from tests.helpers import make_vault


def test_lockout_and_inactive():
    t = [0.0]
    m = ShareManager(clock=lambda: t[0])
    with pytest.raises(ShareError) as e:
        m.pair("X", "a" * 32, "n", "10.0.0.2")
    assert e.value.status == 404
    m.start({})
    for _ in range(5):
        with pytest.raises(ShareError) as e:
            m.pair("WRONG123", "a" * 32, "n", "10.0.0.2")
        assert e.value.status == 403
    with pytest.raises(ShareError) as e:
        m.pair(m.code, "a" * 32, "n", "10.0.0.2")
    assert e.value.status == 429
    t[0] = 61
    tok = m.pair(m.code, "a" * 32, "n", "10.0.0.2")
    assert m.check(tok).device_id == "a" * 32
    m.revoke("a" * 32)
    assert m.check(tok) is None


def test_share_pull_roundtrip(tmp_path):
    app = create_app(Paths(tmp_path / "data", tmp_path / "home"))
    ctx = app.state.ctx
    v = make_vault(tmp_path / "v", {"Notes/a.md": "A\n", "Notes/p.md": "---\nprivate: true\n---\nP\n", "Other/o.md": "O\n"})
    vault = ctx.vaults.add("v", str(v))
    ctx.share.start({vault["id"]: Selection(filter=Filter(paths=["Notes/*"]))})

    async def run():
        t = httpx.ASGITransport(app=app, client=("127.0.0.1", 5))
        async with httpx.AsyncClient(transport=t, base_url="http://x") as hc:
            pc = PeerClient("127.0.0.1:26508", client=hc)
            tok = (await pc.pair(ctx.share.code, "b" * 32, "dev"))["token"]
            man = await pc.manifest(tok, vault["id"])
            assert [i["path"] for i in man["items"]] == ["Notes/a.md"]
            dest = tmp_path / "got.brainpack"
            await pc.pull(tok, vault["id"], ["Notes/a.md"], dest)
            assert [e["path"] for e in read_manifest(dest)["items"]] == ["Notes/a.md"]
            for bad in ("Notes/p.md", "Other/o.md"):
                with pytest.raises(PeerError):
                    await pc.pull(tok, vault["id"], [bad], tmp_path / "no.brainpack")
            assert not (tmp_path / "no.brainpack").exists()
        t = httpx.ASGITransport(app=app, client=("8.8.8.8", 5))
        async with httpx.AsyncClient(transport=t, base_url="http://x") as hc:
            r = await hc.post("/share/v1/pair", json={"code": ctx.share.code, "device_id": "c" * 32, "name": "x"})
            assert r.status_code == 403

    asyncio.run(run())


def test_peer_address_must_be_lan():
    for bad in ["8.8.8.8:26508", "example.com:26508", "10.0.0.2", "10.0.0.2:0", "10.0.0.2:x"]:
        with pytest.raises(PeerError):
            PeerClient(bad)
