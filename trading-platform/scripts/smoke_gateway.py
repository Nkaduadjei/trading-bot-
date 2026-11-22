"""Checks the whole chain through the gateway: login -> risk manager -> signed approval -> execution.

Start all four services first, each in its own terminal:
  bash scripts/run_auth.sh   bash scripts/run_execution.sh   bash scripts/run_risk.sh   bash scripts/run_gateway.sh
Your email must be in TRADER_EMAILS in .env (then restart the gateway).
Then:  .venv/bin/python scripts/smoke_gateway.py      (it asks for the email and password of a TEST account)
"""
import getpass
import os
import sys
from pathlib import Path

import httpx

env = {}
for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

GW, EXEC = "http://127.0.0.1:8000", "http://127.0.0.1:8002"
email = os.environ.get("SMOKE_EMAIL") or input("Test account email (must be in TRADER_EMAILS): ").strip()
password = os.environ.get("SMOKE_PASSWORD") or getpass.getpass("Test account password (12+ characters): ")
bad = 0


def check(name, ok, detail=""):
    global bad
    bad += not ok
    print(("PASS  " if ok else "FAIL  ") + name + (f"   ({detail})" if detail and not ok else ""))


check("gateway is up", httpx.get(f"{GW}/health").status_code == 200)
check("an order without a login is refused", httpx.post(f"{GW}/orders", json=dict(symbol="SPY", side="buy", qty=10, stop_price=95)).status_code == 401)
for path in ("/kill", "/admin", "/paper/prices/SPY"):
    check(f"{path} is not reachable from outside", httpx.get(f"{GW}{path}").status_code in (404, 405))

creds = dict(email=email, password=password)
r = httpx.post(f"{GW}/auth/login", json=creds)
if r.status_code == 401:
    httpx.post(f"{GW}/auth/register", json=creds)
    r = httpx.post(f"{GW}/auth/login", json=creds)
check("login works", r.status_code == 200, r.text)
if r.status_code != 200:
    sys.exit("cannot continue without a login")
H = {"Authorization": "Bearer " + r.json()["access_token"]}

httpx.put(f"{EXEC}/paper/prices/SPY", json={"price": 100}, headers={"X-Internal-Token": env["EXECUTION_TOKEN"]}).raise_for_status()
o = httpx.post(f"{GW}/orders", json=dict(symbol="SPY", side="buy", qty=10, stop_price=95), headers=H)
if o.status_code == 403:
    print("      Your email is not in TRADER_EMAILS. Add it to .env, restart the gateway, and run again.")
check("a sensible order goes through risk check and is filled",
      o.status_code == 200 and o.json().get("approved") and o.json()["order"]["status"] == "filled", o.text)
a = httpx.get(f"{GW}/account", headers=H)
check("the position shows in the account", a.status_code == 200 and a.json()["positions"].get("SPY", 0) >= 10, a.text)
check("a nonsense order is rejected", httpx.post(f"{GW}/orders", json=dict(symbol="SPY", side="buy", qty=-5), headers=H).status_code == 422)
big = httpx.post(f"{GW}/orders", json=dict(symbol="SPY", side="buy", qty=500000, stop_price=95), headers=H)
check("an oversized order is cut down or refused", big.status_code == 200 and (not big.json()["approved"] or big.json()["order"]["qty"] < 500000), big.text)
print("\nAll checks passed" if not bad else f"\n{bad} check(s) FAILED")
sys.exit(1 if bad else 0)
