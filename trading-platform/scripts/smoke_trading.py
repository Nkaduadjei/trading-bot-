"""Checks that the execution and risk-manager services work together, and that the gate holds.

Start both first:  bash scripts/run_execution.sh   and   bash scripts/run_risk.sh   (two terminals)
Then run:          .venv/bin/python scripts/smoke_trading.py
"""
import sys
from pathlib import Path

import httpx

env = {}
for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

EXEC, RISK = "http://127.0.0.1:8002", "http://127.0.0.1:8003"
XH, RH = {"X-Internal-Token": env["EXECUTION_TOKEN"]}, {"X-Internal-Token": env["RISK_TOKEN"]}
bad = 0


def check(name, ok, detail=""):
    global bad
    bad += not ok
    print(("PASS  " if ok else "FAIL  ") + name + (f"   ({detail})" if detail and not ok else ""))


httpx.put(f"{EXEC}/paper/prices/SPY", json={"price": 100}, headers=XH).raise_for_status()
r = httpx.post(f"{RISK}/evaluate", json=dict(symbol="SPY", side="buy", qty=50, stop_price=95), headers=RH).json()
check("risk manager approves a sensible order", r.get("approved"), r)

a = r["approval"]
o = httpx.post(f"{EXEC}/orders", json=a, headers=XH)
check("execution fills an approved order", o.status_code == 200 and o.json()["status"] == "filled", o.text)

acct = httpx.get(f"{EXEC}/account", headers=XH).json()
check("the position shows up in the account", acct["positions"].get("SPY", 0) >= 50, acct)

forged = dict(a, order=dict(a["order"], qty=5000, client_order_id="forged-order-0001"))
check("a tampered order is refused", httpx.post(f"{EXEC}/orders", json=forged, headers=XH).status_code == 403)

nosig = dict(order=dict(a["order"], client_order_id="nosig-order-0001"), approved_at=a["approved_at"], signature="0" * 64)
check("an order with a fake signature is refused", httpx.post(f"{EXEC}/orders", json=nosig, headers=XH).status_code == 403)

check("calls without the internal token are refused", httpx.post(f"{EXEC}/orders", json=a).status_code == 401)

big = httpx.post(f"{RISK}/evaluate", json=dict(symbol="SPY", side="buy", qty=100000, stop_price=95), headers=RH).json()
check("an oversized order is cut down or refused, never passed through",
      (not big["approved"]) or big["approval"]["order"]["qty"] < 100000, big)

print("\nAll checks passed" if not bad else f"\n{bad} check(s) FAILED")
sys.exit(1 if bad else 0)
