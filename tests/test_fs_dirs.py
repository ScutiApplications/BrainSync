import pytest
from fastapi import HTTPException

from src.routes_admin import _list_dirs


def test_lists_subfolders_and_flags_vault(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "A").mkdir()
    (tmp_path / "file.txt").write_text("x")
    got = _list_dirs(str(tmp_path))
    assert got["dirs"] == ["A", "b"] and got["is_vault"] is False
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "AGENTS.md").write_text("x")
    assert _list_dirs(str(tmp_path))["is_vault"] is True


def test_rejects_missing_and_relative():
    for bad in ("relative/dir", "Z:\no\such\folder"):
        with pytest.raises(HTTPException):
            _list_dirs(bad)


def test_empty_path_lists_drives():
    assert _list_dirs("")["parent"] is None
