from typing import Optional

from .config import RiskConfig
from .models import AccountState, ProposedOrder


def plan_order(signal: dict, st: AccountState, price: float, stop_price: Optional[float] = None,
               cfg: RiskConfig = RiskConfig()) -> Optional[ProposedOrder]:
    """Turn a signal (see contracts/signal.schema.json) into the order that would reach its target.

    The result is only a PROPOSAL. It still has to pass RiskManager.check.
    """
    symbol = signal["symbol"]
    target_qty = signal["target_position"] * st.equity / price
    delta = target_qty - st.positions.get(symbol, 0.0)
    if abs(delta) * price < cfg.min_trade_pct * st.equity:
        return None  # too small to be worth the costs
    side = "buy" if delta > 0 else "sell"
    return ProposedOrder(symbol, side, abs(delta), price, stop_price if side == "buy" else None)
