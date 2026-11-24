import pytest

from src.scanner import FrontmatterError, parse_frontmatter, scan_vault
from tests.helpers import make_vault


def test_frontmatter_forms():
    fm = parse_frontmatter("---\ntype: note\ntags:\n  - a\n  - b\nstatus: 'seed'\n---\nbody")
    assert fm == {"type": "note", "tags": ["a", "b"], "status": "seed"}
    assert parse_frontmatter("no front") == {}
    with pytest.raises(FrontmatterError):
        parse_frontmatter("---\ntitle: x\nno end")


def test_scan_privacy_and_whitelist(tmp_path):
    v = make_vault(tmp_path / "v", {
        "Notes/a.md": "---\ntype: note\nstatus: active\ntags: [x, y]\ncreated: 2026-01-02\n---\nbody",
        "Notes/p.md": "---\nprivate: true\n---\nP",
        "Notes/bad.md": "---\ntitle: x\nno end",
        "Priv/z.md": "plain",
        "secrets/s.md": "no", ".env": "K=1",
        ".obsidian/app.json": "{}", ".obsidian/workspace.json": "{}",
        "Notes/pic.png": b"\x89PNG", "Notes/x.exe": b"MZ", "_setup/hooks/h.py": "print(1)",
    })
    items = {i.path: i for i in scan_vault(v, ["Priv"])}
    for gone in ["secrets/s.md", ".env", ".obsidian/workspace.json", "Notes/x.exe"]:
        assert gone not in items
    for kept in [".obsidian/app.json", "_setup/hooks/h.py", "Notes/pic.png"]:
        assert kept in items
    a = items["Notes/a.md"]
    assert (a.type, a.status, a.tags, a.created, a.private) == ("note", "active", ("x", "y"), "2026-01-02", False)
    assert items["Notes/p.md"].private and items["Notes/bad.md"].private and items["Priv/z.md"].private
    assert not items["AGENTS.md"].private
