import json

import httpx
import pytest
from fastapi.testclient import TestClient

from admin_console import audit
from admin_console.app import create_app
from admin_console.config import Settings

RT, AT = "r" * 40, "a" * 40
HOST = "http://127.0.0.1:8004"
H = {"Authorization": "Bearer tok"}


class Up:
    def __init__(self):
        self.calls = []
        self.me = (200, {"id": 1, "email": "boss@example.com"})
        self.down = set()
        self.kill = {"engaged": False, "reason": ""}
        self.users = [{"id": 1, "email": "boss@example.com", "totp_enabled": False, "created_at": 1.0,
                       "locked": False, "password_hash": "SECRET", "totp_secret_enc": "SECRET"}]

    def to(self, host):
        return [c for c in self.calls if c["host"] == host]

    def __call__(self, request):
        body = json.loads(request.content) if request.content else None
        h, p = request.url.host, request.url.path
        self.calls.append(dict(host=h, method=request.method, path=p, headers=dict(request.headers), body=body))
        if h in self.down:
            raise httpx.ConnectError("down at http://" + h)
        if p == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if h == "auth.test":
            if p == "/me":
                return httpx.Response(*self.me[:1], json=self.me[1])
            if p == "/auth/login":
                return httpx.Response(200, json={"access_token": "tok", "token_type": "bearer"})
            if p == "/internal/users":
                return httpx.Response(200, json=self.users)
        if h == "risk.test":
            if p == "/kill":
                return httpx.Response(200, json=self.kill)
            if p == "/kill/engage":
                self.kill = {"engaged": True, "reason": body["reason"]}
                return httpx.Response(200, json=self.kill)
            if p == "/kill/release":
                self.kill = {"engaged": False, "reason": ""}
                return httpx.Response(200, json={"engaged": False})
        return httpx.Response(404)


def make(tmp_path, admins=("boss@example.com",), **kw):
    up = Up()
    s = Settings(risk_token=RT, auth_admin_token=AT, admin_emails=frozenset(admins), auth_url="http://auth.test",
                 risk_url="http://risk.test", execution_url="http://exec.test", gateway_url="http://gw.test",
                 audit_path=str(tmp_path / "audit.log"), **kw)
    return up, TestClient(create_app(s, transport=httpx.MockTransport(up)), base_url=HOST)


ROUTES = [("get", "/api/health"), ("get", "/api/kill"), ("post", "/api/kill/engage"),
          ("post", "/api/kill/release"), ("get", "/api/users"), ("get", "/api/audit")]


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_admin_route_needs_a_login_and_an_admin_email(tmp_path, method, path):
    up, c = make(tmp_path)
    kw = {"json": {"reason": "x"}} if path.endswith("engage") else {}
    assert getattr(c, method)(path, **kw).status_code == 401
    up.me = (200, {"id": 2, "email": "stranger@example.com"})
    assert getattr(c, method)(path, headers=H, **kw).status_code == 403
    assert up.to("risk.test") == [] and not any(x["path"] == "/internal/users" for x in up.calls)


def test_an_empty_admin_list_means_nobody(tmp_path):
    _, c = make(tmp_path, admins=())
    assert c.get("/api/kill", headers=H).status_code == 403


def test_service_health_shows_up_and_down(tmp_path):
    up, c = make(tmp_path)
    up.down = {"exec.test"}
    s = c.get("/api/health", headers=H).json()["services"]
    assert s == {"gateway": "up", "auth": "up", "risk manager": "up", "execution": "down"}


def test_kill_switch_engage_and_release_use_the_risk_token_and_are_audited(tmp_path):
    up, c = make(tmp_path)
    r = c.post("/api/kill/engage", headers=H, json={"reason": "market looks wrong"})
    assert r.status_code == 200 and r.json()["engaged"] and "boss@example.com" in r.json()["reason"]
    assert up.to("risk.test")[-1]["headers"]["x-internal-token"] == RT
    assert c.get("/api/kill", headers=H).json()["engaged"] is True
    assert c.post("/api/kill/release", headers=H).json() == {"engaged": False}
    log = c.get("/api/audit", headers=H).json()
    assert [x["action"] for x in log] == ["kill_engage", "kill_release"]
    assert log[0]["admin"] == "boss@example.com" and log[0]["detail"] == "market looks wrong"


def test_kill_reason_is_limited_and_a_failed_engage_says_state_unknown(tmp_path):
    up, c = make(tmp_path)
    assert c.post("/api/kill/engage", headers=H, json={"reason": "x" * 201}).status_code == 422
    up.down = {"risk.test"}
    r = c.post("/api/kill/engage", headers=H, json={"reason": "stop"})
    assert r.status_code == 502 and "UNKNOWN" in r.json()["detail"]
    assert "risk.test" not in r.text and RT not in r.text
    assert c.get("/api/audit", headers=H).json() == []      # nothing recorded as done


def test_users_list_uses_the_auth_token_not_the_users_and_leaks_no_secrets(tmp_path):
    up, c = make(tmp_path)
    r = c.get("/api/users", headers=H)
    assert r.status_code == 200 and set(r.json()[0]) == {"id", "email", "totp_enabled", "created_at", "locked"}
    assert "SECRET" not in r.text
    call = [x for x in up.calls if x["path"] == "/internal/users"][0]
    assert call["headers"]["x-internal-token"] == AT and "authorization" not in call["headers"]


def test_login_is_proxied_and_rate_limited(tmp_path):
    t = [1_000_000.0]
    up, c = make(tmp_path, clock=lambda: t[0])
    body = {"email": "boss@example.com", "password": "x"}
    assert c.post("/api/login", json=body).json()["access_token"] == "tok"
    for _ in range(9):
        c.post("/api/login", json=body)
    assert c.post("/api/login", json=body).status_code == 429
    t[0] += 61
    assert c.post("/api/login", json=body).status_code == 200


def test_requests_with_an_unexpected_host_name_are_refused(tmp_path):
    _, c = make(tmp_path)
    assert c.get("/health", headers={"Host": "evil.example.com"}).status_code == 421
    assert c.get("/health", headers={"Host": "localhost:8004"}).status_code == 200


def test_the_page_is_served_with_strict_headers_and_no_outside_resources(tmp_path):
    _, c = make(tmp_path)
    for path, kind in (("/", "text/html"), ("/app.js", "javascript"), ("/style.css", "text/css")):
        r = c.get(path)
        assert r.status_code == 200 and kind in r.headers["content-type"]
        assert "script-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY" and r.headers["cache-control"] == "no-store"
    page = c.get("/").text + c.get("/app.js").text
    assert "http://" not in page and "https://" not in page and "innerHTML" not in page
    assert "<script>" not in c.get("/").text                 # no inline scripts
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_the_console_cannot_sign_or_trade_and_validates_its_settings(tmp_path):
    with pytest.raises(ValueError):
        Settings(risk_token="short", auth_admin_token=AT)
    with pytest.raises(RuntimeError):
        Settings.from_env({})
    s = Settings.from_env({"RISK_TOKEN": RT, "AUTH_ADMIN_TOKEN": AT, "ADMIN_EMAILS": " A@x.co,b@x.co,, "})
    assert s.admin_emails == {"a@x.co", "b@x.co"}
    assert not hasattr(s, "approval_key") and not hasattr(s, "execution_token")


def test_audit_file_is_private_and_survives_bad_lines(tmp_path):
    p = str(tmp_path / "a.log")
    audit.record(p, 1_700_000_000, "boss@example.com", "kill_engage", "why")
    assert oct((tmp_path / "a.log").stat().st_mode & 0o777) == "0o600"
    with open(p, "a") as f:
        f.write("{broken\n")
    assert len(audit.tail(p)) == 1
    assert audit.tail(str(tmp_path / "missing.log")) == []
