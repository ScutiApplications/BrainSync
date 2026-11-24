from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Paths
from tests.helpers import make_vault

PW = "correct horse"


def app_for(tmp_path):
    return create_app(Paths(tmp_path / "data", tmp_path / "home"))


def local(app):
    return TestClient(app, client=("127.0.0.1", 1))


def setup(c):
    r = c.post("/api/auth/setup", json={"password": PW})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_locked_until_first_password_set_on_this_computer(tmp_path):
    app = app_for(tmp_path)
    lan = TestClient(app, client=("192.168.1.9", 1))
    assert lan.get("/health").status_code == 200
    assert lan.get("/api/vaults").status_code == 401
    st = lan.get("/api/auth/status").json()
    assert st == {"configured": False, "can_setup": False, "authed": False}
    assert lan.post("/api/auth/setup", json={"password": PW}).status_code == 403  # only localhost may claim it
    c = local(app)
    assert c.post("/api/auth/setup", json={"password": "short"}).status_code == 400
    h = setup(c)
    assert c.post("/api/auth/setup", json={"password": PW}).status_code == 409
    assert c.get("/api/vaults", headers=h).status_code == 200
    assert c.get("/api/auth/status", headers=h).json()["authed"] is True


def test_login_lockout_and_password_change(tmp_path):
    app = app_for(tmp_path)
    c = local(app)
    h = setup(c)
    assert c.post("/api/auth/login", json={"password": "nope nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": PW}).status_code == 200
    r = c.post("/api/auth/password", headers=h, json={"current": PW, "new": "another long one"})
    assert r.status_code == 200
    assert c.get("/api/vaults", headers=h).status_code == 401  # old sessions end
    assert c.post("/api/auth/login", json={"password": PW}).status_code == 401
    for _ in range(5):
        c.post("/api/auth/login", json={"password": "bad bad bad"})
    assert c.post("/api/auth/login", json={"password": "another long one"}).status_code == 429


def test_settings_live_and_validated(tmp_path):
    app = app_for(tmp_path)
    c = local(app)
    h = setup(c)
    assert app.state.ctx.settings.get("max_pack_mb") == 2048
    r = c.put("/api/settings/max_pack_mb", headers=h, json={"value": 5})
    assert r.status_code == 200 and app.state.ctx.settings.get("max_pack_mb") == 5  # applied without restart
    assert c.put("/api/settings/max_pack_mb", headers=h, json={"value": 0}).status_code == 400
    assert c.put("/api/settings/bind", headers=h, json={"value": "not-an-ip"}).status_code == 400
    assert c.put("/api/settings/nope", headers=h, json={"value": 1}).status_code == 400
    opt = next(o for o in c.get("/api/settings", headers=h).json()["options"] if o["key"] == "max_pack_mb")
    assert opt["value"] == 5 and opt["changed"] is True
    c.delete("/api/settings/max_pack_mb", headers=h)
    assert app.state.ctx.settings.get("max_pack_mb") == 2048
    # survives a restart: the value is in the db
    c.put("/api/settings/share_lock_seconds", headers=h, json={"value": 99})
    assert app_for(tmp_path).state.ctx.settings.get("share_lock_seconds") == 99


def test_export_import_over_api(tmp_path):
    c = local(app_for(tmp_path))
    h = setup(c)
    src = make_vault(tmp_path / "src", {"Notes/a.md": "A\n", "Notes/p.md": "---\nprivate: true\n---\nP\n"})
    vid = c.post("/api/vaults", headers=h, json={"name": "s", "path": str(src), "create": False}).json()["id"]
    sel = {"selection": {"filter": {"paths": ["Notes/*"]}}}
    assert c.post(f"/api/vaults/{vid}/select", headers=h, json=sel).json()["selected"] == ["Notes/a.md"]
    pack = c.post(f"/api/vaults/{vid}/export", headers=h, json=sel).content
    dst = tmp_path / "dst"
    did = c.post("/api/vaults", headers=h, json={"name": "d", "path": str(dst), "create": True}).json()["id"]
    prev = c.post(f"/api/import/upload?vault_id={did}", headers=h, content=pack).json()
    row = next(r for r in prev["rows"] if r["path"] == "Notes/a.md")
    assert row["state"] == "new"
    res = c.post("/api/import/apply", headers=h, json={"vault_id": did, "pack_id": prev["pack_id"],
                                                        "decisions": {"Notes/a.md": {"action": "import"}}})
    assert res.json()["applied"] == ["Notes/a.md"] and (dst / "Notes/a.md").read_text() == "A\n"
    assert not (dst / "Notes/p.md").exists()
    # vaults and audit are in the db: a new app on the same data folder sees them
    again = app_for(tmp_path).state.ctx
    assert {v["name"] for v in again.vaults.list()} == {"s", "d"}
    assert any(a["event"] == "import" for a in again.state.read_audit())
