"""Checks the admin console and the kill switch against the real running services.

Start all five first (one terminal each): run_auth, run_execution, run_risk, run_gateway, run_admin  (bash scripts/run_X.sh)
Your email must be in ADMIN_EMAILS AND TRADER_EMAILS in .env (restart the gateway and console after editing).
Then:  .venv/bin/python scripts/smoke_admin.py      (it asks for the email and password of the TEST account)
The kill switch is released again at the end, even if a check fails.
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

CON, GW, EXEC = "http://127.0.0.1:8004", "http://127.0.0.1:8000", "http://127.0.0.1:8002"
email = os.environ.get("SMOKE_EMAIL") or input("Test account email (in ADMIN_EMAILS and TRADER_EMAILS): ").strip()
password = os.environ.get("SMOKE_PASSWORD") or getpass.getpass("Test account password: ")
bad = 0


def check(name, ok, detail=""):
    global bad
    bad += not ok
    print(("PASS  " if ok else "FAIL  ") + name + (f"   ({detail})" if detail and not ok else ""))


check("console page loads", httpx.get(f"{CON}/").status_code == 200)
check("admin data is refused without a login", httpx.get(f"{CON}/api/users").status_code == 401)

creds = dict(email=email, password=password)
r = httpx.post(f"{CON}/api/login", json=creds)
if r.status_code == 401:
    httpx.post(f"{GW}/auth/register", json=creds)
    r = httpx.post(f"{CON}/api/login", json=creds)
check("admin login works", r.status_code == 200, r.text)
if r.status_code != 200:
    sys.exit("cannot continue without a login")
H = {"Authorization": "Bearer " + r.json()["access_token"]}

h = httpx.get(f"{CON}/api/health", headers=H)
if h.status_code == 403:
    print("      Your email is not in ADMIN_EMAILS. Add it to .env, restart the console, and run again.")
    sys.exit(1)
check("all four services report up", h.status_code == 200 and set(h.json()["services"].values()) == {"up"}, h.text)

u = httpx.get(f"{CON}/api/users", headers=H)
check("users are listed without secrets", u.status_code == 200 and any(x["email"] == email.lower() for x in u.json())
      and "password" not in u.text and "scrypt" not in u.text, u.text)

try:
    httpx.put(f"{EXEC}/paper/prices/SPY", json={"price": 100}, headers={"X-Internal-Token": env["EXECUTION_TOKEN"]}).raise_for_status()
    token = httpx.post(f"{GW}/auth/login", json=creds).json()["access_token"]
    GH = {"Authorization": "Bearer " + token}
    order = dict(symbol="SPY", side="buy", qty=1, stop_price=95)

    e = httpx.post(f"{CON}/api/kill/engage", headers=H, json={"reason": "smoke test"})
    check("kill switch engages", e.status_code == 200 and e.json()["engaged"], e.text)
    blocked = httpx.post(f"{GW}/orders", json=order, headers=GH)
    check("a buy is refused while it is engaged", blocked.status_code == 200 and not blocked.json()["approved"]
          and "halted" in str(blocked.json()["reasons"]), blocked.text)
finally:
    rel = httpx.post(f"{CON}/api/kill/release", headers=H)
check("kill switch releases", rel.status_code == 200 and rel.json()["engaged"] is False, rel.text)
ok = httpx.post(f"{GW}/orders", json=order, headers=GH)
check("a buy is approved again after release", ok.status_code == 200 and ok.json()["approved"], ok.text)

a = httpx.get(f"{CON}/api/audit", headers=H)
actions = [x["action"] for x in a.json()] if a.status_code == 200 else []
check("both actions are in the audit log", "kill_engage" in actions and "kill_release" in actions, a.text)

print("\nAll checks passed" if not bad else f"\n{bad} check(s) FAILED")
sys.exit(1 if bad else 0)
