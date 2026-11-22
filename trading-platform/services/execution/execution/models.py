from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str   # unique per order; the same id twice never makes two orders
    symbol: str
    side: str              # "buy" or "sell"
    qty: float

    def __post_init__(self):
        if self.side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if len(self.client_order_id) < 8:
            raise ValueError("client_order_id too short to be unique")


@dataclass
class Order:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    status: str                          # "filled", "rejected", "canceled", "open"
    filled_price: Optional[float] = None
    reason: str = ""


class Broker(Protocol):
    def submit(self, req: OrderRequest) -> Order: ...
    def get_order(self, client_order_id: str) -> Optional[Order]: ...
    def cancel(self, client_order_id: str) -> bool: ...
    def positions(self) -> dict: ...
    def account(self) -> dict: ...  # equity, cash, positions, prices
