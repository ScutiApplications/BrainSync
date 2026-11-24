from src.auth import SESSION_SECONDS, Auth
from src.db import Db


def make(path, now):
    return Auth(Db(path), lambda: (5, 60), lambda: now[0])


def test_login_survives_restart_and_expires(tmp_path):
    db = tmp_path / "b.db"
    now = [1000.0]
    token = make(db, now).setup("longenough1")
    assert make(db, now).check(token)  # new Auth object = restarted service
    now[0] += SESSION_SECONDS + 1
    assert not make(db, now).check(token)


def test_password_change_and_logout_end_sessions(tmp_path):
    now = [1000.0]
    a = make(tmp_path / "b.db", now)
    t1 = a.setup("longenough1")
    t2 = a.change_password("longenough1", "otherpass22", "1.2.3.4")
    assert not make(tmp_path / "b.db", now).check(t1)
    a.logout(t2)
    assert not a.check(t2)
