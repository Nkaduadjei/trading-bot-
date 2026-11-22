import logging
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .ratelimit import RateLimiter

log = logging.getLogger("gateway")
KEEP = ("retry-after", "www-authenticate")   # the only upstream headers passed back to callers


class OrderIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{1,10}$")
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    stop_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)


def create_app(settings: Settings, transport=None) -> FastAPI:
    app = FastAPI(title="api-gateway")
    limiter = RateLimiter(settings.clock)

    def client(url):
        return httpx.AsyncClient(base_url=url, timeout=settings.upstream_timeout, transport=transport)

    auth, risk, execu = client(settings.auth_url), client(settings.risk_url), client(settings.execution_url)
    risk_h = {"X-Internal-Token": settings.risk_token}
    exec_h = {"X-Internal-Token": settings.execution_token}

    @app.middleware("http")
    async def guard(request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        strict = request.url.path in ("/auth/login", "/auth/register")
        wait = limiter.check(("auth" if strict else "all", ip),
                             settings.auth_rate_limit_per_min if strict else settings.rate_limit_per_min)
        if wait is not None:
            return JSONResponse({"detail": "too many requests"}, 429,
                                headers={"Retry-After": str(int(wait) + 1)})
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > settings.max_body_bytes:
            return JSONResponse({"detail": "request too large"}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    async def forward(method: str, path: str, request: Request, body: bool = True) -> Response:
        """Pass one whitelisted request to the auth service and return its answer."""
        headers, content = {}, None
        if "authorization" in request.headers:
            headers["Authorization"] = request.headers["authorization"]
        if body:
            content = await request.body()
            if len(content) > settings.max_body_bytes:
                raise HTTPException(413, "request too large")
            headers["Content-Type"] = request.headers.get("content-type", "application/json")
        try:
            r = await auth.request(method, path, content=content, headers=headers)
        except httpx.HTTPError as e:
            log.warning("auth service unreachable: %s", type(e).__name__)
            raise HTTPException(502, "service unavailable")
        keep = {k: v for k, v in r.headers.items() if k.lower() in KEEP}
        return Response(r.content, r.status_code, headers=keep, media_type=r.headers.get("content-type"))

    async def trader(authorization: Optional[str] = Header(None)) -> dict:
        """Logged in (checked with the auth service) AND on the trader allowlist."""
        if not authorization:
            raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        try:
            r = await auth.get("/me", headers={"Authorization": authorization})
        except httpx.HTTPError:
            raise HTTPException(503, "authentication service unavailable")
        if r.status_code != 200:
            raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
        user = r.json()
        if str(user.get("email", "")).lower() not in settings.trader_emails:
            log.info("trading refused for user id=%s: not on the trader list", user.get("id"))
            raise HTTPException(403, "this account is not allowed to trade")
        return user

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # ---- account routes: forwarded to the auth service, nothing else is reachable ----
    @app.post("/auth/register")
    async def register(request: Request):
        return await forward("POST", "/auth/register", request)

    @app.post("/auth/login")
    async def login(request: Request):
        return await forward("POST", "/auth/login", request)

    @app.get("/me")
    async def me(request: Request):
        return await forward("GET", "/me", request, body=False)

    @app.post("/auth/2fa/setup")
    async def setup_2fa(request: Request):
        return await forward("POST", "/auth/2fa/setup", request, body=False)

    @app.post("/auth/2fa/enable")
    async def enable_2fa(request: Request):
        return await forward("POST", "/auth/2fa/enable", request)

    @app.post("/broker-keys")
    async def add_key(request: Request):
        return await forward("POST", "/broker-keys", request)

    @app.get("/broker-keys")
    async def list_keys(request: Request):
        return await forward("GET", "/broker-keys", request, body=False)

    @app.delete("/broker-keys/{key_id}")
    async def delete_key(key_id: int, request: Request):
        return await forward("DELETE", f"/broker-keys/{key_id}", request, body=False)

    # ---- trading ----
    @app.get("/account")
    async def account(user: dict = Depends(trader)):
        try:
            r = await execu.get("/account", headers=exec_h)
        except httpx.HTTPError:
            raise HTTPException(503, "trading service unavailable")
        if r.status_code != 200:
            raise HTTPException(502, "trading service error")
        return r.json()

    @app.post("/orders")
    async def place_order(body: OrderIn, user: dict = Depends(trader)):
        # 1. ask the risk manager. It reads the account and price itself and signs what it approves.
        try:
            ev = await risk.post("/evaluate", headers=risk_h, json=body.model_dump())
        except httpx.HTTPError:
            raise HTTPException(503, "risk manager unavailable, so no order was placed")
        if ev.status_code == 503:
            raise HTTPException(503, "risk manager could not verify the account, so no order was placed")
        if ev.status_code != 200:
            raise HTTPException(502, "risk manager error, so no order was placed")
        verdict = ev.json()
        if not verdict.get("approved"):
            return {"approved": False, "reasons": verdict.get("reasons", [])}
        approval = verdict.get("approval")
        if not isinstance(approval, dict):
            raise HTTPException(502, "risk manager answer was malformed, so no order was placed")

        # 2. forward the SIGNED approval, untouched. Execution is idempotent by client_order_id,
        #    so one retry after a dropped connection can never create a second order.
        res = None
        for attempt in (1, 2):
            try:
                res = await execu.post("/orders", headers=exec_h, json=approval)
                break
            except httpx.TransportError:
                if attempt == 2:
                    raise HTTPException(503, "trading service unreachable, order status unknown: check /account")
        if res.status_code != 200:
            log.warning("execution refused an approved order: HTTP %s", res.status_code)
            raise HTTPException(502, "trading service refused the order")
        log.info("order placed for user id=%s", user.get("id"))
        return {"approved": True, "reasons": verdict.get("reasons", []), "order": res.json()}

    return app
