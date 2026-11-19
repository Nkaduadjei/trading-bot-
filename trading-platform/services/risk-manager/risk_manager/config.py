from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """All limits are fractions of account equity."""

    max_risk_per_trade: float = 0.01  # most you may lose if the stop is hit
    max_position_pct: float = 0.25    # largest single position
    max_exposure_pct: float = 1.0     # total invested; 1.0 means no leverage
    daily_loss_limit: float = 0.02    # no new buys for the rest of the day after this loss
    max_drawdown: float = 0.10        # from the equity peak; halts until a human releases it
    min_trade_pct: float = 0.005      # ignore rebalances smaller than this, to avoid churn
    whole_shares: bool = True

    def __post_init__(self):
        for name in ("max_risk_per_trade", "max_position_pct", "max_exposure_pct",
                     "daily_loss_limit", "max_drawdown"):
            v = getattr(self, name)
            if not 0 < v <= 1:
                raise ValueError(f"{name} must be in (0, 1], got {v}")
