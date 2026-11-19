from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AccountState:
    equity: float
    start_of_day_equity: float
    peak_equity: float
    positions: dict = field(default_factory=dict)  # symbol -> quantity held
    prices: dict = field(default_factory=dict)     # symbol -> last price


@dataclass(frozen=True)
class ProposedOrder:
    symbol: str
    side: str                      # "buy" or "sell"
    qty: float
    price: float                   # reference price used for sizing
    stop_price: Optional[float] = None  # required for buys


@dataclass(frozen=True)
class Decision:
    approved: bool
    order: Optional[dict]          # matches contracts/order.schema.json when approved
    reasons: list
