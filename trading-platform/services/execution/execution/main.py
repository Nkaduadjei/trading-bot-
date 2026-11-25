"""uvicorn entry point: python -m uvicorn execution.main:app --port 8002"""
import os

from .api import create_app
from .config import make_broker
from .paper import PaperBroker
from .restore import build_paper_broker
from .store import Store

_missing = [k for k in ("APPROVAL_KEY", "EXECUTION_TOKEN") if not os.environ.get(k)]
if _missing:
    raise RuntimeError("missing required settings: " + ", ".join(_missing)
                       + " (run: .venv/bin/python scripts/gen_secrets.py --fill .env)")

store = Store(os.environ.get("EXECUTION_DB_URL", "sqlite:///./execution.db"))
broker = make_broker()
if isinstance(broker, PaperBroker):   # rebuild the paper account from the saved history
    broker = build_paper_broker(store, start_cash=float(os.environ.get("PAPER_START_CASH", "100000")))

app = create_app(broker, os.environ["APPROVAL_KEY"], os.environ["EXECUTION_TOKEN"], store=store)
