import asyncio
import sys

import pytest

from src import agents
from src.db import Db
from src.settings import LiveSettings, SettingError


def test_find_projects_skips_vault_and_noise(tmp_path):
    for p in ("a/.git", "grp/b/.git", "grp/c/node_modules/x/.git", "Brain/.git", ".hidden/d/.git"):
        (tmp_path / p).mkdir(parents=True)
    got = agents.find_projects(tmp_path, tmp_path / "Brain")
    assert [p["rel"] for p in got] == ["a", "grp/b"]


def test_last_synced_reads_frontmatter(tmp_path):
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Projects" / "X.md").write_text("---\ntype: project\nlast_synced: 2026-11-24\n---\n")
    assert agents.last_synced(tmp_path, "X") == (True, "2026-11-24")
    assert agents.last_synced(tmp_path, "Y") == (False, "")


def test_prompt_rejects_odd_names():
    with pytest.raises(agents.AgentError):
        agents.sync_prompt("a'; rm -rf", "D:/x")


def test_command_setting_must_name_the_agent(tmp_path):
    s = LiveSettings(Db(tmp_path / "s.db"))
    s.set("agent_claude_command", "C:/bin/claude.exe")
    for bad in ("C:/bin/evil.exe", "claude-evil", "codex"):
        with pytest.raises(SettingError):
            s.set("agent_claude_command", bad)
    with pytest.raises(SettingError):
        s.set("sync_after", "push-everything")
    assert s.set("agent_default", "codex") == "codex"


def test_job_runs_and_times_out(tmp_path):
    async def go():
        jm = agents.JobManager()
        ok = jm.start("sync", "claude", "t", [sys.executable, "-c", "print('hi')"], tmp_path, 20)
        await ok.task
        assert ok.state == "done" and "hi" in ok.output
        slow = jm.start("sync", "claude", "t", [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 1)
        await slow.task
        assert slow.state == "timeout"
        again = jm.start("sync", "claude", "t", [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 20)
        with pytest.raises(agents.AgentError):
            jm.start("sync", "claude", "t2", [sys.executable, "-c", "1"], tmp_path, 5)
        jm.cancel(again.id)
        await asyncio.gather(again.task, return_exceptions=True)
        assert again.state == "cancelled"

    asyncio.run(go())
