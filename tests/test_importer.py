import pytest

from src.importer import apply_import, build_preview
from src.merger import MergeError
from src.packager import read_manifest, write_pack
from src.scanner import scan_vault
from src.state import State
from tests.helpers import make_vault


def export(vault, state):
    pack = vault.parent / f"{vault.name}-{len(list(vault.parent.glob('*.brainpack')))}.brainpack"
    write_pack(pack, vault, scan_vault(vault, []), device_id=state.device_id(), vault_name="v")
    return pack, read_manifest(pack)


def rows_of(b, pack, m, sb):
    return {r["path"]: r for r in build_preview(b, pack, m, sb, "b" * 32)}


def test_import_then_auto_merge(tmp_path):
    a = make_vault(tmp_path / "a", {"Notes/x.md": "one\ntwo\nthree\n", "Notes/y.md": "y1\n"})
    b = make_vault(tmp_path / "b", {})
    sa, sb = State(tmp_path / "sa"), State(tmp_path / "sb")
    pack, m = export(a, sa)
    rows = rows_of(b, pack, m, sb)
    assert rows["Notes/x.md"]["state"] == "new" and rows["AGENTS.md"]["state"] == "identical"
    decisions = {p: {"action": r["default"]} for p, r in rows.items() if r["default"] != "skip"}
    apply_import(b, pack, m, sb, "b" * 32, decisions)
    assert (b / "Notes/x.md").read_text() == "one\ntwo\nthree\n"

    (a / "Notes/x.md").write_text("ONE\ntwo\nthree\n")
    (b / "Notes/x.md").write_text("one\ntwo\nTHREE\n")
    pack2, m2 = export(a, sa)
    rows = rows_of(b, pack2, m2, sb)
    assert rows["Notes/x.md"]["state"] == "conflict" and rows["Notes/x.md"]["default"] == "merge"
    assert rows["Notes/y.md"]["state"] == "identical"
    res = apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/x.md": {"action": "merge"}})
    assert (b / "Notes/x.md").read_text() == "ONE\ntwo\nTHREE\n"
    assert res["applied"] == ["Notes/x.md"] and any((sb.root / "backups").rglob("x.md"))


def test_conflict_needs_choice_and_absent_means_skip(tmp_path):
    a = make_vault(tmp_path / "a", {"Notes/c.md": "base\n"})
    b = make_vault(tmp_path / "b", {})
    sa, sb = State(tmp_path / "sa"), State(tmp_path / "sb")
    pack, m = export(a, sa)
    apply_import(b, pack, m, sb, "b" * 32, {"Notes/c.md": {"action": "import"}})
    (a / "Notes/c.md").write_text("A\n")
    (b / "Notes/c.md").write_text("B\n")
    pack2, m2 = export(a, sa)
    assert rows_of(b, pack2, m2, sb)["Notes/c.md"]["default"] == "unresolved"
    with pytest.raises(MergeError):
        apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/c.md": {"action": "merge"}})
    assert (b / "Notes/c.md").read_text() == "B\n"
    apply_import(b, pack2, m2, sb, "b" * 32, {"Notes/c.md": {"action": "merge", "choices": {"0": "both"}}})
    assert (b / "Notes/c.md").read_text() == "B\nA\n"
    # nothing decided -> nothing written
    (a / "Notes/c.md").write_text("A2\n")
    pack3, m3 = export(a, sa)
    assert apply_import(b, pack3, m3, sb, "b" * 32, {})["applied"] == []
