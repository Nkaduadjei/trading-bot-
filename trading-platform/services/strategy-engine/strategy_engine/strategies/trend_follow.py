from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TrendFollow:
    """Hold when the fast moving average is above the slow one, otherwise stay flat.

    `positions(prices)[t]` uses prices up to and including day t only. The backtester
    applies it from day t+1, so there is no lookahead.
    """

    fast: int = 20
    slow: int = 100

    def __post_init__(self):
        if not 0 < self.fast < self.slow:
            raise ValueError("need 0 < fast < slow")

    @property
    def warmup(self):
        return self.slow

    def positions(self, prices: pd.Series) -> pd.Series:
        fast = prices.rolling(self.fast).mean()
        slow = prices.rolling(self.slow).mean()
        pos = (fast > slow).astype(float)
        pos[slow.isna()] = 0.0
        return pos
