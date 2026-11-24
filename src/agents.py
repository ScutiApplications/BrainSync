"""Run Claude Code or Codex headless (project-note syncs, setup checks). One job at a time; output is polled."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from src.errors import BrainSyncError

AGENTS = ("claude", "codex")
MAX_OUTPUT = 200_000
_SKIP = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".git", ".idea", ".vscode"}
_NAME = re.compile(r"[A-Za-z0-9 _.\-]+")


class AgentError(BrainSyncError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def find(kind: str, settings) -> str | None:
    """Full path of the agent command, or None when it is not installed or not allowed."""
    if kind not in AGENTS:
        return None
    return shutil.which(settings.get(f"agent_{kind}_command") or kind)


def status(settings, home: Path) -> dict:
    out = {}
    for kind in AGENTS:
        cfg = Path(os.environ.get("CODEX_HOME") or home / ".codex") if kind == "codex" else home / ".claude"
        exe = find(kind, settings)
        out[kind] = {"found": cfg.is_dir() or exe is not None, "runnable": exe is not None,
                     "enabled": bool(settings.get(f"agent_{kind}_enabled"))}
    out["default"] = settings.get("agent_default")
    return out


def find_projects(root: Path, vault: Path, max_depth: int = 3) -> list[dict]:
    """Git projects below root (not the vault itself). A project folder is not searched further."""
    found: list[dict] = []
    vault = vault.resolve()

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted((e for e in os.scandir(d) if e.is_dir(follow_symlinks=False)), key=lambda e: e.name.lower())
        except OSError:
            return
        for e in entries:
            if e.name in _SKIP or e.name.startswith("."):
                continue
            p = Path(e.path)
            if p.resolve() == vault:
                continue
            if (p / ".git").exists():
                found.append({"name": e.name, "path": str(p), "rel": p.relative_to(root).as_posix()})
            elif depth < max_depth:
                walk(p, depth + 1)

    walk(root, 1)
    return found


def last_synced(vault: Path, name: str) -> tuple[bool, str]:
    note = vault / "Projects" / f"{name}.md"
    if not note.is_file():
        return False, ""
    try:
        with note.open(encoding="utf-8", errors="replace") as f:
            for _ in range(40):
                m = re.match(r"last_synced:\s*(\S+)", f.readline())
                if m:
                    return True, m.group(1)
    except OSError:
        pass
    return True, ""


def sync_prompt(name: str, path: str) -> str:
    if not _NAME.fullmatch(name):
        raise AgentError(400, "project name has characters that are not allowed")
    return (f"Use the project-sync skill to update the vault note for the project '{name}' located at {path}. "
            f"Edit only files inside this vault (Projects/{name}.md, index.md, log.md). Treat the project code as read-only. "
            "Finish with a short summary of what changed.")


def command_line(kind: str, exe: str, prompt: str, vault: Path, extra_dir: str | None = None) -> list[str]:
    if kind == "claude":
        cmd = [exe, "-p", prompt, "--permission-mode", "acceptEdits"]
        if extra_dir:
            cmd += ["--add-dir", extra_dir]
        return cmd + ["--allowedTools", "Read", "Glob", "Grep", "Edit", "Write",
                      "Bash(git log:*)", "Bash(git status:*)", "Bash(git -C:*)"]
    return [exe, "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(vault), prompt]


@dataclass
class Job:
    kind: str
    agent: str
    label: str
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    state: str = "running"  # running | done | failed | cancelled | timeout
    output: str = ""
    exit_code: int | None = None
    started: float = field(default_factory=time.time)
    proc: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "agent": self.agent, "label": self.label, "state": self.state,
                "output": self.output, "exit_code": self.exit_code}


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.kill()


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def running(self) -> Job | None:
        return next((j for j in self.jobs.values() if j.state == "running"), None)

    def get(self, jid: str) -> Job:
        j = self.jobs.get(jid)
        if j is None:
            raise AgentError(404, "job not found")
        return j

    def start(self, kind: str, agent: str, label: str, cmd: list[str], cwd: Path, timeout_s: int,
              after: Callable[[Job], Awaitable[str]] | None = None) -> Job:
        if self.running():
            raise AgentError(409, "another agent run is still going")
        job = Job(kind, agent, label)
        self.jobs[job.id] = job
        for old in list(self.jobs)[:-20]:
            if self.jobs[old].state != "running":
                del self.jobs[old]
        job.task = asyncio.create_task(self._run(job, cmd, cwd, timeout_s, after))
        return job

    async def _run(self, job: Job, cmd: list[str], cwd: Path, timeout_s: int, after) -> None:
        async def pump() -> None:
            while chunk := await job.proc.stdout.read(4096):  # type: ignore[union-attr]
                if len(job.output) < MAX_OUTPUT:
                    job.output += chunk.decode("utf-8", "replace")

        try:
            job.proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=str(cwd), stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            await asyncio.wait_for(asyncio.gather(pump(), job.proc.wait()), timeout_s)
            job.exit_code = job.proc.returncode
            job.state = "done" if job.exit_code == 0 else "failed"
            if job.state == "done" and after:
                job.output += "\n" + await after(job)
        except asyncio.TimeoutError:
            job.state = "timeout"
            if job.proc:
                _kill_tree(job.proc)
        except asyncio.CancelledError:
            job.state = "cancelled"
            if job.proc:
                _kill_tree(job.proc)
        except OSError:
            job.state = "failed"
            job.output += "\nThe agent could not be started."

    def cancel(self, jid: str) -> None:
        j = self.get(jid)
        if j.state == "running" and j.task:
            j.state = "cancelled"  # set here too: a task cancelled before its first step never reaches its handler
            if j.proc:
                _kill_tree(j.proc)
            j.task.cancel()


async def _git(vault: Path, *args: str) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec("git", "-C", str(vault), *args, stdin=asyncio.subprocess.DEVNULL,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode or 0, out.decode("utf-8", "replace").strip()


async def finish_sync(vault: Path, mode: str, name: str) -> str:
    """After a successful sync: nothing, commit, or commit and push (push only if a remote exists)."""
    if mode == "nothing":
        return "Vault changes left uncommitted."
    if not (vault / ".git").exists():
        return "The vault is not a git repository, so nothing was committed."
    await _git(vault, "add", "--", "Projects", "index.md", "log.md")
    code, msg = await _git(vault, "commit", "-m", f"project-sync: {name}", "--", "Projects", "index.md", "log.md")
    if code != 0:
        return "Nothing to commit."
    if mode == "commit_push":
        _, remotes = await _git(vault, "remote")
        if not remotes:
            return "Committed. The vault has no remote, so nothing was pushed."
        code, out = await _git(vault, "push")
        return "Committed and pushed." if code == 0 else "Committed, but the push failed."
    return "Committed."
