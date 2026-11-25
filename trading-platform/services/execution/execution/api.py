import hmac
import logging
import math
import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from .approval import ApprovalError, verify
from .paper import PaperBroker
from .store import Store

log = logging.getLogger("execution.api")


class ApprovalIn(BaseModel):
    order: dict
    approved_at: int
    signature: str


class PriceIn(BaseModel):
    price: float


def create_app(broker, approval_key: str, token: str, clock=time.time, max_age: int = 30,
               store: Optional[Store] = None) -> FastAPI:
    if len(approval_key) < 32 or len(token) < 32:
        raise ValueError("APPROVAL_KEY and EXECUTION_TOKEN must be at least 32 characters")
    store = store or Store("sqlite://", clock)
    app = FastAPI(title="execution")
    app.state.broker, app.state.store = broker, store

    def internal(x_internal_token: Optional[str] = Header(None)):
        if not x_internal_token or not hmac.compare_digest(x_internal_token, token):
            raise HTTPException(401, "internal token required")

    def read_account() -> dict:
        try:
            return broker.account()
        except Exception as e:  # e.g. a held symbol has no price: refuse rather than guess
            log.warning("account unavailable: %s", type(e).__name__)
            raise HTTPException(503, "account unavailable")

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": type(broker).__name__}

    @app.get("/account", dependencies=[Depends(internal)])
    def account():
        return read_account()

    @app.post("/orders", dependencies=[Depends(internal)])
    def place(body: ApprovalIn):
        try:
            req = verify(approval_key, body.model_dump(), clock(), max_age)
        except ApprovalError as e:
            log.warning("approval rejected: %s", e)
            raise HTTPException(403, f"approval rejected: {e}")

        # 1. Write the order down BEFORE touching the broker. A replay of the same approval, even
        #    after a restart, finds it here and never creates a second order.
        stored, created = store.begin_order(req, body.approved_at, body.signature)
        if not created and stored["status"] != "submitted":
            return stored

        # 2. Send it (the broker is idempotent by client_order_id too), then finish the record.
        order = broker.submit(req)
        try:
            snapshot = broker.account()
        except Exception:
            snapshot = None
        return store.complete_order(req.client_order_id, order, snapshot)

    @app.get("/orders", dependencies=[Depends(internal)])
    def orders(limit: int = Query(50, ge=1, le=500)):
        return store.orders(limit)

    @app.get("/trades", dependencies=[Depends(internal)])
    def trades(limit: int = Query(50, ge=1, le=500)):
        return store.fills(limit)

    @app.get("/equity", dependencies=[Depends(internal)])
    def equity(limit: int = Query(500, ge=1, le=5000)):
        return store.equity(limit)

    @app.post("/snapshot", dependencies=[Depends(internal)])
    def snapshot():
        acct = read_account()
        store.snapshot(acct)
        return {"equity": acct["equity"], "recorded": True}

    if isinstance(broker, PaperBroker):
        @app.put("/paper/prices/{symbol}", dependencies=[Depends(internal)])
        def set_price(symbol: str, body: PriceIn):
            if not math.isfinite(body.price) or body.price <= 0:
                raise HTTPException(422, "price must be positive")
            broker.set_price(symbol, body.price)
            store.set_price(symbol, body.price)    # remembered, so a restart does not lose it
            return {"symbol": symbol, "price": body.price}

    return app
