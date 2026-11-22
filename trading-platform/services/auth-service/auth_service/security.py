import base64
import hashlib
import hmac
import os
from typing import Optional

import jwt
from cryptography.fernet import Fernet


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str, n: int = 2 ** 15, r: int = 8, p: int = 1) -> str:
    """scrypt: slow and memory-hungry on purpose, so guessing passwords at scale is expensive."""
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=256 * n * r, dklen=32)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        expected = base64.b64decode(dk)
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=n, r=r, p=p,
                              maxmem=256 * n * r, dklen=len(expected))
        return hmac.compare_digest(calc, expected)
    except Exception:
        return False


# Checked when the email is unknown, so "no such user" takes as long as "wrong password".
DUMMY_HASH = hash_password("dummy-password-used-only-for-timing")


def make_token(user_id: int, secret: str, minutes: int, now: float) -> str:
    claims = {"sub": str(user_id), "iat": int(now), "exp": int(now + minutes * 60)}
    return jwt.encode(claims, secret, algorithm="HS256")


def read_token(token: str, secret: str, now: float) -> Optional[int]:
    """Returns the user id, or None for anything wrong. Expiry uses OUR clock, so tests can move it."""
    try:
        c = jwt.decode(token, secret, algorithms=["HS256"],
                       options={"require": ["exp", "sub"], "verify_exp": False, "verify_iat": False})
        if c["exp"] <= now:
            return None
        return int(c["sub"])
    except Exception:
        return None


class Vault:
    """Encrypts secrets before they touch the database. The key lives only in the environment."""

    def __init__(self, key: str):
        self._f = Fernet(key)

    def encrypt(self, text: str) -> str:
        return self._f.encrypt(text.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()  # raises InvalidToken if tampered
