import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import audit
from .config import Settings
from .ratelimit import RateLimiter

log = logging.getLogger("admin")
STATIC = Path(__file__).parent / "static"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
USER_FIELDS = ("id", "email", "totp_enabled", "created_at", "locked")


class LoginIn(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None


class ReasonIn(BaseModel):
    reason: str = Field(default="admin request", min_length=1, max_length=200)


def create_app(settings: Settings, transport=None) -> FastAPI:
    app = FastAPI(title="admin-console", docs_url=None, redoc_url=None, openapi_url=None)
    limiter = RateLimiter(settings.clock)

    def client(url):
        return httpx.AsyncClient(base_url=url, timeout=settings.upstream_timeout, transport=transport)

    auth, risk = client(settings.auth_url), client(settings.risk_url)
    pings = {"gateway": client(settings.gateway_url), "auth": auth, "risk manager": risk,
             "execution": client(settings.execution_url)}
    risk_h = {"X-Internal-Token": settings.risk_token}

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.headers.get("host", "") not in settings.allowed_hosts:  # blocks DNS-rebinding tricks
            return JSONResponse({"detail": "host not allowed"}, 421)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    async def admin(authorization: Optional[str] = Header(None)) -> dict:
        if not authorization:
            raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        try:
            r = await auth.get("/me", headers={"Authorization": authorization})
        except httpx.HTTPError:
            raise HTTPException(503, "authentication service unavailable")
        if r.status_code != 200:
            raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        user = r.json()
        if str(user.get("email", "")).lower() not in settings.admin_emails:
            log.warning("admin access refused for user id=%s", user.get("id"))
            raise HTTPException(403, "not an admin")
        return user

    def note(user, action, detail=""):
        audit.record(settings.audit_path, settings.clock(), user["email"], action, detail)

    # ---- the page itself (static files, no secrets in them) ----
    for route, name, kind in (("/", "index.html", "text/html"), ("/app.js", "app.js", "text/javascript"),
                              ("/style.css", "style.css", "text/css")):
        def make(file=name, media=kind):
            async def serve():
                return Response((STATIC / file).read_bytes(), media_type=media)
            return serve
        app.get(route, include_in_schema=False)(make())

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/login")
    async def login(body: LoginIn, request: Request):
        ip = request.client.host if request.client else "unknown"
        wait = limiter.check(ip, settings.login_rate_per_min)
        if wait is not None:
            return JSONResponse({"detail": "too many attempts"}, 429, headers={"Retry-After": str(int(wait) + 1)})
        try:
            r = await auth.post("/auth/login", json=body.model_dump())
        except httpx.HTTPError:
            raise HTTPException(502, "service unavailable")
        return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))

    @app.get("/api/health")
    async def services(user: dict = Depends(admin)):
        async def ping(name, c):
            try:
                return name, (await c.get("/health")).status_code == 200
            except httpx.HTTPError:
                return name, False
        results = await asyncio.gather(*(ping(n, c) for n, c in pings.items()))
        return {"services": {n: "up" if ok else "down" for n, ok in results}}

    async def kill_call(method, path, user, json=None):
        try:
            r = await risk.request(method, path, headers=risk_h, json=json)
        except httpx.HTTPError:
            raise HTTPException(502, "risk manager unreachable, so the kill switch state is UNKNOWN")
        if r.status_code != 200:
            raise HTTPException(502, "risk manager refused the request")
        return r.json()

    @app.get("/api/kill")
    async def kill_status(user: dict = Depends(admin)):
        return await kill_call("GET", "/kill", user)

    @app.post("/api/kill/engage")
    async def kill_engage(body: ReasonIn, user: dict = Depends(admin)):
        out = await kill_call("POST", "/kill/engage", user, {"reason": f"{user['email']}: {body.reason}"})
        note(user, "kill_engage", body.reason)
        return out

    @app.post("/api/kill/release")
    async def kill_release(user: dict = Depends(admin)):
        out = await kill_call("POST", "/kill/release", user)
        note(user, "kill_release")
        return out

    @app.get("/api/users")
    async def users(user: dict = Depends(admin)):
        try:
            r = await auth.get("/internal/users", headers={"X-Internal-Token": settings.auth_admin_token})
        except httpx.HTTPError:
            raise HTTPException(502, "auth service unreachable")
        if r.status_code != 200:
            raise HTTPException(502, "auth service refused the request")
        note(user, "list_users")
        return [{k: u.get(k) for k in USER_FIELDS} for u in r.json()]   # only these fields, ever

    @app.get("/api/audit")
    async def recent(user: dict = Depends(admin)):
        return audit.tail(settings.audit_path)

    return app
