"""Agent status, project discovery and project-note sync runs. Routes are added to the admin router (login required)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src import agents
from src.ctx import AppContext
from src.security import is_this_machine


class RunIn(BaseModel):
    vault_id: str
    project: str  # path relative to the projects folder, as listed by /sync/projects
    agent: str = ""


def projects_root(ctx: AppContext, vault: Path) -> Path:
    return Path(ctx.settings.get("projects_root") or vault.parent)


def pick_agent(ctx: AppContext, wanted: str) -> tuple[str, str]:
    """(agent, exe) for the requested or default agent, or an AgentError that says what to fix."""
    kind = wanted or ctx.settings.get("agent_default")
    if kind not in agents.AGENTS:
        raise agents.AgentError(400, "unknown agent")
    if not ctx.settings.get(f"agent_{kind}_enabled"):
        raise agents.AgentError(400, "this agent is switched off in Settings")
    exe = agents.find(kind, ctx.settings)
    if not exe:
        raise agents.AgentError(400, "this agent was not found on this computer")
    return kind, exe


def add_sync_routes(r: APIRouter, ctx: AppContext) -> None:
    def guarded(request: Request) -> None:
        if not is_this_machine(request.client.host if request.client else ""):
            raise HTTPException(403, "agents only start on the computer BrainSync runs on")

    @r.get("/agents/status")
    async def agents_status():
        return agents.status(ctx.settings, ctx.paths.home)

    @r.get("/sync/projects")
    async def sync_projects(vault_id: str):
        v = ctx.vaults.get(vault_id)
        vault = Path(v["path"])
        root = projects_root(ctx, vault)

        def scan():
            rows = agents.find_projects(root, vault) if root.is_dir() else []
            for p in rows:
                p["note"], p["last_synced"] = agents.last_synced(vault, p["name"])
            return rows

        return {"root": str(root), "projects": await asyncio.to_thread(scan)}

    @r.post("/sync/run")
    async def sync_run(b: RunIn, request: Request):
        guarded(request)
        v = ctx.vaults.get(b.vault_id)
        vault = Path(v["path"])
        root = projects_root(ctx, vault)
        found = await asyncio.to_thread(agents.find_projects, root, vault) if root.is_dir() else []
        proj = next((p for p in found if p["rel"] == b.project), None)
        if proj is None:
            raise agents.AgentError(404, "project not found in the projects folder")
        kind, exe = pick_agent(ctx, b.agent)
        cmd = agents.command_line(kind, exe, agents.sync_prompt(proj["name"], proj["path"]), vault, proj["path"])
        mode = ctx.settings.get("sync_after")

        async def after(_job):
            return await agents.finish_sync(vault, mode, proj["name"])

        job = ctx.jobs.start("sync", kind, f"Sync {proj['name']}", cmd, vault,
                             ctx.settings.get("agent_timeout_min") * 60, after)
        ctx.state.audit("sync", vault_id=b.vault_id, project=proj["name"], agent=kind)
        return job.view()

    @r.get("/jobs/{jid}")
    async def job_get(jid: str):
        return ctx.jobs.get(jid).view()

    @r.post("/jobs/{jid}/cancel")
    async def job_cancel(jid: str, request: Request):
        guarded(request)
        ctx.jobs.cancel(jid)
        return {"ok": True}
