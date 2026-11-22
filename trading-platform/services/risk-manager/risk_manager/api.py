import hmac
import time
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .approval import make_approval
from .config import RiskConfig
from .gate import RiskManager
from .killswitch import KillSwitch
from .models import AccountState, ProposedOrder
from .state import StateStore


class EvaluateIn(BaseModel):
    symbol: str
    side: str
    qty: float
    stop_price: Optional[float] = None   # note: NO price field. The price comes from execution.


class ReasonIn(BaseModel):
    reason: str = "operator request"


def http_account_fetcher(url: str, token: str, timeout: float = 5.0):
    def fetch() -> dict:
        r = httpx.get(url.rstrip("/") + "/account", headers={"X-Internal-Token": token},
                      timeout=timeout)
        r.raise_for_status()
        return r.json()
    return fetch


def create_app(fetch_account, approval_key: str, token: str, config: RiskConfig = RiskConfig(),
               kill: KillSwitch = None, store: StateStore = None, clock=time.time) -> FastAPI:
    if len(approval_key) < 32 or len(token) < 32:
        raise ValueError("APPROVAL_KEY and RISK_TOKEN must be at least 32 characters")
    app = FastAPI(title="risk-manager")
    kill, store = kill or KillSwitch(), store or StateStore()
    rm = RiskManager(config, kill)
    app.state.kill = kill

    def internal(x_internal_token: Optional[str] = Header(None)):
        if not x_internal_token or not hmac.compare_digest(x_internal_token, token):
            raise HTTPException(401, "internal token required")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/evaluate", dependencies=[Depends(internal)])
    def evaluate(body: EvaluateIn):
        now = clock()
        try:  # account and price come from execution, never from the caller. Any failure = no.
            acct = fetch_account()
            sod, peak = store.update(float(acct["equity"]), now)
            state = AccountState(float(acct["equity"]), sod, peak, dict(acct["positions"]),
                                 dict(acct["prices"]))
            price = state.prices.get(body.symbol)
        except Exception:
            raise HTTPException(503, "cannot read the account, so no order can be approved")
        if price is None:
            return {"approved": False, "reasons": ["no market price for this symbol"]}
        d = rm.check(ProposedOrder(body.symbol, body.side, body.qty, price, body.stop_price), state)
        if not d.approved:
            return {"approved": False, "reasons": d.reasons}
        return {"approved": True, "reasons": d.reasons,
                "approval": make_approval(approval_key, d.order, now)}

    @app.get("/kill", dependencies=[Depends(internal)])
    def kill_status():
        return {"engaged": kill.engaged, "reason": kill.reason}

    @app.post("/kill/engage", dependencies=[Depends(internal)])
    def kill_engage(body: ReasonIn):
        kill.engage(body.reason)
        return {"engaged": True, "reason": kill.reason}

    @app.post("/kill/release", dependencies=[Depends(internal)])
    def kill_release():
        kill.release()
        return {"engaged": False}

    return app
