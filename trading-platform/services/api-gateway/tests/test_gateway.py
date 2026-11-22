import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.config import Settings
from gateway.ratelimit import RateLimiter

RT, ET = "r" * 40, "e" * 40
APPROVAL = {"order": {"client_order_id": "abcdef123456", "symbol": "SPY", "side": "buy", "qty": 10},
            "approved_at": 1700000000, "signature": "f" * 64}


class Upstreams:
    """Stands in for the auth, risk and execution services, and records every call."""

    def __init__(self):
        self.calls = []
        self.me = (200, {"id": 1, "email": "trader@example.com"})
        self.risk = (200, {"approved": True, "reasons": [], "approval": APPROVAL})
        self.exec = [(200, {"id": "paper-1", "status": "filled", "symbol": "SPY"})]

    def to(self, host):
        return [c for c in self.calls if c["host"] == host]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append(dict(host=request.url.host, method=request.method, path=request.url.path,
                               headers=dict(request.headers), body=body))
        h, p = request.url.host, request.url.path
        if h == "auth.test":
            if p == "/me":
                return httpx.Response(self.me[0], json=self.me[1])
            return httpx.Response(200, json={"from": "auth", "path": p})
        if h == "risk.test":
            if isinstance(self.risk, Exception):
                raise self.risk
            return httpx.Response(self.risk[0], json=self.risk[1])
        if h == "exec.test":
            item = self.exec.pop(0) if len(self.exec) > 1 else self.exec[0]
            if isinstance(item, Exception):
                raise item
            return httpx.Response(item[0], json=item[1])
        return httpx.Response(404)


def make(**kw):
    up = Upstreams()
    s = Settings(risk_token=RT, execution_token=ET, auth_url="http://auth.test", risk_url="http://risk.test",
                 execution_url="http://exec.test", trader_emails=frozenset({"trader@example.com"}), **kw)
    return up, TestClient(create_app(s, transport=httpx.MockTransport(up)))


AUTH = {"Authorization": "Bearer sometoken"}
ORDER = dict(symbol="SPY", side="buy", qty=10, stop_price=95)


def test_account_routes_are_forwarded_to_the_auth_service():
    up, c = make()
    r = c.post("/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 200 and r.json() == {"from": "auth", "path": "/auth/login"}
    assert up.to("auth.test")[0]["body"] == {"email": "a@b.co", "password": "x"}
    c.get("/me", headers=AUTH)
    assert up.to("auth.test")[-1]["headers"]["authorization"] == "Bearer sometoken"


def test_upstream_status_codes_and_safe_headers_pass_through():
    class Locked(Upstreams):
        def __call__(self, request):
            return httpx.Response(429, json={"detail": "locked"}, headers={"Retry-After": "30", "Set-Cookie": "x=1"})
    s = Settings(risk_token=RT, execution_token=ET, auth_url="http://auth.test")
    c = TestClient(create_app(s, transport=httpx.MockTransport(Locked())))
    r = c.post("/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 429 and r.headers["retry-after"] == "30" and "set-cookie" not in r.headers


@pytest.mark.parametrize("method,path", [("get", "/kill"), ("post", "/kill/engage"), ("get", "/admin"),
                                         ("put", "/paper/prices/SPY"), ("get", "/auth/2fa/secret"),
                                         ("get", "/broker-keys/1")])
def test_nothing_outside_the_whitelist_is_reachable(method, path):
    up, c = make()
    r = getattr(c, method)(path, headers=AUTH)
    assert r.status_code in (404, 405) and up.calls == []


def test_order_without_a_login_is_refused_and_nothing_is_called():
    up, c = make()
    assert c.post("/orders", json=ORDER).status_code == 401
    assert up.to("risk.test") == [] and up.to("exec.test") == []
    up.me = (401, {"detail": "no"})
    assert c.post("/orders", json=ORDER, headers=AUTH).status_code == 401
    assert up.to("risk.test") == []


def test_only_emails_on_the_trader_list_may_trade_and_an_empty_list_means_nobody():
    up, c = make()
    up.me = (200, {"id": 2, "email": "stranger@example.com"})
    assert c.post("/orders", json=ORDER, headers=AUTH).status_code == 403
    assert c.get("/account", headers=AUTH).status_code == 403
    assert up.to("risk.test") == [] and up.to("exec.test") == []
    s = Settings(risk_token=RT, execution_token=ET, auth_url="http://auth.test")   # no trader_emails at all
    c2 = TestClient(create_app(s, transport=httpx.MockTransport(up)))
    up.me = (200, {"id": 1, "email": "trader@example.com"})
    assert c2.post("/orders", json=ORDER, headers=AUTH).status_code == 403


def test_approved_order_flows_through_risk_then_execution_with_the_approval_untouched():
    up, c = make()
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 200 and r.json()["approved"] and r.json()["order"]["status"] == "filled"
    ev = up.to("risk.test")[0]
    assert ev["headers"]["x-internal-token"] == RT
    assert ev["body"] == dict(symbol="SPY", side="buy", qty=10, stop_price=95)   # no price, no account data
    ex = up.to("exec.test")[0]
    assert ex["body"] == APPROVAL and ex["headers"]["x-internal-token"] == ET


def test_a_rejected_order_never_reaches_execution():
    up, c = make()
    up.risk = (200, {"approved": False, "reasons": ["daily loss limit 2% reached"]})
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 200 and r.json() == {"approved": False, "reasons": ["daily loss limit 2% reached"]}
    assert up.to("exec.test") == []


@pytest.mark.parametrize("risk", [
    (503, {"detail": "x"}), (500, {"detail": "x"}), httpx.ConnectError("down"),
    (200, {"approved": True, "reasons": []}),            # "approved" but no signed approval
    (200, {"approved": True, "approval": "nonsense"}),
])
def test_any_risk_manager_problem_means_no_order(risk):
    up, c = make()
    up.risk = risk
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert r.status_code in (502, 503) and up.to("exec.test") == []


def test_a_dropped_connection_to_execution_is_retried_once_with_the_same_approval():
    up, c = make()
    up.exec = [httpx.ConnectError("dropped"), (200, {"id": "paper-1", "status": "filled"})]
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 200
    posts = up.to("exec.test")
    assert len(posts) == 2 and posts[0]["body"] == posts[1]["body"] == APPROVAL


def test_execution_down_or_refusing_is_reported_honestly():
    up, c = make()
    up.exec = [httpx.ConnectError("a"), httpx.ConnectError("b")]
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 503 and "unknown" in r.json()["detail"]
    up.exec = [(403, {"detail": "approval rejected: expired"})]
    assert c.post("/orders", json=ORDER, headers=AUTH).status_code == 502


@pytest.mark.parametrize("bad", [dict(ORDER, symbol="spy!"), dict(ORDER, symbol=""), dict(ORDER, qty=0),
                                 dict(ORDER, qty=-5), dict(ORDER, qty=10_000_000), dict(ORDER, side="short"),
                                 dict(ORDER, stop_price=-1), {"symbol": "SPY"}])
def test_bad_orders_are_rejected_before_any_service_is_called(bad):
    up, c = make()
    assert c.post("/orders", json=bad, headers=AUTH).status_code == 422
    assert up.to("risk.test") == []


def test_account_view_requires_a_trader():
    up, c = make()
    up.exec = [(200, {"equity": 100000, "positions": {}, "prices": {}})]
    assert c.get("/account", headers=AUTH).json()["equity"] == 100000
    assert c.get("/account").status_code == 401


def test_errors_never_leak_internal_addresses_or_tokens():
    up, c = make()
    up.risk = httpx.ConnectError("could not connect to http://risk.test with " + RT)
    r = c.post("/orders", json=ORDER, headers=AUTH)
    assert "risk.test" not in r.text and RT not in r.text and ET not in r.text


def test_login_is_rate_limited_and_recovers():
    t = [1_000_000.0]
    up, c = make(clock=lambda: t[0])
    body = {"email": "a@b.co", "password": "x"}
    assert all(c.post("/auth/login", json=body).status_code == 200 for _ in range(10))
    r = c.post("/auth/login", json=body)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert len(up.to("auth.test")) == 10          # the blocked attempt never reached the auth service
    t[0] += 61
    assert c.post("/auth/login", json=body).status_code == 200


def test_oversized_bodies_are_refused():
    up, c = make()
    r = c.post("/auth/register", content=b"x" * 70_000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and up.calls == []


def test_security_headers_are_set():
    _, c = make()
    h = c.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store"


def test_settings_validation_and_the_gateway_cannot_sign():
    with pytest.raises(ValueError):
        Settings(risk_token="short", execution_token=ET)
    with pytest.raises(RuntimeError):
        Settings.from_env({})
    s = Settings.from_env({"RISK_TOKEN": RT, "EXECUTION_TOKEN": ET, "TRADER_EMAILS": " A@x.co , b@x.co,, "})
    assert s.trader_emails == {"a@x.co", "b@x.co"}
    assert Settings.from_env({"RISK_TOKEN": RT, "EXECUTION_TOKEN": ET}).trader_emails == frozenset()
    assert not hasattr(s, "approval_key") and "APPROVAL_KEY" not in open("gateway/app.py").read()


def test_rate_limiter_window():
    t = [0.0]
    rl = RateLimiter(lambda: t[0])
    assert all(rl.check("k", 3) is None for _ in range(3))
    assert rl.check("k", 3) == pytest.approx(60.0)
    assert rl.check("other", 3) is None
    t[0] = 61
    assert rl.check("k", 3) is None
