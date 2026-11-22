import hmac
import math
import time
from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .approval import ApprovalError, verify
from .paper import PaperBroker


class ApprovalIn(BaseModel):
    order: dict
    approved_at: int
    signature: str


class PriceIn(BaseModel):
    price: float


def create_app(broker, approval_key: str, token: str, clock=time.time, max_age: int = 30) -> FastAPI:
    if len(approval_key) < 32 or len(token) < 32:
        raise ValueError("APPROVAL_KEY and EXECUTION_TOKEN must be at least 32 characters")
    app = FastAPI(title="execution")
    app.state.broker = broker

    def internal(x_internal_token: Optional[str] = Header(None)):
        if not x_internal_token or not hmac.compare_digest(x_internal_token, token):
            raise HTTPException(401, "internal token required")

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": type(broker).__name__}

    @app.get("/account", dependencies=[Depends(internal)])
    def account():
        return broker.account()

    @app.post("/orders", dependencies=[Depends(internal)])
    def place(body: ApprovalIn):
        try:
            req = verify(approval_key, body.model_dump(), clock(), max_age)
        except ApprovalError as e:
            raise HTTPException(403, f"approval rejected: {e}")
        return asdict(broker.submit(req))

    if isinstance(broker, PaperBroker):
        @app.put("/paper/prices/{symbol}", dependencies=[Depends(internal)])
        def set_price(symbol: str, body: PriceIn):
            if not math.isfinite(body.price) or body.price <= 0:
                raise HTTPException(422, "price must be positive")
            broker.set_price(symbol, body.price)
            return {"symbol": symbol, "price": body.price}

    return app
