"""uvicorn entry point: python -m uvicorn risk_manager.main:app --port 8003"""
import os

from .api import create_app, http_account_fetcher
from .killswitch import KillSwitch
from .state import StateStore

_missing = [k for k in ("APPROVAL_KEY", "RISK_TOKEN", "EXECUTION_TOKEN") if not os.environ.get(k)]
if _missing:
    raise RuntimeError("missing required settings: " + ", ".join(_missing)
                       + " (run: .venv/bin/python scripts/gen_secrets.py --fill .env)")

app = create_app(
    http_account_fetcher(os.environ.get("EXECUTION_URL", "http://127.0.0.1:8002"),
                         os.environ["EXECUTION_TOKEN"]),
    os.environ["APPROVAL_KEY"], os.environ["RISK_TOKEN"],
    kill=KillSwitch(os.environ.get("KILL_SWITCH_FILE", "kill_switch.json")),
    store=StateStore(os.environ.get("RISK_STATE_FILE", "risk_state.json")))
