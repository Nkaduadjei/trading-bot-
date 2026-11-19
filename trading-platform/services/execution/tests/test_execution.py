import pytest
import requests

from execution.alpaca import AlpacaBroker, PAPER_URL
from execution.config import make_broker
from execution.models import OrderRequest
from execution.paper import PaperBroker


def req(oid="order-0001", side="buy", qty=10, sym="SPY"):
    return OrderRequest(oid, sym, side, qty)


def test_paper_buy_fills_worse_than_last_price_and_updates_state():
    b = PaperBroker(cash=10_000)
    b.set_price("SPY", 100.0)
    o = b.submit(req())
    assert o.status == "filled" and o.filled_price > 100.0
    assert b.positions() == {"SPY": 10} and b.cash < 9_000


def test_same_client_order_id_never_fills_twice():
    b = PaperBroker(cash=10_000)
    b.set_price("SPY", 100.0)
    first, second = b.submit(req()), b.submit(req())
    assert first is second and b.positions() == {"SPY": 10}


def test_rejects_without_cash_price_or_position():
    b = PaperBroker(cash=100)
    b.set_price("SPY", 100.0)
    assert b.submit(req("order-0001")).reason == "insufficient cash"
    assert b.submit(req("order-0002", sym="QQQ")).reason == "no price for symbol"
    assert "insufficient position" in b.submit(req("order-0003", "sell")).reason


def test_sell_closes_position():
    b = PaperBroker(cash=10_000)
    b.set_price("SPY", 100.0)
    b.submit(req("order-0001"))
    assert b.submit(req("order-0002", "sell")).status == "filled"
    assert b.positions() == {}


def test_order_request_validation():
    for bad in (dict(side="hold"), dict(qty=0), dict(oid="short")):
        with pytest.raises(ValueError):
            req(**bad)


def test_default_is_paper_and_live_needs_confirmation():
    assert isinstance(make_broker({}), PaperBroker)
    with pytest.raises(RuntimeError):
        make_broker({"TRADING_MODE": "live", "BROKER_API_KEY": "k", "BROKER_API_SECRET": "s"})
    live = make_broker({"TRADING_MODE": "live", "BROKER_API_KEY": "k", "BROKER_API_SECRET": "s",
                        "LIVE_TRADING_CONFIRM": "yes-i-understand"})
    assert "paper" not in live.base


class FakeResp:
    def __init__(self, status, data=None):
        self.status_code, self._d, self.text = status, data or {}, str(data)

    def json(self):
        return self._d


class FakeSession:
    """Records calls. `script` maps (method, path) to a list of responses or exceptions."""
    def __init__(self, script):
        self.headers, self.script, self.calls = {}, script, []

    def request(self, method, url, **kw):
        path = url.replace(PAPER_URL, "")
        self.calls.append((method, path, kw))
        item = self.script[(method, path)].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


ORDER = {"id": "a1", "client_order_id": "order-0001", "symbol": "SPY", "side": "buy",
         "qty": "10", "status": "filled", "filled_avg_price": "100.5"}


def test_alpaca_uses_paper_url_and_sends_client_order_id():
    s = FakeSession({("POST", "/v2/orders"): [FakeResp(200, ORDER)]})
    o = AlpacaBroker("k", "s", session=s).submit(req())
    assert o.status == "filled" and o.filled_price == 100.5
    method, path, kw = s.calls[0]
    assert kw["json"]["client_order_id"] == "order-0001" and s.headers["APCA-API-KEY-ID"] == "k"


def test_alpaca_retry_after_dropped_connection_does_not_double_send():
    """The order reached the broker but the reply was lost. The retry must find it, not resend."""
    s = FakeSession({("POST", "/v2/orders"): [requests.ConnectionError("dropped")],
                     ("GET", "/v2/orders:by_client_order_id"): [FakeResp(200, ORDER)]})
    o = AlpacaBroker("k", "s", session=s).submit(req())
    assert o.id == "a1"
    assert sum(1 for c in s.calls if c[0] == "POST") == 1


def test_alpaca_gives_up_cleanly_when_unreachable():
    err = requests.ConnectionError("down")
    s = FakeSession({("POST", "/v2/orders"): [err] * 3,
                     ("GET", "/v2/orders:by_client_order_id"): [err] * 3})
    o = AlpacaBroker("k", "s", session=s).submit(req())
    assert o.status == "rejected" and o.reason == "broker unreachable"
