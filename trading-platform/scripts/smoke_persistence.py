"""Proves the paper account and its history survive a restart of the execution service.

Needs only two services running: execution (port 8002) and the risk manager (port 8003).
  1.  .venv/bin/python scripts/smoke_persistence.py before    places a trade and remembers what it saw
  2.  restart execution: Ctrl+C in its tab, then  bash scripts/run_execution.sh
  3.  .venv/bin/python scripts/smoke_persistence.py after     checks nothing was lost
"""
import json
import sys
import tempfile
from pathlib import Path

import httpx

env = {}
for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

EXEC, RISK = "http://127.0.0.1:8002", "http://127.0.0.1:8003"
XH, RH = {"X-Internal-Token": env["EXECUTION_TOKEN"]}, {"X-Internal-Token": env["RISK_TOKEN"]}
STATE = Path(tempfile.gettempdir()) / "trading_smoke_persistence.json"
mode = sys.argv[1] if len(sys.argv) == 2 else ""
bad = 0


def check(name, ok, detail=""):
    global bad
    bad += not ok
    print(("PASS  " if ok else "FAIL  ") + name + (f"   ({detail})" if detail and not ok else ""))


def trade(qty):
    r = httpx.post(f"{RISK}/evaluate", json=dict(symbol="SPY", side="buy", qty=qty, stop_price=95), headers=RH).json()
    if not r.get("approved"):
        return None, r
    return httpx.post(f"{EXEC}/orders", json=r["approval"], headers=XH), r


if mode == "before":
    httpx.put(f"{EXEC}/paper/prices/SPY", json={"price": 100}, headers=XH).raise_for_status()
    res, r = trade(5)
    check("a trade is approved and filled", res is not None and res.status_code == 200 and res.json()["status"] == "filled", r)
    acct = httpx.get(f"{EXEC}/account", headers=XH).json()
    orders = httpx.get(f"{EXEC}/orders", headers=XH).json()
    check("the order and fill are in the history", len(orders) >= 1 and len(httpx.get(f"{EXEC}/trades", headers=XH).json()) >= 1)
    check("an equity point was recorded", len(httpx.get(f"{EXEC}/equity", headers=XH).json()) >= 1)
    STATE.write_text(json.dumps(dict(account=acct, order_ids=[o["client_order_id"] for o in orders])))
    print(f"\nSaved what I saw (SPY position {acct['positions'].get('SPY')}). Now restart execution, then run: ... after")
elif mode == "after":
    if not STATE.exists():
        sys.exit("Run the 'before' step first.")
    saved = json.loads(STATE.read_text())
    acct = httpx.get(f"{EXEC}/account", headers=XH)
    check("the account is available after the restart", acct.status_code == 200, acct.text)
    a, b = acct.json(), saved["account"]
    check("positions are the same", a["positions"] == b["positions"], f"{a['positions']} vs {b['positions']}")
    check("cash is the same", abs(a["cash"] - b["cash"]) < 1e-6, f"{a['cash']} vs {b['cash']}")
    check("equity is the same", abs(a["equity"] - b["equity"]) < 1e-6)
    check("the remembered price came back", a["prices"].get("SPY") == 100)
    ids = {o["client_order_id"] for o in httpx.get(f"{EXEC}/orders", headers=XH).json()}
    check("every earlier order is still in the history", set(saved["order_ids"]) <= ids)
    res, r = trade(1)
    check("new trades still work after the restart", res is not None and res.status_code == 200, r)
else:
    sys.exit("usage: smoke_persistence.py before|after")

print("\nAll checks passed" if not bad else f"\n{bad} check(s) FAILED")
sys.exit(1 if bad else 0)
