import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from risk_manager.api import create_app
from risk_manager.approval import sign
from risk_manager.killswitch import KillSwitch
from risk_manager.state import StateStore

KEY, TOKEN = "k" * 40, "t" * 40
H = {"X-Internal-Token": TOKEN}
NOW = 1_700_000_000
VECTOR = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "approval-vector.json").read_text())


class Acct:
    """A stand-in for the execution service's /account."""
    def __init__(self, equity=100_000.0, positions=None, prices=None):
        self.data = dict(equity=equity, cash=equity, positions=positions or {},
                         prices=prices or {"SPY": 100.0})
        self.fail = False

    def __call__(self):
        if self.fail:
            raise ConnectionError("execution is down")
        return self.data


def make(acct=None, **kw):
    acct = acct or Acct()
    return acct, TestClient(create_app(acct, KEY, TOKEN, clock=kw.pop("clock", lambda: NOW), **kw))


def buy(client, qty=100, stop=95.0, symbol="SPY", side="buy"):
    return client.post("/evaluate", json=dict(symbol=symbol, side=side, qty=qty, stop_price=stop), headers=H)


def test_signer_matches_the_shared_contract_vector():
    assert sign(VECTOR["key"], VECTOR["order"], VECTOR["approved_at"]) == VECTOR["signature"]


def test_approved_order_comes_back_signed_and_the_signature_checks_out():
    _, c = make()
    r = buy(c).json()
    a = r["approval"]
    assert r["approved"] and a["order"]["qty"] == 100 and a["approved_at"] == NOW
    o = dict(a["order"], qty=float(a["order"]["qty"]))
    msg = json.dumps({"order": o, "approved_at": NOW}, sort_keys=True, separators=(",", ":"))
    assert a["signature"] == hmac.new(KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()


def test_rejections_carry_reasons_and_no_approval():
    _, c = make()
    r = buy(c, stop=99.9).json()                       # stop too tight
    assert not r["approved"] and "too close" in r["reasons"][0] and "approval" not in r
    assert not buy(c, symbol="ZZZ").json()["approved"]  # no price known
    assert not buy(c, stop=None).json()["approved"]
    assert not buy(c, side="sell").json()["approved"]   # nothing held


def test_orders_are_resized_using_the_price_execution_reports():
    _, c = make()
    r = buy(c, qty=500).json()   # risk 1% of 100k = 1000, 5 per share to stop -> 200
    assert r["approved"] and r["approval"]["order"]["qty"] == 200 and "max risk" in r["reasons"][0]


def test_fails_closed_when_execution_cannot_be_reached():
    acct, c = make()
    acct.fail = True
    r = buy(c)
    assert r.status_code == 503 and "approval" not in r.text


def test_bad_account_data_means_no():
    acct, c = make()
    acct.data["equity"] = "not-a-number"
    assert buy(c).status_code == 503
    acct.data = {"oops": 1}
    assert buy(c).status_code == 503


def test_internal_token_required_everywhere():
    _, c = make()
    for headers in ({}, {"X-Internal-Token": "x" * 40}):
        assert c.post("/evaluate", json=dict(symbol="SPY", side="buy", qty=1, stop_price=95), headers=headers).status_code == 401
        assert c.get("/kill", headers=headers).status_code == 401
        assert c.post("/kill/engage", json={}, headers=headers).status_code == 401
        assert c.post("/kill/release", headers=headers).status_code == 401
    assert c.get("/health").status_code == 200


def test_kill_switch_over_http_blocks_buys_but_not_sells():
    acct, c = make(Acct(positions={"SPY": 50}))
    assert c.post("/kill/engage", json={"reason": "operator"}, headers=H).json()["engaged"]
    assert not buy(c).json()["approved"]
    assert buy(c, qty=50, side="sell", stop=None).json()["approved"]
    assert c.get("/kill", headers=H).json()["reason"] == "operator"
    c.post("/kill/release", headers=H)
    assert buy(c).json()["approved"]


def test_drawdown_is_tracked_across_calls_and_latches():
    acct, c = make()
    assert buy(c).json()["approved"]           # equity 100k sets the peak
    acct.data["equity"] = 89_000.0             # 11% below the peak, limit is 10%
    assert not buy(c).json()["approved"]
    acct.data["equity"] = 100_000.0            # recovered, but the latch holds
    assert not buy(c).json()["approved"]


def test_daily_loss_limit_uses_the_start_of_day_equity():
    t = [NOW]
    acct, c = make(clock=lambda: t[0])
    buy(c)
    acct.data["equity"] = 97_000.0             # -3% today, limit 2%
    assert not buy(c).json()["approved"]
    t[0] += 86_400                             # next day: a fresh baseline
    acct.data["equity"] = 97_000.0
    assert buy(c).json()["approved"]


def test_state_survives_a_restart_and_a_corrupt_file_is_never_ignored(tmp_path):
    p = str(tmp_path / "state.json")
    acct, c = make(store=StateStore(p))
    buy(c)
    _, c2 = make(acct, store=StateStore(p))    # "restart"
    acct.data["equity"] = 89_000.0
    assert not buy(c2).json()["approved"]
    (tmp_path / "state.json").write_text("{broken")
    with pytest.raises(RuntimeError):
        StateStore(p)


def test_weak_secrets_are_refused():
    with pytest.raises(ValueError):
        create_app(Acct(), "short", TOKEN)
