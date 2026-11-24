"""Login, first-run password setup and password change."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from src.auth import AuthError
from src.ctx import AppContext
from src.security import is_this_machine


def bearer(authorization: str) -> str:
    return authorization[7:] if authorization.startswith("Bearer ") else ""


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


class PasswordIn(BaseModel):
    password: str


class ChangeIn(BaseModel):
    current: str
    new: str


def build_auth_router(ctx: AppContext) -> APIRouter:
    r = APIRouter(prefix="/api/auth")

    def guarded(fn):
        try:
            return fn()
        except AuthError as e:
            raise HTTPException(e.status, str(e)) from None

    @r.get("/status")
    async def status(request: Request, authorization: str = Header("")):
        configured = ctx.auth.configured()
        return {"configured": configured,
                "can_setup": not configured and is_this_machine(client_ip(request)),
                "authed": ctx.auth.check(bearer(authorization))}

    @r.post("/setup")
    async def setup(body: PasswordIn, request: Request):
        # First run: only the machine itself may claim the service, never another device on the LAN.
        if not is_this_machine(client_ip(request)):
            raise HTTPException(403, "open BrainSync on this computer (localhost) to set the first password")
        token = guarded(lambda: ctx.auth.setup(body.password))
        ctx.state.audit("password-set")
        return {"token": token}

    @r.post("/login")
    async def login(body: PasswordIn, request: Request):
        return {"token": guarded(lambda: ctx.auth.login(body.password, client_ip(request)))}

    @r.post("/logout")
    async def logout(authorization: str = Header("")):
        ctx.auth.logout(bearer(authorization))
        return {"ok": True}

    @r.post("/password")
    async def change(body: ChangeIn, request: Request, authorization: str = Header("")):
        if not ctx.auth.check(bearer(authorization)):
            raise HTTPException(401, "login required")
        token = guarded(lambda: ctx.auth.change_password(body.current, body.new, client_ip(request)))
        ctx.state.audit("password-changed")
        return {"token": token}

    return r
