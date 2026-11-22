"""uvicorn entry point: python -m uvicorn execution.main:app --port 8002"""
import os

from .api import create_app
from .config import make_broker

_missing = [k for k in ("APPROVAL_KEY", "EXECUTION_TOKEN") if not os.environ.get(k)]
if _missing:
    raise RuntimeError("missing required settings: " + ", ".join(_missing)
                       + " (run: .venv/bin/python scripts/gen_secrets.py --fill .env)")

app = create_app(make_broker(), os.environ["APPROVAL_KEY"], os.environ["EXECUTION_TOKEN"])
