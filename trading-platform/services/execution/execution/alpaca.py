import logging
from typing import Optional

import requests

from .models import Order, OrderRequest

log = logging.getLogger("execution.alpaca")
PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"


class AlpacaBroker:
    """Alpaca REST client. Defaults to the PAPER endpoint.

    Written from Alpaca's public API docs and tested only against a mock here.
    Test it against a real paper account before trusting it.
    """

    def __init__(self, key, secret, live=False, session=None, retries=3, timeout=10):
        if not key or not secret:
            raise ValueError("Alpaca key and secret are required")
        self.base = LIVE_URL if live else PAPER_URL
        self.s = session or requests.Session()
        self.s.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        self.retries, self.timeout = retries, timeout

    def _call(self, method, path, **kw):
        return self.s.request(method, self.base + path, timeout=self.timeout, **kw)

    @staticmethod
    def _order(j) -> Order:
        px = j.get("filled_avg_price")
        return Order(j["id"], j["client_order_id"], j["symbol"], j["side"], float(j["qty"]),
                     j["status"], float(px) if px else None)

    def get_order(self, client_order_id) -> Optional[Order]:
        r = self._call("GET", "/v2/orders:by_client_order_id",
                       params={"client_order_id": client_order_id})
        return self._order(r.json()) if r.status_code == 200 else None

    def submit(self, req: OrderRequest) -> Order:
        body = dict(symbol=req.symbol, qty=str(req.qty), side=req.side, type="market",
                    time_in_force="day", client_order_id=req.client_order_id)
        for attempt in range(1, self.retries + 1):
            try:
                r = self._call("POST", "/v2/orders", json=body)
                if r.status_code in (200, 201):
                    return self._order(r.json())
                existing = self.get_order(req.client_order_id)   # duplicate id? return the original
                if existing:
                    return existing
                log.warning("order rejected (%s): %s", r.status_code, r.text[:200])
                return Order("", req.client_order_id, req.symbol, req.side, req.qty,
                             "rejected", reason=f"HTTP {r.status_code}")
            except requests.RequestException as e:
                log.warning("attempt %d failed: %s", attempt, e)
                # The order may have reached the broker before the connection dropped. Check
                # by client_order_id before retrying so we never send it twice.
                try:
                    existing = self.get_order(req.client_order_id)
                    if existing:
                        return existing
                except requests.RequestException:
                    pass
        return Order("", req.client_order_id, req.symbol, req.side, req.qty,
                     "rejected", reason="broker unreachable")

    def cancel(self, client_order_id) -> bool:
        o = self.get_order(client_order_id)
        return bool(o) and self._call("DELETE", f"/v2/orders/{o.id}").status_code in (200, 204)

    def positions(self) -> dict:
        r = self._call("GET", "/v2/positions")
        r.raise_for_status()
        return {p["symbol"]: float(p["qty"]) for p in r.json()}

    def account(self) -> dict:
        """Equity and cash from /v2/account; positions and their prices from /v2/positions.
        Prices exist only for symbols you hold. A price source for NEW symbols is not built yet."""
        a = self._call("GET", "/v2/account")
        a.raise_for_status()
        p = self._call("GET", "/v2/positions")
        p.raise_for_status()
        rows = p.json()
        return {"equity": float(a.json()["equity"]), "cash": float(a.json()["cash"]),
                "positions": {r["symbol"]: float(r["qty"]) for r in rows},
                "prices": {r["symbol"]: float(r["current_price"]) for r in rows}}
