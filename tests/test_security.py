import pytest

from src.security import UnsafePath, check_rel, is_hard_blocked, is_lan_ip, safe_join


def test_hard_blocks():
    for rel in [".env", "a/.env.local", "secrets/x.md", "x/.git/config", "k/id_rsa.pub", "a.pem", "b/.trash/n.md", ".secrets/a"]:
        assert is_hard_blocked(rel), rel
    for rel in ["Notes/a.md", "Notes/environment.md", "Projects/Secretary.md"]:
        assert not is_hard_blocked(rel), rel


@pytest.mark.parametrize("rel", ["", "/a", "../a", "a/../b", "a\\b", "C:/x", "a//b", "./a"])
def test_check_rel_rejects(rel):
    with pytest.raises(UnsafePath):
        check_rel(rel)


def test_safe_join(tmp_path):
    assert safe_join(tmp_path, "Notes/a.md") == (tmp_path / "Notes" / "a.md").resolve()
    with pytest.raises(UnsafePath):
        safe_join(tmp_path, "../x")


def test_lan():
    for ip in ["192.168.1.5", "10.0.0.2", "172.20.1.1", "127.0.0.1", "169.254.1.1", "::1", "fe80::1"]:
        assert is_lan_ip(ip), ip
    for ip in ["8.8.8.8", "172.32.0.1", "testclient", "", "100.64.0.1"]:
        assert not is_lan_ip(ip), ip
