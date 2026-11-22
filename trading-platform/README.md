# Trading Platform

Automated trading platform: strategy engine, risk gate, broker execution, Spring Boot platform layer, dashboard.

**Status:** backtester, execution service, risk manager (with signed approvals) and auth service built. API gateway, admin console and dashboard are next.

| Folder | Owns |
|---|---|
| `services/strategy-engine` | Python. Strategies and the backtester (built) |
| `services/execution` | Python. Broker API only: paper broker, Alpaca client, HTTP service that accepts only signed orders (built; Alpaca not yet tested with a real account) |
| `services/risk-manager` | Checks every order and signs the approved ones (built) |
| `services/auth-service` | Python (FastAPI). Accounts, 2FA, encrypted broker keys (built) |
| `services/api-gateway`, `admin-console` | Python (FastAPI) platform layer (not started) |
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
