"""Time-based one-time passwords (RFC 6238), standard library only.

Works with Google Authenticator, Aegis, 2FAS and similar apps.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import urllib.parse
from typing import Optional

STEP = 30


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, t: float, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", int(t // STEP)), hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    n = (struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(n).zfill(digits)


def verify(secret: str, code: str, now: float, window: int = 1) -> Optional[int]:
    """Returns the 30-second step number the code belongs to, or None. Accepts +/- `window` steps
    to allow for clock drift. The caller remembers the step so a code can't be used twice."""
    code = str(code).strip()
    if not (code.isdigit() and len(code) == 6):
        return None
    for i in range(-window, window + 1):
        t = now + i * STEP
        if hmac.compare_digest(code_at(secret, t), code):
            return int(t // STEP)
    return None


def provisioning_uri(secret: str, email: str, issuer: str = "TradingPlatform") -> str:
    label = urllib.parse.quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={urllib.parse.quote(issuer)}"
