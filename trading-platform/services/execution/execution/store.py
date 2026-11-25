import json
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import EquityRow, FillRow, MetaRow, OrderRow, PriceRow, make_session_factory
from .models import Order, OrderRequest


def _order(r: OrderRow) -> dict:
    return dict(id=r.broker_order_id, client_order_id=r.client_order_id, symbol=r.symbol, side=r.side,
                qty=r.qty, status=r.status, filled_price=r.filled_price, reason=r.reason,
                approved_at=r.approved_at, created_at=r.created_at, updated_at=r.updated_at)


class Store:
    def __init__(self, url: str = "sqlite://", clock=time.time):
        self.S, self.clock = make_session_factory(url), clock

    # ---- orders: written BEFORE the broker is called, finished after ----
    def begin_order(self, req: OrderRequest, approved_at: int, signature: str):
        """Returns (order, created). If the client_order_id is already stored, created is False."""
        with self.S() as db:
            q = select(OrderRow).where(OrderRow.client_order_id == req.client_order_id)
            row = db.scalar(q)
            if row:
                return _order(row), False
            now = self.clock()
            db.add(OrderRow(client_order_id=req.client_order_id, symbol=req.symbol, side=req.side,
                            qty=req.qty, status="submitted", reason="", approved_at=approved_at,
                            approval_signature=signature, created_at=now, updated_at=now))
            try:
                db.commit()
            except IntegrityError:           # another request stored the same id a moment ago
                db.rollback()
                return _order(db.scalar(q)), False
            return _order(db.scalar(q)), True

    def complete_order(self, client_order_id: str, order: Order, account: Optional[dict]):
        with self.S() as db:
            row = db.scalar(select(OrderRow).where(OrderRow.client_order_id == client_order_id))
            now = self.clock()
            status, reason = order.status, order.reason or ""
            if status == "rejected" and reason == "broker unreachable":
                status = "submitted"         # outcome unknown: a retry of this approval must be allowed
            row.status, row.reason, row.updated_at = status, reason[:200], now
            row.broker_order_id, row.filled_price = order.id or None, order.filled_price
            has_fill = db.scalar(select(FillRow).where(FillRow.order_id == row.id))
            if status == "filled" and order.filled_price is not None and not has_fill:
                db.add(FillRow(order_id=row.id, symbol=row.symbol, side=row.side, qty=row.qty,
                                price=order.filled_price, created_at=now))
            if account is not None:
                db.add(EquityRow(created_at=now, equity=float(account["equity"]), cash=float(account["cash"]),
                                 positions=json.dumps(account["positions"], sort_keys=True)))
            db.commit()
            return _order(row)

    # ---- reading history ----
    def orders(self, limit: int = 50) -> list:
        with self.S() as db:
            return [_order(r) for r in db.scalars(select(OrderRow).order_by(OrderRow.id.desc()).limit(limit))]

    def fills(self, limit: int = 50) -> list:
        with self.S() as db:
            rows = db.scalars(select(FillRow).order_by(FillRow.id.desc()).limit(limit))
            return [dict(id=r.id, order_id=r.order_id, symbol=r.symbol, side=r.side, qty=r.qty,
                         price=r.price, created_at=r.created_at) for r in rows]

    def equity(self, limit: int = 500) -> list:
        with self.S() as db:
            rows = list(db.scalars(select(EquityRow).order_by(EquityRow.id.desc()).limit(limit)))[::-1]
            return [dict(created_at=r.created_at, equity=r.equity, cash=r.cash,
                         positions=json.loads(r.positions)) for r in rows]

    def snapshot(self, account: dict):
        with self.S() as db:
            db.add(EquityRow(created_at=self.clock(), equity=float(account["equity"]), cash=float(account["cash"]),
                             positions=json.dumps(account["positions"], sort_keys=True)))
            db.commit()

    # ---- what the paper account needs to rebuild itself ----
    def set_price(self, symbol: str, price: float):
        with self.S() as db:
            row = db.get(PriceRow, symbol)
            if row:
                row.price, row.updated_at = price, self.clock()
            else:
                db.add(PriceRow(symbol=symbol, price=price, updated_at=self.clock()))
            db.commit()

    def prices(self) -> dict:
        with self.S() as db:
            return {r.symbol: r.price for r in db.scalars(select(PriceRow))}

    def replay_fills(self):
        with self.S() as db:
            return [(r.symbol, r.side, r.qty, r.price) for r in db.scalars(select(FillRow).order_by(FillRow.id))]

    def get_meta(self, key: str) -> Optional[str]:
        with self.S() as db:
            row = db.get(MetaRow, key)
            return row.value if row else None

    def set_meta(self, key: str, value: str):
        with self.S() as db:
            row = db.get(MetaRow, key)
            if row:
                row.value = value
            else:
                db.add(MetaRow(key=key, value=value))
            db.commit()
