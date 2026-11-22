# Trading Platform

Automated trading platform: strategy engine, risk gate, broker execution, Spring Boot platform layer, dashboard.

**Status:** backtester, execution service and risk manager built. Platform layer and dashboard are next. Everything else is a placeholder.

| Folder | Owns |
|---|---|
| `services/strategy-engine` | Python. Strategies and the backtester (built) |
| `services/execution` | Python. Broker API only: paper broker and Alpaca client (built, not yet tested against a real broker) |
| `services/risk-manager` | Checks every order before it goes out (built) |
| `services/auth-service`, `api-gateway`, `admin-console` | Spring Boot platform layer (not started) |
| `web/dashboard` | React dashboard (not started) |
| `contracts/` | Shared JSON schemas. The only thing services share |
| `infra/` | docker-compose, migrations, deploy scripts |
| `docs/` | Decisions and runbooks |

Past performance does not predict future results. Nothing here is financial advice.

## Quick start (Linux)

```
scripts/setup.sh        # once: one shared .venv for every service, creates .env
scripts/test_all.sh     # runs every service's tests
scripts/apply_update.sh ~/Downloads/trading-platform.zip   # later: update in place, no duplicate folders
```
