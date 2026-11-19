from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Costs:
    """Charged on every change of position, as basis points of the traded amount."""

    commission_bps: float = 5.0
    slippage_bps: float = 5.0

    @property
    def per_unit(self) -> float:
        return (self.commission_bps + self.slippage_bps) / 10_000


@dataclass(frozen=True)
class BacktestResult:
    returns: pd.Series    # daily strategy returns after costs
    positions: pd.Series  # position actually held each day (target shifted by one day)

    @property
    def equity(self) -> pd.Series:
        return (1 + self.returns).cumprod()

    @property
    def trades(self) -> int:
        return int((self.positions.diff().abs().fillna(self.positions.abs()) > 0).sum())


def run_backtest(prices: pd.Series, strategy, costs: Costs = Costs()) -> BacktestResult:
    """Simulate a long/flat strategy on daily closes.

    Target decided at the close of day t is held during day t+1 (no lookahead).
    Each change in position pays `costs.per_unit` times the size of the change.
    """
    asset_ret = prices.pct_change().fillna(0.0)
    held = strategy.positions(prices).shift(1).fillna(0.0)
    turnover = held.diff().abs().fillna(held.abs())
    returns = held * asset_ret - turnover * costs.per_unit
    return BacktestResult(returns=returns, positions=held)
