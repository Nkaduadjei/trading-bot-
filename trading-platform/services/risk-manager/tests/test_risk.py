import json
from pathlib import Path

import pytest
from jsonschema import validate

from risk_manager.config import RiskConfig
from risk_manager.gate import RiskManager
from risk_manager.killswitch import KillSwitch
from risk_manager.models import AccountState, ProposedOrder
from risk_manager.sizing import plan_order

SCHEMAS = Path(__file__).resolve().parents[3] / "contracts"


def state(equity=100_000, sod=None, peak=None, positions=None, prices=None):
    return AccountState(equity, sod or equity, peak or equity, positions or {}, prices or {})


def buy(qty, price=100.0, stop=95.0, sym="SPY"):
    return ProposedOrder(sym, "buy", qty, price, stop)


def test_small_buy_is_approved_unchanged_and_matches_the_order_contract():
    d = RiskManager().check(buy(100), state())
    assert d.approved and d.order["qty"] == 100 and d.reasons == []
    validate(d.order, json.loads((SCHEMAS / "order.schema.json").read_text()))


def test_risk_per_trade_resizes_the_order():
    # 1% of 100k = 1000 at risk; 5 per share to the stop -> at most 200 shares
    d = RiskManager().check(buy(240), state())
    assert d.approved and d.order["qty"] == 200
    assert "max risk per trade" in d.reasons[0]


def test_position_size_cap_resizes_the_order():
    d = RiskManager().check(buy(400, stop=99.5), state())  # 25% of 100k at $100 = 250 shares
    assert d.order["qty"] == 250 and "max position size" in d.reasons[0]


def test_total_exposure_cap_counts_what_is_already_held():
    st = state(positions={"QQQ": 900}, prices={"QQQ": 100.0})  # 90k already invested
    d = RiskManager().check(buy(200, stop=99.5), st)           # only 10k of room -> 100 shares
    assert d.order["qty"] == 100 and "max total exposure" in d.reasons[0]


def test_buy_without_a_valid_stop_is_rejected():
    for stop in (None, 100.0, 120.0, float("nan")):
        assert not RiskManager().check(buy(10, stop=stop), state()).approved


def test_sells_cannot_exceed_holdings_and_shorting_is_refused():
    st = state(positions={"SPY": 50}, prices={"SPY": 100.0})
    sell = lambda q, s="SPY": ProposedOrder(s, "sell", q, 100.0)
    assert RiskManager().check(sell(80), st).order["qty"] == 50
    assert not RiskManager().check(sell(10, "QQQ"), st).approved


def test_manual_kill_switch_blocks_buys_but_still_allows_sells():
    kill = KillSwitch()
    kill.engage("operator pressed stop")
    st = state(positions={"SPY": 50}, prices={"SPY": 100.0})
    rm = RiskManager(kill=kill)
    assert not rm.check(buy(10), st).approved
    assert rm.check(ProposedOrder("SPY", "sell", 50, 100.0), st).approved


def test_daily_loss_limit_blocks_buys_for_the_day():
    st = state(equity=97_000, sod=100_000)  # down 3%, limit is 2%
    d = RiskManager().check(buy(10), st)
    assert not d.approved and "daily loss" in d.reasons[0]


def test_drawdown_latches_and_stays_halted_after_recovery_until_released():
    rm = RiskManager()
    assert not rm.check(buy(10), state(equity=89_000, sod=89_000, peak=100_000)).approved
    assert rm.kill.engaged
    assert not rm.check(buy(10), state(equity=99_000, peak=100_000)).approved  # recovered, still off
    rm.kill.release()
    assert rm.check(buy(10), state(equity=99_000, peak=100_000)).approved


def test_kill_switch_survives_a_restart_and_a_corrupt_file_fails_closed(tmp_path):
    p = tmp_path / "kill.json"
    KillSwitch(str(p)).engage("test")
    assert KillSwitch(str(p)).engaged
    p.write_text("{not json")
    assert KillSwitch(str(p)).engaged


@pytest.mark.parametrize("bad", [
    buy(float("nan")), buy(10, price=float("nan")), buy(10, price=-5), buy(0),
    ProposedOrder("SPY", "short", 10, 100.0, 95.0)])
def test_bad_data_is_rejected_not_passed_through(bad):
    assert not RiskManager().check(bad, state()).approved


def test_bad_account_state_is_rejected():
    for st in (state(equity=0), state(equity=float("nan")), state(equity=-5)):
        assert not RiskManager().check(buy(10), st).approved


def test_a_crash_inside_a_check_means_reject():
    st = state(positions={"QQQ": 10}, prices={})  # missing price for a held symbol
    d = RiskManager().check(buy(10), st)
    assert not d.approved and "failed safely" in d.reasons[0]


def test_config_rejects_nonsense_limits():
    for bad in (dict(max_risk_per_trade=0), dict(max_exposure_pct=1.5), dict(max_drawdown=-1)):
        with pytest.raises(ValueError):
            RiskConfig(**bad)


def test_signal_to_order_sizing():
    sig = dict(strategy="trend", symbol="SPY", timestamp="2026-01-02T00:00:00Z", target_position=0.2)
    o = plan_order(sig, state(), price=100.0, stop_price=95.0)
    assert o.side == "buy" and o.qty == pytest.approx(200)
    held = state(positions={"SPY": 200}, prices={"SPY": 100.0})
    assert plan_order(dict(sig, target_position=0.0), held, 100.0).side == "sell"
    assert plan_order(sig, held, 100.0) is None  # already at target: nothing to do


def test_stop_too_close_to_the_price_is_refused():
    d = RiskManager().check(buy(10, stop=99.9), state())
    assert not d.approved and "too close" in d.reasons[0]
    assert RiskManager().check(buy(10, stop=99.5), state()).approved   # exactly 0.5% is allowed
