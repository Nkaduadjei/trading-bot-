# Trading Platform

Automated trading platform: strategy engine, risk gate, broker execution, Spring Boot platform layer, dashboard.

**Status:** backtester, execution service, risk manager (with signed approvals), auth service, API gateway, admin console and the order/trade database built. The dashboard is next.

| Folder | Owns |
|---|---|
| `services/strategy-engine` | Python. Strategies and the backtester (built) |
| `services/execution` | Python. Broker API only: paper broker, Alpaca client, HTTP service that accepts only signed orders (built; Alpaca not yet tested with a real account) |
| `services/risk-manager` | Checks every order and signs the approved ones (built) |
| `services/auth-service` | Python (FastAPI). Accounts, 2FA, encrypted broker keys (built) |
| `services/api-gateway` | Python (FastAPI). The single front door on port 8000 (built) |
| `services/admin-console` | Python (FastAPI). Health view, kill switch, users, audit log on port 8004 (built) |
| `web/dashboard` | React dashboard (not started) |
| `contracts/` | Shared JSON schemas. The only thing services share |
| `infra/` | docker-compose, migrations, deploy scripts |
| `docs/` | Decisions and runbooks |

Past performance does not predict future results. Nothing here is financial advice.

## Quick start (Linux)

```
scripts/setup.sh        # once: one shared .venv for every service, creates .env
scripts/test_all.sh     # runs every service's tests
scripts/apply_update.sh ~/Downloads/update-N.zip   # later: update in place, no duplicate folders
```

Trading services (each in its own terminal): `bash scripts/run_execution.sh` (port 8002), `bash scripts/run_risk.sh` (8003),
then `.venv/bin/python scripts/smoke_trading.py` to check they work together.

Whole chain (four terminals): `run_auth.sh`, `run_execution.sh`, `run_risk.sh`, `run_gateway.sh`, then
`.venv/bin/python scripts/smoke_gateway.py`. Put your email in `TRADER_EMAILS` in `.env` first.

Admin console: `bash scripts/run_admin.sh`, open http://127.0.0.1:8004, log in with an email listed in `ADMIN_EMAILS`.
Checks: `.venv/bin/python scripts/smoke_admin.py` (all five services running).

History: execution saves orders, fills and equity snapshots (`services/execution/execution.db`, private, ignored by git).
Restart check: `.venv/bin/python scripts/smoke_persistence.py before`, restart execution, then `... after`.
