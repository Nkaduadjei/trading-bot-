import os
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Settings:
    risk_token: str          # for the kill switch
    auth_admin_token: str    # for listing users
    admin_emails: frozenset = frozenset()   # empty means NOBODY is an admin (fails closed)
    auth_url: str = "http://127.0.0.1:8001"
    risk_url: str = "http://127.0.0.1:8003"
    execution_url: str = "http://127.0.0.1:8002"
    gateway_url: str = "http://127.0.0.1:8000"
    allowed_hosts: frozenset = frozenset({"127.0.0.1:8004", "localhost:8004"})
    audit_path: str = "admin_audit.log"
    login_rate_per_min: int = 10
    upstream_timeout: float = 3.0
    clock: Callable[[], float] = time.time
    # Deliberately absent: the approval signing key and the execution token.

    def __post_init__(self):
        if len(self.risk_token) < 32 or len(self.auth_admin_token) < 32:
            raise ValueError("RISK_TOKEN and AUTH_ADMIN_TOKEN must be at least 32 characters")

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        missing = [k for k in ("RISK_TOKEN", "AUTH_ADMIN_TOKEN") if not env.get(k)]
        if missing:
            raise RuntimeError("missing required settings: " + ", ".join(missing)
                               + " (run: .venv/bin/python scripts/gen_secrets.py --fill .env)")
        emails = frozenset(e.strip().lower() for e in env.get("ADMIN_EMAILS", "").split(",") if e.strip())
        return cls(risk_token=env["RISK_TOKEN"], auth_admin_token=env["AUTH_ADMIN_TOKEN"], admin_emails=emails,
                   auth_url=env.get("AUTH_URL", cls.auth_url), risk_url=env.get("RISK_URL", cls.risk_url),
                   execution_url=env.get("EXECUTION_URL", cls.execution_url),
                   gateway_url=env.get("GATEWAY_URL", cls.gateway_url),
                   audit_path=env.get("ADMIN_AUDIT_FILE", "admin_audit.log"))
