import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from execution.api import create_app
from execution.models import Order, OrderRequest
from execution.paper import PaperBroker
from execution.restore import build_paper_broker
from execution.store import Store

KEY, TOKEN = "k" * 40, "t" * 40
NOW = 1_700_000_000
H = {"X-Internal-Token": TOKEN}


def approval(qty=10, oid="order-0001", side="buy", at=NOW, symbol="SPY"):
    order = dict(client_order_id=oid, symbol=symbol, side=side, qty=qty)
    msg = json.dumps({"order": dict(order, qty=float(qty)), "approved_at": at}, sort_keys=True, separators=(",", ":"))
    return dict(order=order, approved_at=at, signature=hmac.new(KEY.encode(), msg.encode(), hashlib.sha256).hexdigest())


def boot(url, start_cash=100_000.0, clock=lambda: NOW):
    """Start the service the way main.py does: store, rebuilt paper broker, app."""
    store = Store(url, clock)
    broker = build_paper_broker(store, start_cash)
    return broker, TestClient(create_app(broker, KEY, TOKEN, clock=clock, store=store))


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/exec.db"


def price(c, symbol="SPY", p=100.0):
    assert c.put(f"/paper/prices/{symbol}", json={"price": p}, headers=H).status_code == 200


def test_orders_fills_and_equity_are_saved_and_listed(url):
    _, c = boot(url)
    price(c)
    r = c.post("/orders", json=approval(), headers=H).json()
    assert r["status"] == "filled" and r["client_order_id"] == "order-0001"
    assert [o["client_order_id"] for o in c.get("/orders", headers=H).json()] == ["order-0001"]
    t = c.get("/trades", headers=H).json()
    assert len(t) == 1 and t[0]["qty"] == 10 and t[0]["price"] > 100
    e = c.get("/equity", headers=H).json()
    assert len(e) == 1 and e[0]["positions"] == {"SPY": 10}


def test_rejected_orders_are_kept_with_their_reason_and_make_no_fill(url):
    _, c = boot(url, start_cash=100)
    price(c)
    r = c.post("/orders", json=approval(), headers=H).json()
    assert r["status"] == "rejected" and r["reason"] == "insufficient cash"
    assert c.get("/trades", headers=H).json() == []
    assert c.get("/orders", headers=H).json()[0]["reason"] == "insufficient cash"


def test_everything_survives_a_restart_including_cash_positions_and_prices(url):
    b1, c1 = boot(url)
    price(c1)
    c1.post("/orders", json=approval(10, "order-0001"), headers=H)
    c1.post("/orders", json=approval(4, "order-0002", side="sell"), headers=H)
    before = c1.get("/account", headers=H).json()

    b2, c2 = boot(url)                                   # "restart": a brand-new broker, same database
    after = c2.get("/account", headers=H).json()
    assert after["positions"] == before["positions"] == {"SPY": 6}
    assert after["prices"] == before["prices"]
    assert after["cash"] == pytest.approx(before["cash"]) and after["equity"] == pytest.approx(before["equity"])
    assert len(c2.get("/orders", headers=H).json()) == 2 and len(c2.get("/trades", headers=H).json()) == 2


def test_replaying_an_approval_after_a_restart_never_trades_twice(url):
    _, c1 = boot(url)
    price(c1)
    a = approval()
    first = c1.post("/orders", json=a, headers=H).json()
    _, c2 = boot(url)
    again = c2.post("/orders", json=a, headers=H).json()
    assert again["id"] == first["id"] and again["status"] == "filled"
    assert c2.get("/account", headers=H).json()["positions"] == {"SPY": 10}
    assert len(c2.get("/trades", headers=H).json()) == 1


def test_starting_cash_is_fixed_the_first_time(url):
    boot(url, start_cash=50_000)
    b, _ = boot(url, start_cash=999_999)        # a changed setting must not rewrite history
    assert b.cash == 50_000


def test_a_held_symbol_without_a_price_makes_the_account_unavailable_instead_of_understated(url):
    b = PaperBroker(cash=10_000)
    b.set_price("SPY", 100.0)
    c = TestClient(create_app(b, KEY, TOKEN, clock=lambda: NOW, store=Store(url)))
    c.post("/orders", json=approval(), headers=H)
    b._prices.clear()                            # the price is lost
    assert c.get("/account", headers=H).status_code == 503
    assert c.post("/snapshot", headers=H).status_code == 503


def test_begin_order_is_idempotent_and_a_second_caller_gets_the_stored_row(url):
    s = Store(url)
    req = OrderRequest("order-0001", "SPY", "buy", 10)
    first, created1 = s.begin_order(req, NOW, "s" * 64)
    second, created2 = s.begin_order(req, NOW, "s" * 64)
    assert created1 and not created2 and first["client_order_id"] == second["client_order_id"]
    assert first["status"] == "submitted"


def test_an_unknown_outcome_stays_retryable(url):
    """If the broker could not be reached the order may or may not exist, so a retry must be allowed."""
    class Flaky(PaperBroker):
        calls = 0

        def submit(self, req):
            Flaky.calls += 1
            if Flaky.calls == 1:
                return Order("", req.client_order_id, req.symbol, req.side, req.qty, "rejected", reason="broker unreachable")
            return super().submit(req)

    b = Flaky(cash=10_000)
    b.set_price("SPY", 100.0)
    c = TestClient(create_app(b, KEY, TOKEN, clock=lambda: NOW, store=Store(url)))
    a = approval()
    assert c.post("/orders", json=a, headers=H).json()["status"] == "submitted"
    assert c.post("/orders", json=a, headers=H).json()["status"] == "filled"
    assert len(c.get("/trades", headers=H).json()) == 1


def test_history_endpoints_need_the_token_and_validate_limits(url):
    _, c = boot(url)
    for path in ("/orders", "/trades", "/equity"):
        assert c.get(path).status_code == 401
        assert c.get(path, headers=H).status_code == 200
        assert c.get(path + "?limit=0", headers=H).status_code == 422
        assert c.get(path + "?limit=999999", headers=H).status_code == 422
    assert c.post("/snapshot").status_code == 401


def test_manual_snapshot_adds_a_point_to_the_equity_curve(url):
    _, c = boot(url)
    assert c.post("/snapshot", headers=H).json()["recorded"] is True
    assert len(c.get("/equity", headers=H).json()) == 1


def test_database_file_is_private(url, tmp_path):
    boot(url)
    assert oct((tmp_path / "exec.db").stat().st_mode & 0o777) == "0o600"
