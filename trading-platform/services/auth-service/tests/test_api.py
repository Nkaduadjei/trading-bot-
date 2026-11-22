import logging
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_service import totp
from auth_service.app import create_app
from auth_service.config import Settings
from auth_service.db import BrokerKey, User

PW = "a-long-test-password-1"


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def app(clock):
    s = Settings(jwt_secret="j" * 40, encryption_key=Fernet.generate_key().decode(),
                 database_url="sqlite://", clock=clock)
    return create_app(s)


@pytest.fixture
def client(app):
    return TestClient(app)


def register(client, email="nana@example.com", pw=PW):
    return client.post("/auth/register", json={"email": email, "password": pw})


def login(client, email="nana@example.com", pw=PW, code=None):
    return client.post("/auth/login", json={"email": email, "password": pw, "totp_code": code})


def auth(client, **kw):
    register(client, **{k: v for k, v in kw.items() if k in ("email", "pw")})
    tok = login(client, **{k: v for k, v in kw.items() if k in ("email", "pw")}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_register_validates_and_never_echoes_secrets(client):
    r = register(client)
    assert r.status_code == 201 and set(r.json()) == {"id", "email"}
    assert register(client, email="NANA@Example.com").status_code == 409      # same email, any case
    assert register(client, email="b@example.com", pw="short").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_password_is_stored_hashed(app, client):
    register(client)
    with app.state.session_factory() as db:
        u = db.scalar(select(User))
        assert u.password_hash.startswith("scrypt$") and PW not in u.password_hash


def test_login_and_me(client):
    register(client)
    r = login(client)
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    me = client.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "nana@example.com"


def test_wrong_password_and_unknown_email_look_identical(client):
    register(client)
    a, b = login(client, pw="wrong-password-123"), login(client, email="ghost@example.com")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_protected_routes_reject_missing_forged_and_expired_tokens(client, clock):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer forged.token.here"}).status_code == 401
    h = auth(client)
    assert client.get("/me", headers=h).status_code == 200
    clock.t += 16 * 60
    assert client.get("/me", headers=h).status_code == 401


def test_lockout_after_repeated_failures_then_recovers(client, clock):
    register(client)
    for _ in range(5):
        assert login(client, pw="wrong-password-123").status_code == 401
    locked = login(client)                       # correct password, but locked
    assert locked.status_code == 429 and "Retry-After" in locked.headers
    clock.t += 16 * 60
    assert login(client).status_code == 200


def test_two_factor_flow_including_replay_protection(client, clock):
    h = auth(client)
    secret = client.post("/auth/2fa/setup", headers=h).json()["secret"]
    assert client.post("/auth/2fa/enable", json={"code": "000000"}, headers=h).status_code == 401
    ok = client.post("/auth/2fa/enable", json={"code": totp.code_at(secret, clock.t)}, headers=h)
    assert ok.status_code == 200 and client.get("/me", headers=h).json()["totp_enabled"] is True

    assert login(client).json()["detail"] == "totp_required"
    assert login(client, code="000000").status_code == 401
    code = totp.code_at(secret, clock.t)
    assert login(client, code=code).status_code == 200
    assert login(client, code=code).status_code == 401          # same code again: replay refused
    clock.t += 30
    assert login(client, code=totp.code_at(secret, clock.t)).status_code == 200


def test_totp_secret_is_encrypted_in_the_database(app, client):
    h = auth(client)
    secret = client.post("/auth/2fa/setup", headers=h).json()["secret"]
    with app.state.session_factory() as db:
        assert secret not in db.scalar(select(User)).totp_secret_enc


def test_broker_keys_are_encrypted_hidden_and_private_to_their_owner(app, client):
    h = auth(client)
    body = dict(broker="Alpaca", api_key="PKABCDEF123456", api_secret="TOPSECRETVALUE9999")
    assert client.post("/broker-keys", json=body, headers=h).status_code == 422     # no attestation
    r = client.post("/broker-keys", json=dict(body, trade_only_confirmed=True), headers=h)
    assert r.status_code == 201 and r.json()["api_key_hint"] == "3456"
    assert "TOPSECRET" not in r.text

    listing = client.get("/broker-keys", headers=h)
    assert listing.json()[0]["broker"] == "alpaca"
    assert "TOPSECRET" not in listing.text and "PKABCDEF" not in listing.text

    with app.state.session_factory() as db:
        row = db.scalar(select(BrokerKey))
        assert "TOPSECRET" not in row.api_secret_enc and "PKABCDEF" not in row.api_key_enc
        assert app.state.vault.decrypt(row.api_secret_enc) == "TOPSECRETVALUE9999"

    other = auth(client, email="other@example.com")
    assert client.get("/broker-keys", headers=other).json() == []
    assert client.delete(f"/broker-keys/{r.json()['id']}", headers=other).status_code == 404
    assert client.delete(f"/broker-keys/{r.json()['id']}", headers=h).status_code == 204
    assert client.get("/broker-keys", headers=h).json() == []


def test_secrets_never_reach_the_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    h = auth(client)
    secret = client.post("/auth/2fa/setup", headers=h).json()["secret"]
    login(client, pw="wrong-password-123")
    client.post("/broker-keys", headers=h, json=dict(
        broker="alpaca", api_key="PKABCDEF123456", api_secret="TOPSECRETVALUE9999",
        trade_only_confirmed=True))
    for s in (PW, "wrong-password-123", "TOPSECRETVALUE9999", "PKABCDEF123456", secret):
        assert s not in caplog.text
