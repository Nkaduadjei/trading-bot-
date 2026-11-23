import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class Settings:
    jwt_secret: str        # signs login tokens
    encryption_key: str    # Fernet key that encrypts broker keys and 2FA secrets at rest
    database_url: str = "sqlite:///./auth.db"
    access_token_minutes: int = 15
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    min_password_length: int = 12
    clock: Callable[[], float] = time.time  # injectable so tests can move time
    admin_token: Optional[str] = None       # lets the admin console list users; unset = endpoint does not exist

    def __post_init__(self):
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.admin_token is not None and len(self.admin_token) < 32:
            raise ValueError("AUTH_ADMIN_TOKEN must be at least 32 characters")
        try:
            Fernet(self.encryption_key)
        except Exception:
            raise ValueError("KEY_ENCRYPTION_KEY is not a valid Fernet key") from None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        missing = [k for k in ("JWT_SECRET", "KEY_ENCRYPTION_KEY") if not env.get(k)]
        if missing:
            raise RuntimeError("missing required settings: " + ", ".join(missing)
                               + " (see .env.example and scripts/gen_secrets.py)")
        return cls(jwt_secret=env["JWT_SECRET"], encryption_key=env["KEY_ENCRYPTION_KEY"],
                   database_url=env.get("DATABASE_URL", "sqlite:///./auth.db"),
                   admin_token=env.get("AUTH_ADMIN_TOKEN") or None)
