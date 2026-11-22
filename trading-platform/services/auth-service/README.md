# auth-service

Python (FastAPI). Accounts, login with optional 2FA, and encrypted storage of broker API keys.

| File | Does |
|---|---|
| `auth_service/config.py` | Settings from environment. Refuses to start with weak or missing secrets |
| `auth_service/security.py` | Password hashing (scrypt), login tokens (JWT), encryption of stored keys |
| `auth_service/totp.py` | 2FA codes (RFC 6238), written with the standard library only |
| `auth_service/db.py` | Database tables: users and broker keys |
| `auth_service/app.py` | The HTTP endpoints |

Endpoints: `POST /auth/register`, `POST /auth/login`, `GET /me`, `POST /auth/2fa/setup`,
`POST /auth/2fa/enable`, `POST /broker-keys`, `GET /broker-keys`, `DELETE /broker-keys/{id}`, `GET /health`.

Run tests: `python -m pytest -q`. Run the server: `scripts/run_auth.sh` (needs `.env`, see `scripts/gen_secrets.py`).

Not built yet: refresh tokens and logout, password reset, an internal endpoint for the execution
service to fetch a decrypted key, and PostgreSQL (the default database is a local SQLite file).
