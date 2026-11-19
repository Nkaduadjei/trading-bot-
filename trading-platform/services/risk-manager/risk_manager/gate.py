import math
import uuid

from .config import RiskConfig
from .killswitch import KillSwitch
from .models import AccountState, Decision, ProposedOrder


def _ok(*nums):
    return all(isinstance(n, (int, float)) and math.isfinite(n) for n in nums)


class RiskManager:
    def __init__(self, config: RiskConfig = RiskConfig(), kill: KillSwitch = None):
        self.cfg, self.kill = config, kill or KillSwitch()

    def check(self, o: ProposedOrder, st: AccountState) -> Decision:
        """Approve (possibly resized) or reject. Any error or bad input means reject."""
        try:
            return self._check(o, st)
        except Exception as e:
            return Decision(False, None, [f"rejected, check failed safely: {e}"])

    def _reject(self, *why):
        return Decision(False, None, list(why))

    def _approve(self, o, qty, reasons):
        order = dict(client_order_id=uuid.uuid4().hex, symbol=o.symbol, side=o.side, qty=qty)
        return Decision(True, order, reasons)

    def _check(self, o, st):
        if not _ok(o.qty, o.price, st.equity, st.start_of_day_equity, st.peak_equity):
            return self._reject("bad numbers in order or account state")
        if st.equity <= 0 or o.price <= 0 or o.qty <= 0:
            return self._reject("equity, price and quantity must be positive")
        if o.side not in ("buy", "sell"):
            return self._reject("side must be buy or sell")

        # Automatic latch: a deep drawdown halts new risk until a human releases it.
        if st.equity <= st.peak_equity * (1 - self.cfg.max_drawdown) and not self.kill.engaged:
            self.kill.engage(f"max drawdown {self.cfg.max_drawdown:.0%} reached")

        if o.side == "sell":
            return self._sell(o, st)
        return self._buy(o, st)

    def _sell(self, o, st):
        held = st.positions.get(o.symbol, 0.0)  # reducing risk is always allowed, even when halted
        if held <= 0:
            return self._reject(f"nothing to sell in {o.symbol} (no shorting)")
        qty = min(o.qty, held)
        why = [f"sell capped from {o.qty:g} to {qty:g}: only {held:g} held"] if qty < o.qty else []
        return self._approve(o, qty, why)

    def _buy(self, o, st):
        c = self.cfg
        if self.kill.engaged:
            return self._reject(f"trading halted: {self.kill.reason}")
        if st.equity <= st.start_of_day_equity * (1 - c.daily_loss_limit):
            return self._reject(f"daily loss limit {c.daily_loss_limit:.0%} reached")
        if o.stop_price is None or not _ok(o.stop_price) or not 0 < o.stop_price < o.price:
            return self._reject("a buy needs a stop price below the entry price")

        held = st.positions.get(o.symbol, 0.0)
        exposure = sum(q * st.prices[s] for s, q in st.positions.items())
        limits = {
            "max risk per trade": c.max_risk_per_trade * st.equity / (o.price - o.stop_price),
            "max position size": max(0.0, c.max_position_pct * st.equity / o.price - held),
            "max total exposure": max(0.0, (c.max_exposure_pct * st.equity - exposure) / o.price),
        }
        rule, cap = min(limits.items(), key=lambda kv: kv[1])
        qty = min(o.qty, cap)
        if c.whole_shares:
            qty = math.floor(qty)
        if qty <= 0:
            return self._reject(f"size is zero after limits (tightest: {rule})")
        why = [f"resized from {o.qty:g} to {qty:g}: {rule}"] if qty < o.qty else []
        return self._approve(o, qty, why)
