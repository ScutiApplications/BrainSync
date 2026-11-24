from src.filters import STARTER, Filter, Selection, select
from src.scanner import Item


def it(path, **kw):
    return Item(path=path, sha256=kw.pop("sha", "h"), size=1, mtime=kw.pop("mtime", 0.0), **kw)


ITEMS = [
    it("Notes/a.md", type="note", status="active", tags=("x",), created="2026-02-01"),
    it("Notes/b.md", type="note", status="seed", tags=("y",), created="2026-03-01"),
    it("Notes/p.md", type="note", private=True),
    it("Templates/t.md"), it("AGENTS.md"), it("_setup/s.json"), it(".obsidian/app.json"),
]


def paths(sel):
    return [i.path for i in select(ITEMS, sel)]


def test_private_never_by_filter():
    assert "Notes/p.md" not in paths(Selection())
    assert "Notes/p.md" not in paths(Selection(filter=Filter(paths=["Notes/*"])))
    assert "Notes/p.md" in paths(Selection(include_private={"Notes/p.md"}))


def test_filter_fields():
    assert paths(Selection(filter=Filter(types=["note"], statuses=["active"]))) == ["Notes/a.md"]
    assert paths(Selection(filter=Filter(tags=["y"]))) == ["Notes/b.md"]
    assert paths(Selection(filter=Filter(created_from="2026-02-15"))) == ["Notes/b.md"]
    assert paths(Selection(filter=Filter(created_to="2026-02-15"))) == ["Notes/a.md"]


def test_include_exclude_and_explicit_mode():
    assert paths(Selection(use_filter=False, include={"AGENTS.md"})) == ["AGENTS.md"]
    assert "Notes/a.md" not in paths(Selection(exclude={"Notes/a.md"}))


def test_changed_since():
    sel = Selection(filter=Filter(changed_since={"Notes/a.md": "h", "Notes/b.md": "old"}, paths=["Notes/*"]))
    assert paths(sel) == ["Notes/b.md"]


def test_starter():
    got = paths(STARTER)
    assert set(got) == {"Templates/t.md", "AGENTS.md", "_setup/s.json", ".obsidian/app.json"}
    assert Selection.from_dict({"filter": {"tags": ["x"]}, "include": ["AGENTS.md"]}).include == {"AGENTS.md"}
