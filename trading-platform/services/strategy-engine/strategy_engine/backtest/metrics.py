import numpy as np
import pandas as pd

PERIODS = 252  # trading days per year


def summarize(returns: pd.Series, trades: int = 0) -> dict:
    """Headline numbers for a series of daily returns."""
    if len(returns) < 2:
        return dict(total_return=0.0, cagr=0.0, sharpe=0.0, max_drawdown=0.0, trades=trades)
    equity = (1 + returns).cumprod()
    years = len(returns) / PERIODS
    final = float(equity.iloc[-1])
    std = returns.std(ddof=1)
    return dict(
        total_return=final - 1,
        cagr=final ** (1 / years) - 1 if final > 0 else -1.0,
        sharpe=float(returns.mean() / std * np.sqrt(PERIODS)) if std > 0 else 0.0,
        max_drawdown=float((equity / equity.cummax() - 1).min()),
        trades=trades,
    )
