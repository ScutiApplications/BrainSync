import pytest

from src.merger import (MergeError, classify, conflict_count, is_text, keep_both_name,
                        merge_hunks, resolve, union_lines)


def test_classify_table():
    assert classify(None, b"t", None) == "new"
    assert classify(b"a\r\nb", b"a\nb", None) == "identical"
    assert classify(b"m", b"t", None) == "no_base"
    assert classify(b"base", b"t", b"base") == "theirs_only"
    assert classify(b"m", b"base", b"base") == "mine_only"
    assert classify(b"m", b"t", b"base") == "conflict"


def test_clean_three_way():
    h = merge_hunks(b"one\ntwo\nthree\n", b"ONE\ntwo\nthree\n", b"one\ntwo\nTHREE\n")
    assert conflict_count(h) == 0
    assert resolve(h, {}) == "ONE\ntwo\nTHREE\n"


def test_conflict_choices():
    h = merge_hunks(b"x\n", b"B\n", b"A\n")
    assert conflict_count(h) == 1
    with pytest.raises(MergeError):
        resolve(h, {})
    assert resolve(h, {"0": "mine"}) == "B\n"
    assert resolve(h, {0: "theirs"}) == "A\n"
    assert resolve(h, {0: "both"}) == "B\nA\n"
    assert resolve(h, {0: {"text": "edited\n"}}) == "edited\n"


def test_two_way_when_no_base():
    h = merge_hunks(None, b"same\nmine\n", b"same\ntheirs\n")
    assert conflict_count(h) == 1
    assert resolve(h, {0: "theirs"}) == "same\ntheirs\n"


def test_helpers():
    assert union_lines("a\nb\n", "b\nc\nc\n") == "a\nb\nc\n"
    assert keep_both_name("Notes/pic.png", "Lap/top") == "Notes/pic (from Lap_top).png"
    assert is_text(b"hi") and not is_text(b"\x00\x01") and not is_text(b"\xff\xfe\xfa")
