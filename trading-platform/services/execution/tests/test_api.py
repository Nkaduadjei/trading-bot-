import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from execution.api import create_app
from execution.approval import ApprovalError, verify
from execution.paper import PaperBroker

KEY, TOKEN = "k" * 40, "t" * 40
NOW = 1_700_000_000
VECTOR = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "approval-vector.json").read_text())


def sign(order, at, key=KEY):
    """Test-only signer. The real execution service has no signing code."""
    o = dict(order, qty=float(order["qty"]))
    msg = json.dumps({"order": o, "approved_at": at}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def approval(qty=10, oid="order-0001", side="buy", at=NOW, key=KEY, symbol="SPY"):
    order = dict(client_order_id=oid, symbol=symbol, side=side, qty=qty)
    return dict(order=order, approved_at=at, signature=sign(order, at, key))


@pytest.fixture
def broker():
    b = PaperBroker(cash=100_000)
    b.set_price("SPY", 100.0)
    return b


@pytest.fixture
def client(broker):
    return TestClient(create_app(broker, KEY, TOKEN, clock=lambda: NOW))


H = {"X-Internal-Token": TOKEN}


def test_matches_the_shared_contract_vector():
    assert sign(VECTOR["order"], VECTOR["approved_at"], VECTOR["key"]) == VECTOR["signature"]
    req = verify(VECTOR["key"], dict(order=VECTOR["order"], approved_at=VECTOR["approved_at"],
                                     signature=VECTOR["signature"]), VECTOR["approved_at"])
    assert req.symbol == "SPY" and req.qty == 10


def test_valid_approval_places_the_order(client, broker):
    r = client.post("/orders", json=approval(), headers=H)
    assert r.status_code == 200 and r.json()["status"] == "filled"
    assert broker.positions() == {"SPY": 10}


@pytest.mark.parametrize("tamper", [
    lambda a: a["order"].update(qty=1000),
    lambda a: a["order"].update(symbol="QQQ"),
    lambda a: a["order"].update(side="sell"),
    lambda a: a.update(signature="0" * 64),
    lambda a: a.update(approved_at=a["approved_at"] + 1),
    lambda a: a["order"].update(extra="field"),
])
def test_any_change_to_an_approved_order_is_refused(client, broker, tamper):
    a = approval()
    tamper(a)
    assert client.post("/orders", json=a, headers=H).status_code == 403
    assert broker.positions() == {}


def test_approval_signed_with_the_wrong_key_is_refused(client, broker):
    assert client.post("/orders", json=approval(key="x" * 40), headers=H).status_code == 403
    assert broker.positions() == {}


def test_stale_and_future_approvals_are_refused(broker):
    for at in (NOW - 31, NOW + 6):
        c = TestClient(create_app(broker, KEY, TOKEN, clock=lambda: NOW))
        assert c.post("/orders", json=approval(at=at), headers=H).status_code == 403
    assert broker.positions() == {}


def test_replaying_an_approval_never_fills_twice(client, broker):
    a = approval()
    assert client.post("/orders", json=a, headers=H).status_code == 200
    assert client.post("/orders", json=a, headers=H).status_code == 200
    assert broker.positions() == {"SPY": 10}


def test_internal_token_is_required(client):
    for headers in ({}, {"X-Internal-Token": "wrong" * 10}):
        assert client.get("/account", headers=headers).status_code == 401
        assert client.post("/orders", json=approval(), headers=headers).status_code == 401
    assert client.get("/health").status_code == 200


def test_account_endpoint_reports_equity_positions_and_prices(client, broker):
    client.post("/orders", json=approval(), headers=H)
    a = client.get("/account", headers=H).json()
    assert a["positions"] == {"SPY": 10} and a["prices"]["SPY"] == 100.0
    assert a["equity"] == pytest.approx(a["cash"] + 1000)


def test_paper_price_endpoint_validates(client):
    assert client.put("/paper/prices/QQQ", json={"price": 250}, headers=H).status_code == 200
    assert client.put("/paper/prices/QQQ", json={"price": -1}, headers=H).status_code == 422


def test_weak_secrets_are_refused(broker):
    with pytest.raises(ValueError):
        create_app(broker, "short", TOKEN)
    with pytest.raises(ValueError):
        create_app(broker, KEY, "short")


def test_verify_rejects_garbage():
    for junk in ({}, {"order": 1, "approved_at": 1, "signature": "x"},
                 {"order": {}, "approved_at": True, "signature": "x"}):
        with pytest.raises(ApprovalError):
            verify(KEY, junk, NOW)
