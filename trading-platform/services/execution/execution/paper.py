import logging
from itertools import count
from typing import Optional

from .models import Order, OrderRequest

log = logging.getLogger("execution.paper")


class PaperBroker:
    """Simulated broker. Market orders fill at the last known price, worse by slippage."""

    def __init__(self, cash=100_000.0, commission_bps=5.0, slippage_bps=5.0):
        self.cash = cash
        self.commission = commission_bps / 10_000
        self.slippage = slippage_bps / 10_000
        self._prices, self._orders, self._pos = {}, {}, {}
        self._ids = count(1)

    def set_price(self, symbol, price):
        self._prices[symbol] = price

    def submit(self, req: OrderRequest) -> Order:
        if req.client_order_id in self._orders:          # idempotent: same id, same order
            log.info("duplicate %s ignored", req.client_order_id)
            return self._orders[req.client_order_id]
        order = Order(f"paper-{next(self._ids)}", req.client_order_id, req.symbol,
                      req.side, req.qty, "rejected")
        last = self._prices.get(req.symbol)
        if last is None:
            order.reason = "no price for symbol"
        elif req.side == "buy":
            px = last * (1 + self.slippage)
            cost = req.qty * px * (1 + self.commission)
            if cost > self.cash:
                order.reason = "insufficient cash"
            else:
                self.cash -= cost
                self._pos[req.symbol] = self._pos.get(req.symbol, 0.0) + req.qty
                order.status, order.filled_price = "filled", px
        else:
            if self._pos.get(req.symbol, 0.0) < req.qty:
                order.reason = "insufficient position (no shorting in paper mode)"
            else:
                px = last * (1 - self.slippage)
                self.cash += req.qty * px * (1 - self.commission)
                self._pos[req.symbol] -= req.qty
                order.status, order.filled_price = "filled", px
        self._orders[req.client_order_id] = order
        log.info("order %s %s %s x%s -> %s %s", order.id, req.side, req.symbol, req.qty,
                 order.status, order.reason)
        return order

    def get_order(self, client_order_id) -> Optional[Order]:
        return self._orders.get(client_order_id)

    def cancel(self, client_order_id) -> bool:
        return False  # market orders fill instantly, so there is never an open order to cancel

    def positions(self) -> dict:
        return {s: q for s, q in self._pos.items() if q}

    def account(self) -> dict:
        equity = self.cash + sum(q * self._prices.get(s, 0.0) for s, q in self._pos.items())
        return {"equity": equity, "cash": self.cash, "positions": self.positions(),
                "prices": dict(self._prices)}
