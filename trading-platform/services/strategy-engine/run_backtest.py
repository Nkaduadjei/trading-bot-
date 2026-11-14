"""Run a walk-forward backtest.  python run_backtest.py [--csv data/SPY.csv] [--seed 7]"""
import argparse

from strategy_engine.backtest import Costs, promotion_check, walk_forward
from strategy_engine.data import load_csv, synthetic_prices


def pct(x):
    return f"{x:.1%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="CSV with Date and Close columns; omit to use synthetic data")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--commission-bps", type=float, default=5.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    a = ap.parse_args()

    prices = load_csv(a.csv) if a.csv else synthetic_prices(seed=a.seed)
    src = a.csv or f"synthetic random walk (seed {a.seed}) - no real edge exists in it"
    wf = walk_forward(prices, costs=Costs(a.commission_bps, a.slippage_bps))

    print(f"Data: {src}  ({len(prices)} days)")
    print(f"{'test window':<25}{'params':<12}{'IS Sharpe':>10}{'OOS Sharpe':>12}")
    for f in wf.folds:
        w = f"{f['test'][0]:%Y-%m-%d}..{f['test'][1]:%Y-%m-%d}"
        print(f"{w:<25}{str(f['params']):<12}{f['is_sharpe']:>10.2f}{f['oos_sharpe']:>12.2f}")
    o = wf.oos
    print(f"\nOut-of-sample: return {pct(o['total_return'])}, CAGR {pct(o['cagr'])}, "
          f"Sharpe {o['sharpe']:.2f}, max drawdown {pct(o['max_drawdown'])}, trades {o['trades']}")
    print(f"Average in-sample Sharpe of chosen params: {wf.in_sample_sharpe:.2f}")
    ok, why = promotion_check(wf)
    print("\nPromote to paper trading:", "YES" if ok else "NO")
    for w in why:
        print(" -", w)


if __name__ == "__main__":
    main()
