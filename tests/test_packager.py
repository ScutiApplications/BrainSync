import json
import zipfile

import pytest

from src.packager import PackError, read_file, read_manifest, write_pack
from src.scanner import scan_vault
from tests.helpers import make_vault

DEV = "a" * 32


def test_roundtrip_and_tamper(tmp_path):
    v = make_vault(tmp_path / "v", {"Notes/a.md": "hello"})
    pack = tmp_path / "p.brainpack"
    write_pack(pack, v, scan_vault(v, []), device_id=DEV, vault_name="v")
    m = read_manifest(pack)
    entry = next(e for e in m["items"] if e["path"] == "Notes/a.md")
    assert read_file(pack, entry) == b"hello"
    bad = tmp_path / "bad.brainpack"
    with zipfile.ZipFile(pack) as src, zipfile.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, b"tampered" if n == "files/Notes/a.md" else src.read(n))
    with pytest.raises(PackError):
        read_file(bad, entry)


@pytest.mark.parametrize("path", ["../x", "/abs", ".env", "a/secrets/b.md"])
def test_manifest_rejects_bad_paths(tmp_path, path):
    pack = tmp_path / "m.brainpack"
    m = {"format": 1, "pack_id": "p", "source_device_id": DEV, "vault_name": "v", "created": "x",
         "items": [{"path": path, "sha256": "0", "size": 0, "mtime": 0, "private": False}]}
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
    with pytest.raises(PackError):
        read_manifest(pack)


def test_not_a_pack(tmp_path):
    p = tmp_path / "x.brainpack"
    p.write_bytes(b"nope")
    with pytest.raises(PackError):
        read_manifest(p)
