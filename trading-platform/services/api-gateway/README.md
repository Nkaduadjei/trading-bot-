# api-gateway

The single front door (port 8000). Python (FastAPI).

| File | Does |
|---|---|
| `gateway/config.py` | Settings from environment. Refuses weak tokens |
| `gateway/ratelimit.py` | Per-address request limits (strict for login and register) |
| `gateway/app.py` | The routes. A whitelist: nothing else is reachable |

Routes: `POST /auth/register`, `POST /auth/login`, `GET /me`, `POST /auth/2fa/setup`, `POST /auth/2fa/enable`,
`POST|GET /broker-keys`, `DELETE /broker-keys/{id}` (all forwarded to the auth service),
`POST /orders` and `GET /account` (trading, allowed only for emails in `TRADER_EMAILS`), `GET /health`.

How an order flows: gateway checks your login with the auth service, then asks the risk manager,
then forwards the risk manager's SIGNED approval to execution. The gateway never holds the signing
key, so it cannot approve an order itself.

Not exposed on purpose: the kill switch (the admin console will use it), the paper price endpoint, anything not listed above.

Run tests: `python -m pytest -q`. Run: `bash scripts/run_gateway.sh`.
Not built yet: trusting `X-Forwarded-For` behind a proxy (limits are per direct connection), per-user broker accounts.
