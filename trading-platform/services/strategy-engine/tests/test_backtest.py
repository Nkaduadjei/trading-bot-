import numpy as np
import pandas as pd
import pytest

from strategy_engine.backtest import Costs, promotion_check, run_backtest, summarize, walk_forward
from strategy_engine.data import synthetic_prices
from strategy_engine.strategies import TrendFollow


def test_signal_ignores_the_future():
    """Changing prices after day t must not change the signal on or before day t."""
    p = synthetic_prices(n=400)
    q = p.copy()
    q.iloc[300:] *= 1.5
    s = TrendFollow(10, 50)
    pd.testing.assert_series_equal(s.positions(p).iloc[:300], s.positions(q).iloc[:300])


def test_position_is_delayed_one_day():
    p = synthetic_prices(n=400)
    s = TrendFollow(10, 50)
    held = run_backtest(p, s, Costs(0, 0)).positions
    assert (held.iloc[1:].values == s.positions(p).iloc[:-1].values).all()


def test_costs_reduce_returns():
    p = synthetic_prices(n=600)
    s = TrendFollow(10, 50)
    free = run_backtest(p, s, Costs(0, 0)).equity.iloc[-1]
    paid = run_backtest(p, s, Costs(10, 10)).equity.iloc[-1]
    assert paid < free


def test_zero_cost_buy_and_hold_matches_price_move():
    p = pd.Series([100.0, 110.0, 121.0], index=pd.bdate_range("2020-01-01", periods=3))

    class AlwaysLong:
        warmup = 0
        def positions(self, prices):
            return pd.Series(1.0, index=prices.index)

    r = run_backtest(p, AlwaysLong(), Costs(0, 0))
    # target set on day 1 is held from day 2, so it earns both +10% moves: 1.10 * 1.10
    assert r.equity.iloc[-1] == pytest.approx(1.21)


def test_max_drawdown_known_value():
    r = pd.Series([0.10, -0.20, 0.05])
    m = summarize(r)
    assert m["max_drawdown"] == pytest.approx(-0.20)


def test_walk_forward_test_windows_follow_training_windows():
    wf = walk_forward(synthetic_prices(n=2000))
    assert len(wf.folds) >= 3
    for f in wf.folds:
        assert f["train"][1] < f["test"][0]
    starts = [f["test"][0] for f in wf.folds]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert wf.oos_returns.index.is_unique


def test_random_walk_is_not_promoted():
    """Across several random seeds the gate should reject most strategies built on pure noise."""
    passed = sum(promotion_check(walk_forward(synthetic_prices(n=2500, seed=s, drift=0.0)))[0]
                 for s in range(10))
    assert passed <= 3
