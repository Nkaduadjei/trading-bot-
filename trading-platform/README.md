# Trading Platform

Automated trading platform: strategy engine, risk gate, broker execution, Spring Boot platform layer, dashboard.

**Status:** step 1 of the build order, the backtester (`services/strategy-engine`). Everything else is a placeholder.

| Folder | Owns |
|---|---|
| `services/strategy-engine` | Python. Strategies and the backtester (built) |
| `services/execution` | Python. Broker API only (not started) |
| `services/risk-manager` | Checks every order before it goes out (not started) |
| `services/auth-service`, `api-gateway`, `admin-console` | Spring Boot platform layer (not started) |
| `web/dashboard` | React dashboard (not started) |
| `contracts/` | Shared JSON schemas. The only thing services share |
| `infra/` | docker-compose, migrations, deploy scripts |
| `docs/` | Decisions and runbooks |

Past performance does not predict future results. Nothing here is financial advice.
