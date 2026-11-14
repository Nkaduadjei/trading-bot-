"""Price data loading. Returns a pandas Series of closing prices indexed by date."""
import numpy as np
import pandas as pd


def load_csv(path, date_col="Date", price_col="Close"):
    """Load daily closes from a CSV (columns Date, Close by default)."""
    df = pd.read_csv(path, parse_dates=[date_col]).sort_values(date_col)
    s = df.set_index(date_col)[price_col].astype(float).dropna()
    s = s[~s.index.duplicated(keep="last")]
    if s.empty or (s <= 0).any():
        raise ValueError("prices must be non-empty and positive")
    s.name = "Close"
    return s


def synthetic_prices(n=2500, seed=7, drift=0.0003, vol=0.01, start=100.0):
    """A random walk. It has NO tradable pattern, which makes it a useful honesty check:
    a sound backtest should find no reliable edge here."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    idx = pd.bdate_range("2012-01-02", periods=n)
    return pd.Series(start * np.exp(np.cumsum(rets)), index=idx, name="Close")
