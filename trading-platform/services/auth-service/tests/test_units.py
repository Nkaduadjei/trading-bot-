import base64

import pytest
from cryptography.fernet import Fernet, InvalidToken

from auth_service import totp
from auth_service.config import Settings
from auth_service.security import Vault, hash_password, make_token, read_token, verify_password

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize("t,code", [(59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
                                    (1234567890, "005924"), (2000000000, "279037"),
                                    (20000000000, "353130")])
def test_totp_matches_the_rfc_6238_test_vectors(t, code):
    assert totp.code_at(RFC_SECRET, t) == code


def test_totp_verify_window_and_step_number():
    now = 1_000_000_000.0
    code = totp.code_at(RFC_SECRET, now)
    assert totp.verify(RFC_SECRET, code, now) == int(now // 30)
    assert totp.verify(RFC_SECRET, code, now + 30) is not None   # one step of drift is fine
    assert totp.verify(RFC_SECRET, code, now + 120) is None      # too old
    for bad in ("", "12345", "abcdef", "1234567", None):
        assert totp.verify(RFC_SECRET, bad, now) is None


def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert h1 != h2 and h1.startswith("scrypt$") and "correct" not in h1
    assert verify_password("correct horse battery", h1)
    assert not verify_password("wrong", h1)
    for junk in ("", "garbage", "scrypt$x$y$z$a$b", "md5$1$2$3$4$5"):
        assert not verify_password("anything", junk)


def test_token_roundtrip_expiry_and_tampering():
    secret, now = "s" * 40, 1_000_000.0
    tok = make_token(7, secret, 15, now)
    assert read_token(tok, secret, now + 60) == 7
    assert read_token(tok, secret, now + 15 * 60 + 1) is None   # expired
    assert read_token(tok, "x" * 40, now) is None               # wrong secret
    assert read_token(tok[:-3] + "abc", secret, now) is None    # tampered
    assert read_token("not.a.token", secret, now) is None


def test_vault_encrypts_and_detects_tampering():
    v = Vault(Fernet.generate_key().decode())
    enc = v.encrypt("my-secret")
    assert "my-secret" not in enc and v.decrypt(enc) == "my-secret"
    with pytest.raises(InvalidToken):
        v.decrypt(enc[:-4] + "AAAA")
    with pytest.raises(InvalidToken):
        Vault(Fernet.generate_key().decode()).decrypt(enc)       # wrong key


def test_settings_refuse_weak_or_missing_secrets():
    good = Fernet.generate_key().decode()
    with pytest.raises(ValueError):
        Settings(jwt_secret="short", encryption_key=good)
    with pytest.raises(ValueError):
        Settings(jwt_secret="s" * 40, encryption_key="not-a-key")
    with pytest.raises(RuntimeError) as e:
        Settings.from_env({})
    assert "JWT_SECRET" in str(e.value) and "KEY_ENCRYPTION_KEY" in str(e.value)
    assert Settings.from_env({"JWT_SECRET": "s" * 40, "KEY_ENCRYPTION_KEY": good}).max_failed_logins == 5
