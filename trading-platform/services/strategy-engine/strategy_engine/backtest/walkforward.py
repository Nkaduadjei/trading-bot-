from dataclasses import dataclass
from itertools import product

import pandas as pd

from ..strategies import TrendFollow
from .engine import Costs, run_backtest
from .metrics import summarize

DEFAULT_GRID = [(f, s) for f, s in product((10, 20, 50), (100, 150, 200))]


@dataclass(frozen=True)
class WalkForwardResult:
    folds: list              # one dict per fold: params, in-sample and out-of-sample Sharpe
    oos_returns: pd.Series   # stitched out-of-sample returns (the only ones to trust)
    in_sample_sharpe: float  # average Sharpe of the chosen params on their own training data
    oos: dict                # summarize() of the stitched out-of-sample returns


def walk_forward(prices, grid=DEFAULT_GRID, train_len=756, test_len=252,
                 costs: Costs = Costs()) -> WalkForwardResult:
    """Pick parameters on a training window, then trade the NEXT window with them. Roll forward.

    Parameters never see the data they are judged on.
    """
    folds, parts, trades = [], [], 0
    start = 0
    while start + train_len + test_len <= len(prices):
        train = prices.iloc[start:start + train_len]
        te0, te1 = start + train_len, start + train_len + test_len

        scored = []
        for fast, slow in grid:
            r = run_backtest(train, TrendFollow(fast, slow), costs)
            scored.append((summarize(r.returns, r.trades)["sharpe"], (fast, slow)))
        is_sharpe, (fast, slow) = max(scored)

        strat = TrendFollow(fast, slow)
        lo = max(0, te0 - strat.warmup)  # warm-up so averages exist on the first test day
        r = run_backtest(prices.iloc[lo:te1], strat, costs)
        test_idx = prices.index[te0:te1]
        oos_ret = r.returns.loc[test_idx]
        parts.append(oos_ret)
        trades += int((r.positions.loc[test_idx].diff().abs().fillna(0) > 0).sum())

        folds.append(dict(train=(train.index[0], train.index[-1]),
                          test=(test_idx[0], test_idx[-1]), params=(fast, slow),
                          is_sharpe=is_sharpe,
                          oos_sharpe=summarize(oos_ret)["sharpe"]))
        start += test_len

    if not folds:
        raise ValueError("not enough data for one train+test window")
    oos_returns = pd.concat(parts)
    return WalkForwardResult(
        folds=folds, oos_returns=oos_returns,
        in_sample_sharpe=sum(f["is_sharpe"] for f in folds) / len(folds),
        oos=summarize(oos_returns, trades))


def promotion_check(wf: WalkForwardResult, min_oos_sharpe=0.3, min_ratio=0.5,
                    max_drawdown=-0.35, min_trades=10, min_folds=3):
    """The gate to paper trading. Returns (passed, reasons_it_failed)."""
    why = []
    o = wf.oos
    if len(wf.folds) < min_folds:
        why.append(f"only {len(wf.folds)} folds; need {min_folds}")
    if o["sharpe"] < min_oos_sharpe:
        why.append(f"out-of-sample Sharpe {o['sharpe']:.2f} < {min_oos_sharpe}")
    if wf.in_sample_sharpe > 0 and o["sharpe"] < min_ratio * wf.in_sample_sharpe:
        why.append("out-of-sample Sharpe is less than half the in-sample Sharpe (likely overfit)")
    if o["max_drawdown"] < max_drawdown:
        why.append(f"max drawdown {o['max_drawdown']:.0%} is worse than {max_drawdown:.0%}")
    if o["trades"] < min_trades:
        why.append(f"only {o['trades']} trades; too few to judge")
    return (not why), why
