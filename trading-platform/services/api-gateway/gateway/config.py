import os
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Settings:
    risk_token: str                 # lets the gateway call the risk manager
    execution_token: str            # lets the gateway call execution
    auth_url: str = "http://127.0.0.1:8001"
    risk_url: str = "http://127.0.0.1:8003"
    execution_url: str = "http://127.0.0.1:8002"
    trader_emails: frozenset = frozenset()   # empty means NOBODY may trade (fails closed)
    rate_limit_per_min: int = 120
    auth_rate_limit_per_min: int = 10        # login and register
    max_body_bytes: int = 65536
    upstream_timeout: float = 5.0
    clock: Callable[[], float] = time.time
    # Deliberately absent: the approval key. The gateway can never sign an approval.

    def __post_init__(self):
        if len(self.risk_token) < 32 or len(self.execution_token) < 32:
            raise ValueError("RISK_TOKEN and EXECUTION_TOKEN must be at least 32 characters")

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        missing = [k for k in ("RISK_TOKEN", "EXECUTION_TOKEN") if not env.get(k)]
        if missing:
            raise RuntimeError("missing required settings: " + ", ".join(missing)
                               + " (run: .venv/bin/python scripts/gen_secrets.py --fill .env)")
        emails = frozenset(e.strip().lower() for e in env.get("TRADER_EMAILS", "").split(",") if e.strip())
        return cls(risk_token=env["RISK_TOKEN"], execution_token=env["EXECUTION_TOKEN"],
                   auth_url=env.get("AUTH_URL", cls.auth_url), risk_url=env.get("RISK_URL", cls.risk_url),
                   execution_url=env.get("EXECUTION_URL", cls.execution_url), trader_emails=emails)
